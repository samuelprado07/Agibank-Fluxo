"""Capture read-only, versioned facts. Provider requests happen after this transaction."""
import json
from datetime import date
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from .dashboard import capture_projection, build_from_snapshot
from .projection_version import CALCULATION_VERSION, projection_version
from .simulations import active_scenario, fingerprint, target, validated_change, compare, SALT, VERSION


class AssistantError(Exception):
    def __init__(self, message, code='invalid_request', status=400):
        super().__init__(message)
        self.code, self.status = code, status


@transaction.atomic
def capture_context(alternative_token=None):
    scenario = active_scenario()
    scenario, movements, occurrences = capture_projection(scenario.pk, materialize=False)
    base = build_from_snapshot(scenario, movements, occurrences)
    alternative = None
    if alternative_token:
        try:
            token = signing.loads(alternative_token, salt=SALT)
            if not isinstance(token, dict):
                raise ValueError()
            if token.get('version') != VERSION or token.get('scenario_id') != scenario.pk:
                raise ValueError()
            if token.get('fingerprint') != fingerprint(scenario):
                raise AssistantError('O planejamento mudou. Calcule a alternativa novamente.', 'stale_alternative', 409)
            occurrence = target(scenario, token['occurrence_id'])
            changes, _ = validated_change(occurrence, token['changes'])
            calculated = compare(scenario, movements, occurrences, occurrence, changes, fixed_end=date.fromisoformat(token['end']))
            alternative = {key: calculated[key] for key in ('comparison', 'period', 'warnings', 'before', 'after')}
            alternative['version'] = projection_version(alternative)
        except (signing.BadSignature, KeyError, TypeError, ValueError):
            raise AssistantError('Alternativa inválida. Simule novamente.') from None
    data = {key: base[key] for key in ('reference_date', 'period', 'indicators', 'days', 'alerts', 'next_incomes', 'overdue_incomes', 'assumptions', 'warnings', 'projection_policy')}
    # Only planning data; no customer profile, account, key, raw ledger or audit trail.
    context = {'schema_version': 1, 'calculation_version': CALCULATION_VERSION,
               'projection_version': base['projection_version'], 'generated_at': timezone.now().isoformat(),
               **data, 'alternative': alternative,
               'essential_expenses': [{'description': item.description, 'date': item.due_date, 'amount': item.amount} for item in occurrences if item.direction == 'expense' and item.essential and item.status == 'pending' and item.due_date <= base['period']['end']]}
    return json.loads(json.dumps(context, cls=DjangoJSONEncoder))


def metadata(context):
    return {key: context[key] for key in ('schema_version', 'calculation_version', 'projection_version', 'generated_at', 'reference_date', 'period')} | {'alternative_version': context['alternative']['version'] if context['alternative'] else None}


def facts_for(context):
    """Every numeric/date mention must reference one of these server-owned facts."""
    facts = {}
    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                if key not in ('id', 'occurrence_id', 'series_id', 'sequence', 'start_sequence', 'end_sequence', 'version', 'max_shortfall_sequence', 'margin_recovery_sequence'):
                    walk(item, f'{path}.{key}' if path else key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f'{path}.{index}')
        elif value is not None and not isinstance(value, bool):
            facts[path] = value
    for key in ('reference_date', 'period', 'indicators', 'days', 'alerts', 'next_incomes', 'overdue_incomes', 'essential_expenses', 'alternative'):
        walk(context[key], key)
    return facts
