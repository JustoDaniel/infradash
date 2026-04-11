"""
Collector DigitalOcean — Billing API
Permissões necessárias: Personal Access Token com escopo billing:read
"""

import os
import requests
from datetime import date, timedelta


BASE_URL = "https://api.digitalocean.com/v2"
TIMEOUT = 15


def collect_digitalocean() -> dict:
    token = os.getenv("DIGITALOCEAN_TOKEN")
    if not token:
        return _error("Token não configurado. Adicione DIGITALOCEAN_TOKEN no .env")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        # Custo do mês atual
        bal_resp = requests.get(
            f"{BASE_URL}/customers/my/balance",
            headers=headers,
            timeout=TIMEOUT,
        )
        if bal_resp.status_code == 401:
            return _error("Token inválido ou sem permissão de billing")
        bal_resp.raise_for_status()
        balance = bal_resp.json()

        total = abs(float(balance.get("month_to_date_usage", 0)))

        # Histórico de faturas para delta vs mês anterior
        hist_resp = requests.get(
            f"{BASE_URL}/customers/my/billing_history",
            headers=headers,
            params={"per_page": 5},
            timeout=TIMEOUT,
        )
        hist_resp.raise_for_status()
        history = hist_resp.json().get("billing_history", [])

        prev_total = _find_prev_month_total(history)
        delta_pct = ((total - prev_total) / prev_total * 100) if prev_total > 0 else 0

        # Breakdown via sumário da fatura mais recente (mês anterior)
        services = _get_invoice_summary(headers, history)

        return {
            "provider": "DO",
            "label": "DigitalOcean",
            "color": "#0069ff",
            "bg": "#eff6ff",
            "text_color": "#1e40af",
            "total": round(total, 2),
            "currency": "USD",
            "delta_pct": round(delta_pct, 1),
            "services": services,
            "error": None,
        }

    except requests.exceptions.ConnectionError:
        return _error("Sem conexão com a API da DigitalOcean")
    except Exception as e:
        return _error(str(e))


def _find_prev_month_total(history: list) -> float:
    """Retorna o valor da fatura do mês anterior."""
    today = date.today()
    last_month = (today.replace(day=1) - timedelta(days=1))

    for entry in history:
        if entry.get("type") != "Invoice":
            continue
        try:
            invoice_date = date.fromisoformat(entry.get("date", "")[:10])
            if invoice_date.year == last_month.year and invoice_date.month == last_month.month:
                return abs(float(entry.get("amount", 0)))
        except (ValueError, TypeError):
            pass

    # Fallback: primeira fatura disponível
    for entry in history:
        if entry.get("type") == "Invoice":
            return abs(float(entry.get("amount", 0)))

    return 0.0


def _get_invoice_summary(headers: dict, history: list) -> list:
    """
    Obtém o sumário da fatura mais recente como breakdown de serviços.
    A DigitalOcean não expõe breakdown do mês corrente — usa a última fatura fechada.
    """
    invoice_uuid = None
    for entry in history:
        if entry.get("type") == "Invoice" and entry.get("invoice_uuid"):
            invoice_uuid = entry["invoice_uuid"]
            break

    if not invoice_uuid:
        return []

    try:
        resp = requests.get(
            f"{BASE_URL}/customers/my/invoices/{invoice_uuid}/summary",
            headers=headers,
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []

        items = resp.json().get("product_charges", {}).get("items", [])
        services = [
            {"name": item.get("name", "Unknown"), "cost": round(abs(float(item.get("amount", 0))), 2)}
            for item in items
            if abs(float(item.get("amount", 0))) >= 0.01
        ]
        services.sort(key=lambda x: x["cost"], reverse=True)
        return services[:6]

    except Exception:
        return []


def _error(msg: str) -> dict:
    return {
        "provider": "DO",
        "label": "DigitalOcean",
        "color": "#0069ff",
        "bg": "#eff6ff",
        "text_color": "#1e40af",
        "total": 0,
        "currency": "USD",
        "delta_pct": 0,
        "services": [],
        "error": msg,
    }
