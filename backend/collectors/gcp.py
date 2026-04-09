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
          service.description AS service,
          ROUND(SUM(cost), 2) AS total
        FROM `{project_id}.{dataset}.{table}`
        WHERE DATE(usage_start_time) >= '{first}'
          AND DATE(usage_start_time) <= '{today.isoformat()}'
        GROUP BY service
        ORDER BY total DESC
        LIMIT 10
        """

        url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project_id}/queries"
        body = {"query": query, "useLegacySql": False, "timeoutMs": 15000}
        r = requests.post(url, headers=headers, json=body, timeout=20)
        data = r.json()

        if "error" in data:
            return _error(data["error"].get("message", str(data["error"])))

        rows = data.get("rows", [])
        services = []
        total = 0.0

        for row in rows:
            vals = row.get("f", [])
            if len(vals) >= 2:
                name = vals[0].get("v", "Outros") or "Outros"
                cost = float(vals[1].get("v", 0) or 0)
                if cost > 0:
                    services.append({"name": name, "cost": round(cost, 2)})
                    total += cost

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
