import { date, money } from '../format.js'

export default function AlertsPanel({ alerts, period }) {
  return <section className="panel alerts-panel" aria-labelledby="alerts-title">
    <div className="panel-heading"><div><p className="eyebrow">ATENÇÃO ANTECIPADA</p><h2 id="alerts-title">Pontos para acompanhar</h2></div><span className="count-tag">{alerts.length}</span></div>
    <p className="muted">Análise de {date(period.start)} a {date(period.end)}.</p>
    {!alerts.length && <p className="empty-alert">Nenhuma insuficiência ou ausência de margem identificada nos dados e no período considerados.</p>}
    {alerts.map((a, i) => <article key={`${a.type}-${a.date}-${i}`} className={`alert-card ${a.type}`}>
      <p className="alert-date">{date(a.date)}{a.outside_chart && <span className="outside-label">Além do gráfico de 15 dias</span>}</p>
      <h3>{a.type === 'insufficient' ? 'Possível insuficiência de saldo' : 'Saldo sem margem'}</h3>
      {a.type === 'insufficient' ? <>
        <p>Poderão faltar <strong>{money(a.first_shortfall)}</strong> nesta data. A maior necessidade estimada neste intervalo é de <strong>{money(a.max_shortfall)}</strong>.</p>
        {a.expenses.length > 0 && <details><summary>Compromissos do intervalo</summary><ul>{a.expenses.map((e) => <li key={e.id}>{e.description} — {money(e.amount)} <span className="muted">({e.is_estimate ? 'estimativa para' : 'vencimento'} {date(e.due_date)})</span></li>)}</ul></details>}
        <p className="alert-footnote">{a.ongoing ? 'O déficit permanece até o limite analisado.' : `Recuperação estimada em ${date(a.recovery_date)}.`}</p>
      </> : <p>O saldo calculado chega a zero na sequência de eventos. Não há margem para despesas adicionais nesse momento.</p>}
      <p className="alert-footnote">{a.next_income ? `Próxima entrada relevante: ${money(a.next_income.amount)} em ${date(a.next_income.date)}, ainda estimada.` : 'Sem próximo recebimento previsto relevante neste horizonte.'}</p>
      {a.type === 'insufficient' && <p className="alert-footnote">Resultado conjunto dos compromissos; não determina qual despesa deve deixar de ser paga.</p>}
    </article>)}
  </section>
}
