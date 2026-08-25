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


def _get_token(cred_path: str) -> str:
    """Autentica uma service account e retorna o bearer token."""
    from google.oauth2 import service_account
    import google.auth.transport.requests
    credentials = service_account.Credentials.from_service_account_file(
        cred_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


def collect_gcp() -> dict:
    try:
        import requests as http

        config = load_config()
        global_cred_path = config.get("credentials_path") or os.getenv("GCP_CREDENTIALS_PATH")
        billings = [b for b in config.get("billings", []) if b.get("enabled", True)]

        if not billings:
            # Fallback: variáveis de ambiente (método legado, pré-admin panel)
            env_project = os.getenv("GCP_PROJECT_ID")
            env_billing = os.getenv("GCP_BILLING_ACCOUNT_ID")
            env_dataset = os.getenv("GCP_DATASET", "gcp_billing_data")
            if env_project and env_billing:
                billings = [{
                    "id": "env",
                    "name": "GCP (via env)",
                    "billing_account_id": env_billing,
                    "project_id": env_project,
                    "dataset": env_dataset,
                    "enabled": True,
                }]
            else:
                return _error(
                    "Nenhuma billing account GCP configurada. "
                    "Abra o painel Admin (⚙) e adicione suas billing accounts."
                )

        # Cache de tokens por arquivo de credenciais — evita re-auth para mesma SA
        token_cache: dict[str, str] = {}

        today = date.today()
        first = today.replace(day=1).isoformat()

        # Acumula projetos e total de todas as billings
        projects_map: dict[str, dict] = {}
        grand_total = 0.0
        billing_errors: list[str] = []
        billings_breakdown: list[dict] = []  # total por billing account

        for billing in billings:
            label      = billing.get("name", billing["billing_account_id"])
            billing_id = billing["billing_account_id"]
            # Credencial específica da billing tem prioridade sobre a global
            cred_path  = billing.get("credentials_path") or global_cred_path

            if not cred_path:
                billing_errors.append(
                    f"[{label}] Credenciais não configuradas. "
                    "Defina a service account global ou uma específica para esta billing."
                )
                billings_breakdown.append({"name": label, "id": billing_id, "total": 0.0, "error": True})
                continue

            if cred_path not in token_cache:
                try:
                    token_cache[cred_path] = _get_token(cred_path)
                except Exception as e:
                    billing_errors.append(f"[{label}] Erro ao autenticar service account: {e}")
                    billings_breakdown.append({"name": label, "id": billing_id, "total": 0.0, "error": True})
                    continue

            headers    = {"Authorization": f"Bearer {token_cache[cred_path]}"}
            project_id = billing["project_id"]
            dataset    = billing.get("dataset", "gcp_billing_data")
            table      = billing.get("table") or _table_from_account_id(billing["billing_account_id"])

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

            billing_total = 0.0
            try:
                r    = http.post(url, headers=headers, json=body, timeout=20)
                data = r.json()

                if "error" in data:
                    billing_errors.append(f"[{label}] {data['error'].get('message', str(data['error']))}")
                    billings_breakdown.append({"name": label, "id": billing_id, "total": 0.0, "error": True})
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
                    grand_total  += cost
                    billing_total += cost

                billings_breakdown.append({"name": label, "id": billing_id, "total": round(billing_total, 2), "error": False})

            except Exception as e:
                billing_errors.append(f"[{label}] {e}")
                billings_breakdown.append({"name": label, "id": billing_id, "total": 0.0, "error": True})

        billings_breakdown.sort(key=lambda b: b["total"], reverse=True)

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
            "provider":           "GCP",
            "label":              "Google Cloud Platform",
            "color":              "#2563eb",
            "bg":                 "#dbeafe",
            "text_color":         "#1e40af",
            "total":              round(grand_total, 2),
            "currency":           "USD",
            "delta_pct":          0,
            "services":           services,
            "projects":           projects,
            "billings_breakdown": billings_breakdown,
            "error":              "; ".join(billing_errors) if billing_errors else None,
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
