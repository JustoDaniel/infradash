import os
from datetime import date

def collect_gcp() -> dict:
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests
        import requests

        cred_path = os.getenv("GCP_CREDENTIALS_PATH")
        project_id = os.getenv("GCP_PROJECT_ID")
        dataset = "gcp_billing_data"
        table = "gcp_billing_export_v1_0167BE_F4BEC3_50DA1D"

        credentials = service_account.Credentials.from_service_account_file(
            cred_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        token = credentials.token
        headers = {"Authorization": f"Bearer {token}"}

        today = date.today()
        first = today.replace(day=1).isoformat()

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

        url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project_id}/queries"
        body = {"query": query, "useLegacySql": False, "timeoutMs": 15000}
        r = requests.post(url, headers=headers, json=body, timeout=20)
        data = r.json()

        if "error" in data:
            return _error(data["error"].get("message", str(data["error"])))

        rows = data.get("rows", [])
        projects_map = {}
        total = 0.0

        for row in rows:
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
            total += cost

        projects = sorted(projects_map.values(), key=lambda p: p["total"], reverse=True)

        # flat services list (top 6 across all projects) for backward compat
        all_services: dict = {}
        for proj in projects:
            for svc in proj["services"]:
                all_services[svc["name"]] = round(all_services.get(svc["name"], 0) + svc["cost"], 2)
        services = sorted(
            [{"name": k, "cost": v} for k, v in all_services.items()],
            key=lambda s: s["cost"], reverse=True
        )[:6]

        return {
            "provider": "GCP",
            "label": "Google Cloud Platform",
            "color": "#2563eb",
            "bg": "#dbeafe",
            "text_color": "#1e40af",
            "total": round(total, 2),
            "currency": "USD",
            "delta_pct": 0,
            "services": services,
            "projects": projects,
            "error": None,
        }

    except Exception as e:
        return _error(str(e))


def _error(msg):
    return {
        "provider": "GCP", "label": "Google Cloud Platform",
        "color": "#2563eb", "bg": "#dbeafe", "text_color": "#1e40af",
        "total": 0, "currency": "USD", "delta_pct": 0,
        "services": [], "error": msg,
    }
