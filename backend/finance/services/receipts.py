from .payments import PaymentError, change_payment


def change_receipt(income_id, action, payload, *, scenario):
    try:
        return change_payment(income_id, action, payload, scenario=scenario, income=True)
    except PaymentError as error:
        message = str(error).replace("Despesa", "Renda").replace("despesa", "renda").replace("pagamento", "recebimento").replace("paga.", "recebida.")
        errors = {key: [text.replace("pagamento", "recebimento") for text in values] for key, values in error.errors.items()}
        raise PaymentError(message, error.status, errors) from error
