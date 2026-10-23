"""Deterministic explanations using only financial engine facts, never free-form answers."""
TEMPLATE_VERSION = 'local-explanations-v1'
LABEL = 'Explicações automáticas demonstrativas'
FALLBACK_REASONS = frozenset({'provider_timeout', 'provider_unavailable', 'provider_rate_limit', 'provider_configuration', 'assistant_unavailable', 'invalid_response'})


def local_explanation(context):
    paragraphs = ['A IA não está disponível nesta resposta. Este resumo local não permite responder livremente a qualquer pergunta; utiliza apenas os resultados calculados para o período de {{period.start}} a {{period.end}}.']
    alternative = context.get('alternative')
    if alternative:
        comparison = alternative['comparison']
        def result_text(side):
            path = f'alternative.comparison.{side}'
            result = comparison[side]
            if result['status'] == 'insufficient':
                return 'Primeira insuficiência em {{' + path + '.first_deficit_date}}; maior falta estimada de {{' + path + '.max_shortfall}}.'
            return 'Nenhuma insuficiência identificada no período; maior falta estimada de {{' + path + '.max_shortfall}}.'
        paragraphs.append('Comparação no mesmo período calculado: antes — ' + result_text('before') + ' Alternativa — ' + result_text('after') + ' Isso não altera as condições reais dos compromissos nem garante sua cobertura fora do período comparado.')
        if comparison['after']['has_no_margin']:
            paragraphs[-1] += ' A alternativa ainda apresenta ausência de margem em algum ponto.'
        if alternative.get('moved_outside_period') or any('depois do período' in warning or 'fora do período' in warning for warning in alternative.get('warnings', [])):
            paragraphs[-1] += ' Há compromisso fora da janela comparada; ele continua existindo.'
    else:
        deficit = next(((index, alert) for index, alert in enumerate(context['alerts']) if alert['type'] == 'insufficient'), None)
        margin = next(((index, alert) for index, alert in enumerate(context['alerts']) if alert['type'] == 'no_margin'), None)
        if deficit:
            index, alert = deficit
            root = f'alerts.{index}'
            text = 'Os recursos considerados podem não cobrir os compromissos. Primeiro déficit em {{' + root + '.date}}, com falta inicial estimada de {{' + root + '.first_shortfall}} e maior falta no episódio de {{' + root + '.max_shortfall}}.'
            if alert.get('expenses'):
                text += ' Um compromisso associado ao intervalo é {{' + root + '.expenses.0.description}}, previsto em {{' + root + '.expenses.0.due_date}} por {{' + root + '.expenses.0.amount}}. Isso não determina qual despesa deve deixar de ser paga.'
            text += ' Ajustes no orçamento podem não ser suficientes para cobrir a necessidade de recursos.'
            paragraphs.append(text)
        elif margin:
            index, _ = margin
            paragraphs.append('O saldo chega a zero em {{alerts.' + str(index) + '.date}}. Há ausência de margem para despesas adicionais nesse ponto, mesmo sem déficit identificado.')
        else:
            paragraphs.append('Nenhuma insuficiência identificada nos dados e no período considerados. O saldo projetado ao final é {{indicators.projected_final}}; isso não garante disponibilidade nem cobre gastos ausentes do cadastro.')
    if context.get('overdue_incomes'):
        paragraphs.append('Há recebimento atrasado, como {{overdue_incomes.0.description}}, esperado em {{overdue_incomes.0.date}}. Ele não está disponível na projeção até confirmação ou atualização da previsão.')
    elif not context.get('next_incomes'):
        paragraphs.append('Não há próximo recebimento elegível informado no horizonte analisado. Os dados não permitem estimar uma nova renda nem garantir como os compromissos serão cobertos.')
    else:
        paragraphs.append('O próximo recebimento de {{next_incomes.0.amount}}, previsto para {{next_incomes.0.date}}, ainda é estimado. Saídas são consideradas antes de entradas no mesmo dia; realizações já incluídas no saldo atual não são descontadas novamente.')
    paragraphs.append('Estimativa condicionada aos dados cadastrados: gastos ausentes e previsões não confirmadas podem alterar o resultado. Consulte os cadastros e, para comparar uma mudança ainda não calculada, use Simular. Necessidades essenciais não devem ser cortadas automaticamente.')
    if context.get('warnings'):
        paragraphs[-1] += ' Atenção aos dados: {{warnings.0}}'
    return {'paragraphs': paragraphs}
