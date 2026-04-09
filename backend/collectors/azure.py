"""
Collector: Microsoft Azure Cost Management
Usa azure-identity + azure-mgmt-costmanagement
"""

import os
from datetime import datetime, timedelta

from azure.identity import ClientSecretCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryDefinition,
    QueryTimePeriod,
    QueryDataset,
    QueryAggregation,
    QueryGrouping,
    TimeframeType,
)


def _get_credentials():
    return ClientSecretCredential(
        tenant_id=os.getenv("AZURE_TENANT_ID"),
        client_id=os.getenv("AZURE_CLIENT_ID"),
        client_secret=os.getenv("AZURE_CLIENT_SECRET"),
    )


def get_costs() -> dict:
    try:
        subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        if not subscription_id:
            return {"error": "AZURE_SUBSCRIPTION_ID não configurado", "total": 0, "services": []}

        credential = _get_credentials()
        client = CostManagementClient(credential)

        scope = f"/subscriptions/{subscription_id}"

        # Período: início do mês até hoje
        today = datetime.utcnow()
        first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        query = QueryDefinition(
            type="ActualCost",
            timeframe=TimeframeType.CUSTOM,
            time_period=QueryTimePeriod(
                from_property=first_day,
                to=today,
            ),
            dataset=QueryDataset(
                granularity="None",
                aggregation={
                    "totalCost": QueryAggregation(name="Cost", function="Sum")
                },
                grouping=[
                    QueryGrouping(type="Dimension", name="ServiceName")
                ],
            ),
        )

        result = client.query.usage(scope=scope, parameters=query)

        services = []
        total = 0.0
        currency = "USD"

        if result and result.rows:
            for row in result.rows:
                cost = float(row[0]) if row[0] else 0.0
                service_name = str(row[1]) if len(row) > 1 else "Unknown"
                if len(row) > 2:
                    currency = str(row[2])
                if cost > 0:
                    services.append({"name": service_name, "cost": round(cost, 4)})
                    total += cost

        services.sort(key=lambda x: x["cost"], reverse=True)

        return {
            "provider": "Azure",
            "label": "Microsoft Azure",
            "total": round(total, 2),
            "currency": currency,
            "services": services[:8],
            "period": f"{first_day.strftime('%d/%m')} – {today.strftime('%d/%m/%Y')}",
            "delta_pct": 0,
            "error": None,
        }

    except Exception as e:
        return {
            "provider": "Azure",
            "label": "Microsoft Azure",
            "error": str(e),
            "total": 0,
            "delta_pct": 0,
            "services": [],
        }
