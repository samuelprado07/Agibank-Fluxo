import re
import json
from datetime import date
from decimal import Decimal
from django.core import signing
from .projection_context import AssistantError, capture_context, metadata, facts_for
from .gemini_provider import generate
from .local_explanations import local_explanation, FALLBACK_REASONS, TEMPLATE_VERSION, LABEL

HISTORY_SALT = 'finance.assistant.history.v1'
REFERENCE = re.compile(r'\{\{([a-zA-Z0-9_.]+)\}\}')


def display_fact(path, value):
    if isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return date.fromisoformat(value).strftime('%d/%m/%Y')
    if isinstance(value, str) and re.fullmatch(r'-?\d+\.\d{2}', value):
        amount = f'{Decimal(value):,.2f}'.replace(',', 'x').replace('.', ',').replace('x', '.')
        return f'R$ {amount}'
    return str(value)


def validate_answer(answer, facts):
    if not isinstance(answer, dict) or set(answer) != {'paragraphs'} or not isinstance(answer['paragraphs'], list) or not 1 <= len(answer['paragraphs']) <= 4:
        raise AssistantError('A resposta da IA não pôde ser validada.', 'invalid_response', 502)
    references = {}
    paragraphs = []
    for paragraph in answer['paragraphs']:
        if not isinstance(paragraph, str) or not paragraph.strip() or len(paragraph) > 1500:
            raise AssistantError('A resposta da IA não pôde ser validada.', 'invalid_response', 502)
        plain = REFERENCE.sub('', paragraph)
        if re.search(r'\d|[{}<>]|https?://|R\$|%', plain):
            raise AssistantError('A resposta contém informação numérica sem referência válida. Tente novamente.', 'invalid_response', 502)
        def replace(match):
            path = match.group(1)
            if path not in facts:
                raise AssistantError('A resposta cita informação indisponível. Tente novamente.', 'invalid_response', 502)
            value = display_fact(path, facts[path])
            references[path] = {'id': path, 'value': facts[path], 'display': value}
            return value
        paragraphs.append(REFERENCE.sub(replace, paragraph).strip())
    return '\n\n'.join(paragraphs), list(references.values())


def respond(payload):
    if not isinstance(payload, dict) or set(payload) - {'message', 'projection_version', 'alternative_token', 'history_token'}:
        raise AssistantError('Campos adicionais não são permitidos.')
    message = payload.get('message')
    if not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
        raise AssistantError('Escreva uma pergunta de até dois mil caracteres.')
    for key, limit in [('projection_version', 64), ('alternative_token', 20000), ('history_token', 80000)]:
        if payload.get(key) is not None and (not isinstance(payload[key], str) or len(payload[key]) > limit):
            raise AssistantError('Dados de consulta inválidos.')
    context = capture_context(payload.get('alternative_token'))
    if payload.get('projection_version') != context['projection_version']:
        raise AssistantError('O planejamento mudou. Atualize a projeção antes de perguntar.', 'stale_projection', 409)
    history = []
    if payload.get('history_token'):
        try:
            previous = signing.loads(payload['history_token'], salt=HISTORY_SALT)
            if not isinstance(previous, dict):
                raise signing.BadSignature()
            if previous.get('version') == context['projection_version'] and previous.get('alternative_version') == metadata(context)['alternative_version']:
                history = previous.get('turns', [])[-3:]
        except signing.BadSignature:
            raise AssistantError('O histórico da conversa é inválido. Inicie uma nova conversa.') from None
    facts = facts_for(context)
    outbound = {'schema_version': context['schema_version'], 'calculation_version': context['calculation_version'], 'reference_date': context['reference_date'],
                'period': context['period'], 'projection_policy': context['projection_policy'], 'assumptions': context['assumptions'], 'warnings': context['warnings'],
                'facts': facts, 'has_alternative': context['alternative'] is not None}
    if len(json.dumps(outbound, ensure_ascii=False)) > 180000:
        raise AssistantError('Este planejamento tem dados demais para uma orientação segura nesta consulta.', 'context_too_large', 413)
    fallback_reason = None
    try:
        raw = generate(outbound, message.strip(), history)
        text, references = validate_answer(raw, facts)
    except AssistantError as error:
        if error.code not in FALLBACK_REASONS:
            raise
        fallback_reason = error.code
        text, references = validate_answer(local_explanation(context), facts)
    current = capture_context()
    version = context['projection_version']
    alternative_version = metadata(context)['alternative_version']
    mode = 'local' if fallback_reason else 'gemini'
    turns = (history + [{'question': message.strip(), 'answer': text, 'response_mode': mode}])[-3:]
    return {**metadata(context), 'text': text, 'references': references, 'provider': mode,
            'response_mode': mode, 'fallback_reason': fallback_reason,
            'template_version': TEMPLATE_VERSION if fallback_reason else None,
            'label': LABEL if fallback_reason else 'Gemini',
            'stale': current['projection_version'] != version, 'current_projection_version': current['projection_version'],
            'history_token': signing.dumps({'version': version, 'alternative_version': alternative_version, 'turns': turns}, salt=HISTORY_SALT, compress=True),
            'limitations': 'Orientação informativa baseada em estimativas. Não garante recebimentos nem resultados; necessidades essenciais não devem ser cortadas automaticamente.'}
