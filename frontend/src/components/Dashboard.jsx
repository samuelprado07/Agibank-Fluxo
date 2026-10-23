import IndicatorCard from './IndicatorCard.jsx'
import ProjectionChart from './ProjectionChart.jsx'
import AlertsPanel from './AlertsPanel.jsx'
import AssumptionsPanel from './AssumptionsPanel.jsx'
import { date, money } from '../format.js'

export default function Dashboard({ data }) {
  const { indicators: v, next_income: income, period } = data
  const interval = `${date(period.start)} a ${date(period.end)}`
  const committedPeriod = income ? `Até ${date(income.date)}, inclusive` : 'Próxima renda não informada neste horizonte'
  return <>
    <section className="balance-hero" aria-labelledby="greeting">
      <div><p className="eyebrow">BOM TER VOCÊ POR AQUI</p><h1 id="greeting">Olá, Samuel<span>.</span></h1><p className="hero-description">Vamos olhar para os seus próximos dias?</p></div>
      <div className="balance-block"><p>Saldo atual</p><strong className={Number(v.current_balance) < 0 ? 'negative' : ''}>{money(v.current_balance)}</strong><span>Entradas e saídas realizadas até {date(data.reference_date)}</span></div>
    </section>
    <ProjectionChart days={data.chart_days} analysisDays={data.days} referenceDate={data.reference_date} assumptionDetails={data.assumption_details} />
    {data.overdue_incomes?.length > 0 && <section className="panel overdue-incomes" aria-labelledby="overdue-incomes-title"><div className="panel-heading"><h2 id="overdue-incomes-title">Recebimentos atrasados</h2><a href="#incomes" className="text-button">Conferir renda</a></div><p className="muted">Ainda não confirmados em {date(data.reference_date)}. Não compõem o saldo, a projeção nem o próximo recebimento.</p><ul>{data.overdue_incomes.map((item) => <li key={item.id}><strong>{item.description}</strong> · {money(item.amount)} · esperado em {date(item.date)}</li>)}</ul></section>}
    <div className="overview-bottom">
      <section className="summary-section" aria-labelledby="summary-title"><div className="section-heading"><div><p className="eyebrow">CADA COMPROMISSO CONTA</p><h2 id="summary-title">Seu planejamento em detalhes</h2></div><span>{interval}</span></div>
        <div className="indicators-grid">
          <IndicatorCard label="Próximo recebimento" value={income ? money(income.amount) : 'Não informado'} period={income ? `Previsto para ${date(income.date)}` : `Busca de ${interval}`} note={income ? `${income.description} · Ainda estimado` : 'Sem entrada prevista válida no horizonte.'} />
          {data.next_incomes?.slice(1).map((item, index) => <IndicatorCard key={`${item.description}-${index}`} label="Outro recebimento na mesma data" value={money(item.amount)} period={`Previsto para ${date(item.date)}`} note={`${item.description} · Ainda estimado`} />)}
          <IndicatorCard label="Essenciais pendentes" value={money(v.pending_essential)} period={`${interval}, incluindo vencidas`} note="Compromissos essenciais ainda não pagos." />
          <IndicatorCard label="Valor comprometido" value={money(v.committed)} period={committedPeriod} note="Todas as despesas pendentes e estimativas, essenciais ou não. Não bloqueia dinheiro." />
          <IndicatorCard label="Saldo próprio restante" value={money(v.own_remaining)} period={income ? `Após compromissos até ${date(income.date)}` : committedPeriod} note="Sem incluir rendas futuras ou limite de crédito." negative={v.own_remaining !== null && Number(v.own_remaining) < 0} />
          <IndicatorCard label="Saldo projetado final" value={money(v.projected_final)} period={`Ao final de ${date(period.end)}`} note="Considera entradas previstas e saídas cadastradas." negative={Number(v.projected_final) < 0} />
        </div>
      </section>
      <AlertsPanel alerts={data.alerts} period={period} referenceDate={data.reference_date} assumptionDetails={data.assumption_details} />
    </div>
    <AssumptionsPanel assumptions={data.assumptions} warnings={data.warnings} />
  </>
}
