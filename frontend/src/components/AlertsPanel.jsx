import { date, money } from '../format.js'
import { useId } from 'react'

function DeficitStatus({ alert, period }) {
  if (alert.ongoing) return <p className="alert-footnote">O déficit permanece até {date(alert.analysis_end || period.end)}, limite desta análise.</p>
  return <>
    <p className="alert-footnote">{alert.end_reason === 'zero_margin'
      ? `Saída do déficit estimada em ${date(alert.recovery_date)}, com saldo zero. Ainda sem margem nesse ponto.`
      : `Saída do déficit e saldo positivo estimados em ${date(alert.recovery_date)}${alert.recovery_balance !== undefined ? `, com saldo de ${money(alert.recovery_balance)} após a entrada considerada` : ''}.`}</p>
    {alert.end_reason === 'zero_margin' && alert.margin_recovery_date && <p className="alert-footnote">Saldo positivo estimado posteriormente, em {date(alert.margin_recovery_date)}{alert.margin_recovery_income ? `, condicionado ao recebimento previsto de ${money(alert.margin_recovery_income.amount)}` : ''}.</p>}
  </>
}

function RelevantIncome({ income }) {
  if (!income) return <p className="alert-footnote">Nenhuma próxima entrada prevista elegível na busca de até 60 dias a partir da referência.</p>
  if (income.outside_analysis) return <p className="alert-footnote">Entrada prevista após o período analisado: {income.description}, {money(income.amount)} em {date(income.date)}. Não foi usada para projetar recuperação neste período.</p>
  return <p className="alert-footnote">Próxima entrada prevista relevante: {income.description}, {money(income.amount)} em {date(income.date)}, ainda estimada. {income.role === 'partial_reduction' ? 'Ela reduz o déficit, mas não o cobre integralmente nesse ponto.' : income.role === 'closes_deficit' ? 'Na sequência calculada, essa entrada permite sair do déficit.' : 'A indicação da próxima entrada não significa cobertura integral dos compromissos.'}</p>
}

export default function AlertsPanel({ alerts, period, referenceDate, assumptionDetails = {} }) {
  const titleId = useId()
  return <section className="panel alerts-panel" aria-labelledby={titleId}>
    <div className="panel-heading"><div><p className="eyebrow">ATENÇÃO ANTECIPADA</p><h2 id={titleId}>Pontos para acompanhar</h2></div><span className="count-tag">{alerts.length}</span></div>
    <p className="muted">Referência: {date(referenceDate || period.start)}. Análise de {date(period.start)} a {date(period.end)}, inclusive. Alertas exibidos somente nesta aplicação.</p>
    {!alerts.length && <p className="empty-alert">Nenhuma insuficiência ou ausência de margem identificada nos dados e no período considerados.</p>}
    {alerts.map((a, i) => <article key={a.id || `${a.type}-${a.date}-${i}`} className={`alert-card ${a.type}`}>
      <p className="alert-date">{date(a.date)}{a.outside_chart && <span className="outside-label">Além do gráfico de 15 dias</span>}</p>
      <h3>{a.type === 'insufficient' ? 'Possível insuficiência de saldo' : 'Ausência de margem'}</h3>
      {a.type === 'insufficient' ? <>
        <p>Maior falta estimada na primeira data: <strong>{money(a.first_day_shortfall ?? a.first_shortfall)}</strong>. No primeiro ponto negativo da sequência, a insuficiência é de {money(a.first_shortfall)}.</p>
        <p>A maior insuficiência estimada no episódio é de <strong>{money(a.max_shortfall)}</strong>{a.max_shortfall_date ? ` em ${date(a.max_shortfall_date)}` : ''}.</p>
        {a.starts_with_deficit && <p className="alert-footnote">O episódio começa com o saldo atual já negativo na referência.</p>}
        {a.expenses.length > 0 && <details><summary>Compromissos do intervalo</summary><ul>{a.expenses.map((e) => <li key={e.id}>{e.description} — {money(e.amount)} <span className="muted">({e.is_estimate ? 'estimativa para' : 'vencimento'} {date(e.due_date)})</span></li>)}</ul></details>}
        {!a.expenses.length && <p className="alert-footnote">Sem novos compromissos previstos nas datas deste episódio. A insuficiência pode partir do saldo inicial da projeção.</p>}
        <DeficitStatus alert={a} period={period} />
        {a.income_dependency && <div className="alert-dependency"><p>{a.income_dependency.recovery_relies_on_estimates
          ? 'A saída do déficit calculada depende das entradas previstas abaixo ocorrerem nos valores e datas informados.'
          : a.income_dependency.reduction_relies_on_estimates ? 'Há redução condicionada a entradas previstas, mas não há saída do déficit dentro do período analisado.'
            : 'Nenhuma entrada prevista reduz este déficit dentro do intervalo calculado.'}</p>
          <p className="alert-footnote">Este critério avalia a redução e a saída do déficit observado. Não é uma comparação com um cenário sem renda.</p>
          {a.recovery_incomes?.length > 0 && <details><summary>Entradas previstas que contribuem no episódio</summary><ul>{a.recovery_incomes.map((income) => <li key={income.id}>{income.description} — {money(income.amount)} em {date(income.date)}. {income.role === 'partial_reduction' ? `Redução parcial; ainda poderão faltar ${money(income.remaining_shortfall)} após essa entrada.` : 'Permite sair do déficit na sequência calculada.'} Recebimento ainda não confirmado.</li>)}</ul></details>}
        </div>}
      </> : <p>O saldo calculado chega a zero na sequência de eventos. Não há margem para despesas adicionais nesse momento.</p>}
      <RelevantIncome income={a.next_income} />
      <details className="alert-assumptions"><summary>Como este alerta foi calculado</summary><ul>{(a.assumption_codes || []).map((code) => <li key={code}>{assumptionDetails[code] || code}</li>)}</ul><p className="alert-footnote">Previsões não garantem disponibilidade. Gastos ausentes e alterações nos dados podem mudar o resultado.</p></details>
      {a.type === 'insufficient' && <p className="alert-footnote">Resultado conjunto dos compromissos; não determina qual despesa deve deixar de ser paga.</p>}
    </article>)}
  </section>
}
