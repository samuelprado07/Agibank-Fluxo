import copy
import hashlib
import json
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

from finance.models import ExpenseSeries, ExpenseSeriesExclusion, ExpenseSeriesRevision, IncomeSeries, IncomeSeriesRevision, Movement, Occurrence, Scenario, SimulationApplication
from .dashboard import build_dashboard, build_from_snapshot, capture_projection
from .expenses import edit_expense, require_editable, validate_expense
from .incomes import edit_income, require_pending, validate_income

SALT = "finance.alternative.v1"
VERSION = 1


class SimulationError(Exception):
    def __init__(self, message, status=400, errors=None):
        super().__init__(message)
        self.status = status
        self.errors = errors or {}


def active_scenario():
    scenario = Scenario.objects.order_by("pk").first()
    if scenario is None:
        raise SimulationError("Nenhum planejamento financeiro cadastrado.", 404)
    return scenario


def fingerprint(scenario):
    sources = [(Scenario, {"pk": scenario.pk}), (Occurrence, {"scenario": scenario}), (Movement, {"scenario": scenario}),
               (ExpenseSeries, {"scenario": scenario}), (IncomeSeries, {"scenario": scenario}),
               (ExpenseSeriesRevision, {"series__scenario": scenario}), (IncomeSeriesRevision, {"series__scenario": scenario}),
               (ExpenseSeriesExclusion, {"series__scenario": scenario})]
    values = {model.__name__: list(model.objects.filter(**filters).order_by("pk").values()) for model, filters in sources}
    return hashlib.sha256(json.dumps(values, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def target(scenario, occurrence_id):
    if type(occurrence_id) is not int or occurrence_id <= 0:
        raise SimulationError("Selecione uma ocorrência válida.")
    occurrence = Occurrence.objects.filter(scenario=scenario, pk=occurrence_id).first()
    if occurrence is None:
        raise SimulationError("Ocorrência não encontrada neste planejamento.", 404)
    if occurrence.direction == "expense":
        require_editable(occurrence)
    elif occurrence.direction == "income":
        require_pending(occurrence)
    else:
        raise SimulationError("Tipo de ocorrência inválido.")
    return occurrence


def validated_change(occurrence, changes):
    if not isinstance(changes, dict) or not changes or changes.keys() - {"amount", "date"}:
        raise SimulationError("Informe apenas valor e/ou data de uma única ocorrência.")
    mapped = {("due_date" if occurrence.direction == "expense" else "expected_date") if key == "date" else key: value for key, value in changes.items()}
    if occurrence.direction == "expense":
        form, errors = validate_expense(mapped, occurrence)
        if errors:
            raise SimulationError("Confira os dados da alternativa.", errors=errors)
        amount, when = form.cleaned_data["amount"], form.cleaned_data["due_date"]
    else:
        values = validate_income(mapped, occurrence)
        amount, when = values["amount"], values["expected_date"]
    if amount == occurrence.amount and when == occurrence.due_date:
        raise SimulationError("Altere o valor ou a data para testar uma alternativa.")
    return {"amount": f"{amount:.2f}", "date": when.isoformat()}, mapped


def summarize(result):
    deficits = [alert for alert in result["alerts"] if alert["type"] == "insufficient"]
    return {"status": "insufficient" if deficits else "no_insufficiency", "first_deficit_date": deficits[0]["date"] if deficits else None,
            "max_shortfall": max((alert["max_shortfall"] for alert in deficits), default=Decimal("0.00")),
            "has_no_margin": any(alert["type"] == "no_margin" for alert in result["alerts"])}


def compare(scenario, movements, occurrences, occurrence, changes, *, fixed_end=None):
    before = build_from_snapshot(scenario, movements, occurrences, fixed_end=fixed_end)
    end = before["period"]["end"]
    alternative = [copy.copy(row) for row in occurrences]
    for row in alternative:
        if row.pk == occurrence.pk and not row._state.adding:
            row.amount = Decimal(changes["amount"])
            row.due_date = date.fromisoformat(changes["date"])
            row.is_exception = bool(row.series_id or row.income_series_id) or row.is_exception
    after = build_from_snapshot(scenario, movements, alternative, fixed_end=end)
    for result in (before, after):
        result["projection_policy"]["horizon"] = "fixed_base_comparison_period"
        result["assumptions"].append("Nesta comparação, referência e período são fixados pela base. Alterar datas não altera condições reais dos compromissos.")
    moved = occurrence.due_date <= end < date.fromisoformat(changes["date"])
    warnings = ["Alterar uma data na simulação não modifica vencimentos, acordos ou condições reais do compromisso."]
    if moved:
        warnings.append("A ocorrência foi movida para depois do período comparado. A ausência de déficit nesse período não significa que o compromisso deixou de existir.")
    elif date.fromisoformat(changes["date"]) > end:
        warnings.append("A ocorrência continua após o período comparado e não foi incluída nas movimentações desse intervalo.")
    return {"reference_date": scenario.reference_date, "period": before["period"], "before": before, "after": after,
            "comparison": {"before": summarize(before), "after": summarize(after)}, "moved_outside_horizon": moved, "warnings": warnings}


@transaction.atomic
def preview(payload):
    if payload.keys() - {"occurrence_id", "changes"}:
        raise SimulationError("Campos adicionais não são permitidos na prévia.")
    scenario = active_scenario()
    scenario, movements, occurrences = capture_projection(scenario.pk, materialize=False)
    occurrence = target(scenario, payload.get("occurrence_id"))
    changes, _ = validated_change(occurrence, payload.get("changes"))
    result = compare(scenario, movements, occurrences, occurrence, changes)
    token_data = {"version": VERSION, "scenario_id": scenario.pk, "occurrence_id": occurrence.pk, "changes": changes,
                  "fingerprint": fingerprint(scenario), "end": result["period"]["end"].isoformat(), "reference_date": scenario.reference_date.isoformat()}
    result["preview_token"] = signing.dumps(token_data, salt=SALT, compress=True)
    result["occurrence"] = {"id": occurrence.pk, "description": occurrence.description, "direction": occurrence.direction,
                            "original_amount": occurrence.amount, "original_date": occurrence.due_date, "changes": changes,
                            "scope": "this", "is_recurring": bool(occurrence.series_id or occurrence.income_series_id)}
    return result


@transaction.atomic
def apply_preview(payload):
    if set(payload) != {"preview_token", "key"} or not isinstance(payload.get("preview_token"), str) or not isinstance(payload.get("key"), str):
        raise SimulationError("Informe o token da prévia e a chave da aplicação.")
    try:
        key = UUID(payload["key"])
        data = signing.loads(payload["preview_token"], salt=SALT)
    except (ValueError, signing.BadSignature):
        raise SimulationError("A prévia é inválida. Calcule a alternativa novamente.")
    digest = hashlib.sha256(payload["preview_token"].encode()).hexdigest()
    previous = SimulationApplication.objects.filter(key=key).first()
    if previous:
        if previous.token_digest != digest:
            raise SimulationError("Esta chave já foi utilizada para outra alternativa.", 409)
        return previous.result
    scenario = active_scenario()
    if data.get("version") != VERSION or data.get("scenario_id") != scenario.pk or data.get("fingerprint") != fingerprint(scenario):
        raise SimulationError("O planejamento mudou após a prévia. Atualize os dados e simule novamente.", 409)
    scenario, movements, occurrences = capture_projection(scenario.pk, materialize=False)
    occurrence = target(scenario, data["occurrence_id"])
    changes, mapped = validated_change(occurrence, data["changes"])
    compared = compare(scenario, movements, occurrences, occurrence, changes, fixed_end=date.fromisoformat(data["end"]))
    if occurrence.direction == "expense":
        form, _ = validate_expense(mapped, occurrence)
        edit_expense(occurrence, form, "this")
    else:
        edit_income(occurrence, mapped)
    dashboard = build_dashboard(scenario)
    operation = SimulationApplication.objects.create(key=key, token_digest=digest, occurrence=occurrence, result={})
    result = {"applied": True, "application_id": operation.pk, "occurrence_id": occurrence.pk,
              "comparison": compared["comparison"], "comparison_period": compared["period"], "dashboard": dashboard}
    operation.result = json.loads(json.dumps(result, cls=DjangoJSONEncoder))
    operation.save(update_fields=["result"])
    return operation.result


@transaction.atomic
def context():
    scenario = active_scenario()
    linked = Movement.objects.filter(scenario=scenario, is_voided=False, occurrence__isnull=False).values_list("occurrence_id", flat=True)
    rows = scenario.occurrences.filter(status="pending", direction__in=("expense", "income")).exclude(pk__in=linked).order_by("due_date", "pk")
    return {"reference_date": scenario.reference_date, "occurrences": [{"id": row.pk, "description": row.description, "amount": row.amount,
              "date": row.due_date, "direction": row.direction, "is_estimate": row.is_estimate,
              "is_recurring": bool(row.series_id or row.income_series_id)} for row in rows]}
