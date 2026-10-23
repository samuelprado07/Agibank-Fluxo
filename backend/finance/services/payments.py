import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from finance.models import Movement, Occurrence, PaymentHistory, PaymentOperation, ReceiptHistory, ReceiptOperation, Scenario


class PaymentError(Exception):
    def __init__(self, message, status=409, errors=None):
        super().__init__(message)
        self.status = status
        self.errors = errors or {}


def validate(payload, action):
    allowed = {"key", "version"} | ({"amount", "date"} if action != "undo" else set()) | ({"reason"} if action != "confirm" else set())
    errors = {key: ["Campo não permitido."] for key in payload.keys() - allowed}
    try:
        key = UUID(payload.get("key", "")) if isinstance(payload.get("key"), str) else None
        if key is None:
            raise ValueError
    except ValueError:
        errors["key"] = ["Informe uma chave UUID para esta operação."]
        key = None
    if type(payload.get("version")) is not int or payload["version"] < 0:
        errors["version"] = ["Informe a versão atual do pagamento."]
    if action != "confirm" and (not isinstance(payload.get("reason"), str) or not 1 <= len(payload["reason"].strip()) <= 500):
        errors["reason"] = ["Informe o motivo, com até 500 caracteres."]
    if action != "undo":
        amount = payload.get("amount")
        if not isinstance(amount, str) or not re.fullmatch(r"\d{1,12}(?:\.\d{1,2})?", amount) or Decimal(amount) <= 0:
            errors["amount"] = ["Informe um valor positivo com até 12 dígitos inteiros e 2 decimais."]
        try:
            if not isinstance(payload.get("date"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload["date"]):
                raise ValueError
            date.fromisoformat(payload["date"])
        except ValueError:
            errors["date"] = ["Informe uma data válida no formato AAAA-MM-DD."]
    if errors:
        raise PaymentError("Confira os dados do pagamento.", 400, errors)
    return key


def snapshot(movement):
    if movement is None:
        return {}
    return {"amount": str(movement.amount), "date": movement.date.isoformat(), "is_voided": movement.is_voided, "version": movement.version}


@transaction.atomic
def change_payment(expense_id, action, payload, *, scenario, income=False):
    # Both directions share the same lock, idempotency and audit contract.
    operation_model = ReceiptOperation if income else PaymentOperation
    history_model = ReceiptHistory if income else PaymentHistory
    direction = "income" if income else "expense"
    key = validate(payload, action)
    fingerprint = hashlib.sha256(json.dumps([scenario.pk if scenario else None, expense_id, action, payload], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    expense = Occurrence.objects.select_for_update().filter(pk=expense_id, scenario=scenario, direction=direction).first()
    if expense is None:
        raise PaymentError("Despesa não encontrada.", 404)
    previous = operation_model.objects.filter(key=key).first()
    if previous:
        if previous.fingerprint != fingerprint:
            raise PaymentError("Esta chave já foi utilizada com outros dados.")
        return previous.result
    movement = Movement.objects.select_for_update().filter(occurrence=expense).first()
    if payload["version"] != (movement.version if movement else 0):
        raise PaymentError("Este pagamento foi alterado. Atualize a lista antes de continuar.")
    active = movement is not None and not movement.is_voided
    if action == "confirm":
        if expense.status != "pending" or active:
            raise PaymentError("Somente uma despesa pendente e sem pagamento ativo pode ser paga.")
    elif expense.status != "settled" or not active:
        raise PaymentError("Não há pagamento ativo consistente para corrigir ou desfazer.")
    if movement and (movement.scenario_id != scenario.pk or movement.direction != direction):
        raise PaymentError("O vínculo do pagamento precisa ser revisado.")
    if action != "undo":
        effective_date = date.fromisoformat(payload["date"])
        if not scenario.opening_date <= effective_date <= scenario.reference_date:
            raise PaymentError("A data efetiva deve estar entre a abertura e a referência do cenário.", 400, {"date": [f"Use uma data entre {scenario.opening_date} e {scenario.reference_date}."]})
    before = snapshot(movement)
    if action == "undo":
        movement.is_voided = True
        expense.status = "pending"
    else:
        if movement is None:
            movement = Movement(scenario=scenario, occurrence=expense, direction=direction, description=expense.description, version=0)
        movement.amount = Decimal(payload["amount"]).quantize(Decimal("0.01"))
        movement.date = effective_date
        movement.is_voided = False
        expense.status = "settled"
    movement.version += 1
    movement.full_clean()
    movement.save()
    expense.save(update_fields=["status"])
    result = {"occurrence_id": expense.pk, "status": expense.status, "receipt" if income else "payment": snapshot(movement)}
    operation = operation_model.objects.create(key=key, fingerprint=fingerprint, result=result)
    history_model.objects.create(movement=movement, operation=operation, action=action, reason=payload.get("reason", "").strip(), before=before, after=snapshot(movement))
    return result
