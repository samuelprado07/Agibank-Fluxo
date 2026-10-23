import IndicatorCard from './IndicatorCard.jsx'
import ProjectionChart from './ProjectionChart.jsx'
import { date, money, shortDate } from '../format.js'
import { Icon } from './Navigation.jsx'

export default function Dashboard({ data }) {
  const { indicators: v, next_income: income, period } = data
  const interval = `${date(period.start)} a ${date(period.end)}`
  const upcoming = data.chart_days.flatMap((day) => day.events || [])
  return <>
    <section className="balance-hero" aria-labelledby="greeting">
      <div className="hero-heading"><div><p className="eyebrow">MEU PLANEJAMENTO</p><h1 id="greeting">Olá, Samuel</h1></div><span className="fluxo-badge">FLUXO</span></div>
      <div className="balance-block"><p>Saldo atual</p><strong className={Number(v.current_balance) < 0 ? 'negative' : ''}>{money(v.current_balance)}</strong><span>Entradas e saídas realizadas até {date(data.reference_date)}</span></div>
    </section>
    <nav className="quick-actions" aria-label="Atalhos do planejamento">{[['expenses', 'Despesas'], ['incomes', 'Renda prevista'], ['recurrences', 'Recorrências'], ['simulations', 'Simular']].map(([key, label]) => <a key={key} href={`#${key}`}><Icon name={key} /><span>{label}</span></a>)}</nav>
    <ProjectionChart days={data.chart_days} analysisDays={data.days} referenceDate={data.reference_date} assumptionDetails={data.assumption_details} alerts={data.alerts} period={period} />
    <section className="panel upcoming-panel" aria-labelledby="upcoming-title"><div className="panel-heading"><h2 id="upcoming-title">Próximos dias</h2><span className="muted">{shortDate(data.chart_days[0].date)} a {shortDate(data.chart_days.at(-1).date)}</span></div><p className="muted">Entradas e saídas previstas, incluindo vencidas consideradas imediatas.</p>{upcoming.length ? <ul className="upcoming-list">{upcoming.map((event, index) => <li key={`${event.occurrence_id}-${index}`}><div><strong>{event.description}</strong><small>{date(event.effective_date)} · {event.direction === 'income' ? 'Entrada prevista' : event.is_estimate ? 'Estimativa de saída' : 'Saída prevista'}</small></div><b className={event.direction === 'income' ? 'income-value' : 'expense-value'}>{event.direction === 'income' ? '+' : '−'} {money(event.amount)}</b></li>)}</ul> : <p className="muted">Nenhuma movimentação prevista nestes 15 dias.</p>}</section>
    {data.overdue_incomes?.length > 0 && <section className="panel overdue-incomes" aria-labelledby="overdue-incomes-title"><div className="panel-heading"><h2 id="overdue-incomes-title">Recebimentos atrasados</h2><a href="#incomes" className="text-button">Conferir renda</a></div><p className="muted">Ainda não confirmados em {date(data.reference_date)}. Não compõem o saldo, a projeção nem o próximo recebimento.</p><ul>{data.overdue_incomes.map((item) => <li key={item.id}><strong>{item.description}</strong> · {money(item.amount)} · esperado em {date(item.date)}</li>)}</ul></section>}
    <div className="overview-bottom">
      <section className="summary-section" aria-labelledby="summary-title"><div className="section-heading"><div><p className="eyebrow">CADA COMPROMISSO CONTA</p><h2 id="summary-title">Seu planejamento em detalhes</h2></div><span>{interval}</span></div>
        <div className="indicators-grid">
          <IndicatorCard label="Próximo recebimento" value={income ? money(income.amount) : 'Não informado'} period={income ? `Previsto para ${date(income.date)}` : `Busca de ${interval}`} note={income ? `${income.description} · Ainda estimado` : 'Sem entrada prevista válida no horizonte.'} />
          {data.next_incomes?.slice(1).map((item, index) => <IndicatorCard key={`${item.description}-${index}`} label="Outro recebimento na mesma data" value={money(item.amount)} period={`Previsto para ${date(item.date)}`} note={`${item.description} · Ainda estimado`} />)}
          <IndicatorCard label="Essenciais pendentes" value={money(v.pending_essential)} period={`${interval}, incluindo vencidas`} note="Compromissos essenciais ainda não pagos." />
          <IndicatorCard label="Saldo projetado final" value={money(v.projected_final)} period={`Ao final de ${date(period.end)}`} note="Considera entradas previstas e saídas cadastradas." negative={Number(v.projected_final) < 0} />
        </div>
      </section>
    </div>
  </>
}
