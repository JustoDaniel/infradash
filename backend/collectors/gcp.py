import os
import json
from datetime import date
from pathlib import Path

# Config file lives at the project root (two levels up from this file)
_DEFAULT_CONFIG = str(Path(__file__).parent.parent.parent / "gcp_billings.json")
CONFIG_PATH = os.getenv("GCP_BILLINGS_CONFIG", _DEFAULT_CONFIG)


def load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"credentials_path": "", "billings": []}


def _table_from_account_id(billing_account_id: str) -> str:
    """Deriva o nome da tabela BigQuery a partir do ID da billing account.
    Ex: '010F20-0DC5CD-C6859C' → 'gcp_billing_export_v1_010F20_0DC5CD_C6859C'
    """
    normalized = billing_account_id.upper().replace("-", "_")
    return f"gcp_billing_export_v1_{normalized}"


def collect_gcp() -> dict:
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests
        import requests as http

        config = load_config()
        cred_path = config.get("credentials_path") or os.getenv("GCP_CREDENTIALS_PATH")
        billings = [b for b in config.get("billings", []) if b.get("enabled", True)]

        if not cred_path:
            return _error(
                "Credenciais GCP não configuradas. "
                "Abra o painel Admin (⚙) e informe o caminho do arquivo de service account."
            )

        if not billings:
            return _error(
                "Nenhuma billing account GCP configurada. "
                "Abra o painel Admin (⚙) e adicione suas billing accounts."
            )

        credentials = service_account.Credentials.from_service_account_file(
            cred_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        token = credentials.token
        headers = {"Authorization": f"Bearer {token}"}

        today = date.today()
        first = today.replace(day=1).isoformat()

        # Acumula projetos e total de todas as billings
        projects_map: dict[str, dict] = {}
        grand_total = 0.0
        billing_errors: list[str] = []

        for billing in billings:
            project_id = billing["project_id"]
            dataset    = billing.get("dataset", "gcp_billing_data")
            table      = billing.get("table") or _table_from_account_id(billing["billing_account_id"])
            label      = billing.get("name", billing["billing_account_id"])

            # Query com breakdown por projeto GCP (útil em orgs com múltiplos projetos)
            query = f"""
            SELECT
              project.id   AS project_id,
              project.name AS project_name,
              service.description AS service,
              ROUND(SUM(cost), 2) AS total
            FROM `{project_id}.{dataset}.{table}`
            WHERE DATE(usage_start_time) >= '{first}'
              AND DATE(usage_start_time) <= '{today.isoformat()}'
            GROUP BY project_id, project_name, service
            ORDER BY project_id, total DESC
            """

            url  = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project_id}/queries"
            body = {"query": query, "useLegacySql": False, "timeoutMs": 15000}

            try:
                r    = http.post(url, headers=headers, json=body, timeout=20)
                data = r.json()

                if "error" in data:
                    billing_errors.append(f"[{label}] {data['error'].get('message', str(data['error']))}")
                    continue

                for row in data.get("rows", []):
                    vals = row.get("f", [])
                    if len(vals) < 4:
                        continue
                    proj_id   = vals[0].get("v") or "unknown"
                    proj_name = vals[1].get("v") or proj_id
                    svc_name  = vals[2].get("v") or "Outros"
                    cost      = float(vals[3].get("v", 0) or 0)
                    if cost <= 0:
                        continue
                    if proj_id not in projects_map:
                        projects_map[proj_id] = {"id": proj_id, "name": proj_name, "total": 0.0, "services": []}
                    projects_map[proj_id]["services"].append({"name": svc_name, "cost": round(cost, 2)})
                    projects_map[proj_id]["total"] = round(projects_map[proj_id]["total"] + cost, 2)
                    grand_total += cost

            except Exception as e:
                billing_errors.append(f"[{label}] {e}")

        projects = sorted(projects_map.values(), key=lambda p: p["total"], reverse=True)

        # Lista flat de serviços (top 10, soma entre todos os projetos/billings)
        all_services: dict[str, float] = {}
        for proj in projects:
            for svc in proj["services"]:
                all_services[svc["name"]] = round(all_services.get(svc["name"], 0) + svc["cost"], 2)
        services = sorted(
            [{"name": k, "cost": v} for k, v in all_services.items()],
            key=lambda s: s["cost"], reverse=True
        )[:10]

        return {
            "provider":   "GCP",
            "label":      "Google Cloud Platform",
            "color":      "#2563eb",
            "bg":         "#dbeafe",
            "text_color": "#1e40af",
            "total":      round(grand_total, 2),
            "currency":   "USD",
            "delta_pct":  0,
            "services":   services,
            "projects":   projects,
            "error":      "; ".join(billing_errors) if billing_errors else None,
        }

    except Exception as e:
        return _error(str(e))


def _error(msg: str) -> dict:
    return {
        "provider":   "GCP",
        "label":      "Google Cloud Platform",
        "color":      "#2563eb",
        "bg":         "#dbeafe",
        "text_color": "#1e40af",
        "total":      0,
        "currency":   "USD",
        "delta_pct":  0,
        "services":   [],
        "projects":   [],
        "error":      msg,
    }
