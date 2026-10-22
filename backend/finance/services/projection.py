"""Deterministic daily projection. No database or model dependency."""
from datetime import timedelta
from decimal import Decimal


def project(balance, reference, end, events):
    days, alerts = [], []
    risk = None
    zero_start = None
    margin_dates = set()
    for offset in range((end - reference).days + 1):
        date = reference + timedelta(days=offset)
        today = sorted((e for e in events if e["date"] == date), key=lambda e: (e["direction"] == "income", e["id"]))
        opening = balance
        minimum = balance
        incoming = outgoing = Decimal("0.00")

        def observe():
            nonlocal risk, zero_start
            if balance < 0:
                if risk is None:
                    risk = {"type": "insufficient", "date": date, "first_shortfall": -balance, "max_shortfall": -balance, "expenses": []}
                    alerts.append(risk)
                risk["max_shortfall"] = max(risk["max_shortfall"], -balance)
            elif risk is not None:
                risk["recovery_date"] = date
                risk = None
            if balance == 0 and zero_start is None:
                if date not in margin_dates:
                    alerts.append({"type": "no_margin", "date": date})
                    margin_dates.add(date)
                zero_start = date
            elif balance != 0:
                zero_start = None

        observe()
        for event in today:
            if event["direction"] == "expense":
                balance -= event["amount"]
                outgoing += event["amount"]
            else:
                balance += event["amount"]
                incoming += event["amount"]
            minimum = min(minimum, balance)
            observe()
        # Show the day's commitments together, without assigning priority or blame.
        expenses = [{"id": e["id"], "description": e["description"], "amount": e["amount"], "due_date": e["due_date"]} for e in today if e["direction"] == "expense"]
        for alert in alerts:
            if alert["type"] == "insufficient" and alert["date"] <= date and alert.get("recovery_date", end) >= date:
                alert["expenses"].extend(expenses)
        days.append({"date": date, "opening_balance": opening, "income": incoming, "expenses": outgoing, "minimum_balance": minimum, "closing_balance": balance})
    for alert in alerts:
        alert["outside_chart"] = alert["date"] > reference + timedelta(days=14)
        if alert["type"] == "insufficient":
            alert["ongoing"] = "recovery_date" not in alert
    return days, alerts
