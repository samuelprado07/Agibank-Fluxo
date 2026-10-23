"""Deterministic daily projection. No database or model dependency."""
from datetime import timedelta
from decimal import Decimal
from .alerts import ALERT_ASSUMPTIONS, build_alerts

ASSUMPTION_DETAILS = {
    **ALERT_ASSUMPTIONS,
    "reference_cutoff": "Na referência, a abertura é o saldo atual, já incluindo as entradas e saídas realizadas até essa data, inclusive; não é o saldo no início do dia civil.",
    "previous_close_opening": "A abertura deste dia corresponde ao fechamento projetado do dia anterior.",
    "projected_events_only": "A sequência contém somente previsões pendentes; realizações já incorporadas ao saldo atual não são reaplicadas.",
    "expenses_before_income": "Saídas são consideradas antes das entradas previstas no mesmo dia. Horários bancários não são simulados.",
    "technical_id_order": "Dentro de cada direção, o identificador da ocorrência desempata a ordem; isso não indica prioridade de pagamento.",
    "overdue_expense_at_reference": "Despesas vencidas, incluindo estimativas vencidas, são consideradas imediatas na referência. A data original é preservada.",
    "estimated_income": "A entrada é uma previsão e depende do recebimento na data informada; não há garantia de disponibilidade.",
    "monthly_occurrence": "Somente a ocorrência mensal participa do cálculo; a configuração da recorrência não é somada novamente.",
    "variable_estimate": "A estimativa utiliza o valor e a data informados; não representa um pagamento realizado.",
    "no_events": "Nenhuma entrada ou saída prevista foi considerada neste dia; o saldo foi mantido.",
}


def project(balance, reference, end, events):
    days = []
    for offset in range((end - reference).days + 1):
        date = reference + timedelta(days=offset)
        today = sorted((e for e in events if e["date"] == date), key=lambda e: (e["direction"] == "income", e["id"]))
        opening = balance
        minimum = balance
        incoming = outgoing = Decimal("0.00")
        ordered_events = []
        assumption_codes = ["reference_cutoff" if date == reference else "previous_close_opening", "projected_events_only", "expenses_before_income", "technical_id_order"]

        for event in today:
            if event["direction"] == "expense":
                balance -= event["amount"]
                outgoing += event["amount"]
            else:
                balance += event["amount"]
                incoming += event["amount"]
            minimum = min(minimum, balance)
            is_estimate = event.get("is_estimate", False)
            is_recurring = event.get("is_recurring", False)
            ordered_events.append({
                "occurrence_id": event["id"], "description": event["description"],
                "direction": event["direction"], "amount": event["amount"],
                "original_date": event["due_date"], "effective_date": date,
                "source": "estimate" if is_estimate else event["direction"],
                "status": "pending", "is_estimate": is_estimate, "is_recurring": is_recurring,
                "series_id": event.get("series_id"), "series_type": event.get("series_type"),
                "competence": event.get("competence"), "sequence": len(ordered_events) + 1,
                "balance_after": balance,
            })
            if event["direction"] == "expense" and event["due_date"] < reference:
                assumption_codes.append("overdue_expense_at_reference")
            if event["direction"] == "income":
                assumption_codes.append("estimated_income")
            if is_estimate:
                assumption_codes.append("variable_estimate")
            if is_recurring:
                assumption_codes.append("monthly_occurrence")
        if not ordered_events:
            assumption_codes.append("no_events")
        days.append({"date": date, "opening_balance": opening, "income": incoming, "expenses": outgoing, "minimum_balance": minimum, "closing_balance": balance, "events": ordered_events, "assumption_codes": list(dict.fromkeys(assumption_codes))})
    return days, build_alerts(days, reference, end)
