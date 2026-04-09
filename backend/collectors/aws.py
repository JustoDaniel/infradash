"""
Collector AWS — Cost Explorer + EC2
Permissões IAM necessárias:
  - ce:GetCostAndUsage
  - ec2:DescribeInstances (opcional, para listar recursos)
"""

import os
from datetime import date, timedelta
import boto3
from botocore.exceptions import NoCredentialsError, ClientError


def collect_aws() -> dict:
    try:
        session = boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        )

        ce = session.client("ce", region_name="us-east-1")  # Cost Explorer só existe em us-east-1

        today = date.today()
        first_of_month = today.replace(day=1)
        # Cost Explorer precisa que end > start e end não pode ser hoje se ainda não fechou
        end = today.isoformat() if today.day > 1 else (today + timedelta(days=1)).isoformat()

        resp = ce.get_cost_and_usage(
            TimePeriod={
                "Start": first_of_month.isoformat(),
                "End": end,
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        services = []
        total = 0.0

        for result in resp.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                name = group["Keys"][0]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                if amount < 0.01:
                    continue
                services.append({"name": name, "cost": round(amount, 2)})
                total += amount

        services.sort(key=lambda x: x["cost"], reverse=True)
        top_services = services[:6]  # top 6 por custo

        # Delta mês anterior
        prev_end = first_of_month.isoformat()
        prev_start = (first_of_month - timedelta(days=1)).replace(day=1).isoformat()
        prev_resp = ce.get_cost_and_usage(
            TimePeriod={"Start": prev_start, "End": prev_end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
        prev_total = 0.0
        for r in prev_resp.get("ResultsByTime", []):
            prev_total += float(r["Total"]["UnblendedCost"]["Amount"])

        delta_pct = ((total - prev_total) / prev_total * 100) if prev_total > 0 else 0

        return {
            "provider": "AWS",
            "label": "Amazon Web Services",
            "color": "#E59400",
            "bg": "#fef3c7",
            "text_color": "#92400e",
            "total": round(total, 2),
            "currency": "USD",
            "delta_pct": round(delta_pct, 1),
            "services": top_services,
            "error": None,
        }

    except NoCredentialsError:
        return _error("AWS", "Credenciais não configuradas. Edite o .env")
    except ClientError as e:
        return _error("AWS", str(e))
    except Exception as e:
        return _error("AWS", str(e))


def _error(provider: str, msg: str) -> dict:
    return {
        "provider": "AWS",
        "label": "Amazon Web Services",
        "color": "#E59400",
        "bg": "#fef3c7",
        "text_color": "#92400e",
        "total": 0,
        "currency": "USD",
        "delta_pct": 0,
        "services": [],
        "error": msg,
    }
