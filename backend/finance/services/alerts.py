"""Derive preventive alerts from the exact sequence returned by the projection."""
from datetime import timedelta
from decimal import Decimal

ZERO = Decimal("0.00")

ALERT_ASSUMPTIONS = {
    "continuous_negative_episode": "Etapas consecutivas com saldo negativo formam um único episódio. O episódio termina no primeiro saldo não negativo; novo déficit posterior inicia outro episódio.",
    "first_day_peak": "A insuficiência inicial é a primeira passagem para negativo. A maior falta na primeira data e a maior falta de todo o episódio são informadas separadamente.",
    "zero_is_no_margin": "Saldo zero encerra o déficit, mas continua sem margem. Ausência de margem e insuficiência podem ser observadas em momentos diferentes do mesmo dia.",
    "contextual_expenses": "Os compromissos listados são o contexto das datas do episódio, não uma atribuição de culpa ou recomendação de deixar uma conta sem pagamento.",
    "deficit_income_dependency": "A dependência indicada considera apenas entradas previstas que reduzem o déficit observado ou permitem sair dele. Não é uma comparação com um cenário alternativo sem renda.",
}


def income_info(event, day):
    return {"id": event["occurrence_id"], "description": event["description"], "amount": event["amount"], "date": day, "status": "estimated", "outside_analysis": False}


def build_alerts(days, reference, end):
    alerts = []
    risk = waiting_margin = None
    zero_active = False
    margin_dates = set()

    def common(kind, day, sequence):
        return {"id": f"{kind}:{day.isoformat()}:{sequence}", "type": kind, "date": day, "start_sequence": sequence,
                "reference_date": reference, "analysis_start": reference, "analysis_end": end,
                "outside_chart": day > reference + timedelta(days=14)}

    for day in days:
        current_date = day["date"]
        points = [(0, day["opening_balance"], None, day["opening_balance"])]
        previous = day["opening_balance"]
        for event in day["events"]:
            points.append((event["sequence"], event["balance_after"], event, previous))
            previous = event["balance_after"]
        for sequence, balance, event, before in points:
            if risk is not None and event and event["direction"] == "income" and before < ZERO:
                risk["recovery_incomes"].append({**income_info(event, current_date), "role": "closes_deficit" if balance >= ZERO else "partial_reduction",
                                                "deficit_reduction": min(event["amount"], -before), "remaining_shortfall": max(-balance, ZERO)})
            if balance < ZERO:
                waiting_margin = None
                if risk is None:
                    risk = {**common("insufficient", current_date, sequence), "first_shortfall": -balance,
                            "first_day_shortfall": -balance, "max_shortfall": -balance, "max_shortfall_date": current_date,
                            "max_shortfall_sequence": sequence, "starts_with_deficit": current_date == reference and sequence == 0,
                            "expenses": [], "recovery_incomes": [], "margin_recovery_date": None,
                            "margin_recovery_sequence": None, "margin_recovery_income": None,
                            "end_date": end, "end_sequence": len(days[-1]["events"]), "end_reason": "horizon_limit", "ongoing": True}
                    alerts.append(risk)
                if current_date == risk["date"]:
                    risk["first_day_shortfall"] = max(risk["first_day_shortfall"], -balance)
                if -balance > risk["max_shortfall"]:
                    risk.update(max_shortfall=-balance, max_shortfall_date=current_date, max_shortfall_sequence=sequence)
            elif risk is not None:
                risk.update(recovery_date=current_date, recovery_balance=balance, end_date=current_date, end_sequence=sequence,
                            end_reason="zero_margin" if balance == ZERO else "positive_margin", ongoing=False)
                waiting_margin = risk
                risk = None
            if waiting_margin is not None and balance > ZERO:
                waiting_margin.update(margin_recovery_date=current_date, margin_recovery_sequence=sequence,
                                      margin_recovery_income=income_info(event, current_date) if event and event["direction"] == "income" else None)
                waiting_margin = None
            if balance == ZERO and not zero_active and current_date not in margin_dates:
                alerts.append(common("no_margin", current_date, sequence))
                margin_dates.add(current_date)
            zero_active = balance == ZERO

    for alert in alerts:
        last_date = alert.get("end_date", alert["date"])
        context = [day for day in days if alert["date"] <= day["date"] <= last_date]
        codes = ["zero_is_no_margin"]
        if alert["type"] == "insufficient":
            codes += ["continuous_negative_episode", "first_day_peak", "contextual_expenses", "deficit_income_dependency"]
            alert["expenses"] = [{"id": event["occurrence_id"], "description": event["description"], "amount": event["amount"],
                                  "due_date": event["original_date"], "effective_date": day["date"], "is_estimate": event["is_estimate"]}
                                 for day in context for event in day["events"] if event["direction"] == "expense"]
            alert["income_dependency"] = {"criterion": "estimated_entries_reducing_the_observed_deficit",
                                           "recovery_relies_on_estimates": bool(alert["recovery_incomes"]) and not alert["ongoing"],
                                           "reduction_relies_on_estimates": bool(alert["recovery_incomes"])}
        codes += [code for day in context for code in day["assumption_codes"]]
        alert["assumption_codes"] = list(dict.fromkeys(codes))
    return alerts


def attach_relevant_incomes(alerts, forecasts, days, analysis_end):
    positions = {event["occurrence_id"]: (day["date"], event["sequence"]) for day in days for event in day["events"]}
    for alert in alerts:
        start = (alert["date"], alert["start_sequence"])
        relevant = next((item for item in forecasts if item["date"] >= alert["date"] and positions.get(item["id"], (item["date"], 1)) > start), None)
        if relevant is None:
            alert["next_income"] = None
            continue
        outside = relevant["date"] > analysis_end
        role = next((item["role"] for item in alert.get("recovery_incomes", []) if item["id"] == relevant["id"]), "projected_income")
        alert["next_income"] = {**relevant, "outside_analysis": outside, "role": "outside_analysis" if outside else role}
