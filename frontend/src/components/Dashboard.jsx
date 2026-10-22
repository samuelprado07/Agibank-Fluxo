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
    <div className="dashboard-intro"><div><p className="eyebrow">SEU PLANEJAMENTO FINANCEIRO</p><h1>Um olhar para o que vem pela frente.</h1><p className="intro">Entenda seus compromissos hoje e antecipe os próximos passos.</p></div><div className="reference-box"><span>Data de referência</span><strong>{date(data.reference_date)}</strong><small>Cenário fixo demonstrativo</small></div></div>
    <div className="scenario-strip"><span className="demo-dot" /><span>{data.scenario.name}</span><span className="scenario-period">Período analisado: {interval}</span></div>
    <section className="indicators-grid" aria-label="Resumo financeiro por período">
      <IndicatorCard label="Saldo atual" value={money(v.current_balance)} period={`Realizados de ${date(data.scenario.opening_date)} até ${date(data.reference_date)}`} note="Recursos próprios. Não inclui limite de crédito." emphasis />
      <IndicatorCard label="Próximo recebimento previsto" value={income ? money(income.amount) : 'Não informado'} period={income ? `Previsto para ${date(income.date)}` : `Busca no período ${interval}`} note={income ? `${income.description} · Estimado, ainda não recebido` : 'Sem entrada prevista válida no horizonte analisado.'} />
      <IndicatorCard label="Despesas essenciais pendentes" value={money(v.pending_essential)} period={`${interval}, incluindo vencidas`} note="Ocorrências essenciais ainda não pagas." />
      <IndicatorCard label="Valor comprometido antes da renda" value={money(v.committed)} period={committedPeriod} note={income ? 'Essenciais pendentes. Não bloqueia dinheiro.' : `Compromissos no período analisado: ${money(v.pending_essential)}.`} />
      <IndicatorCard label="Saldo próprio restante" value={money(v.own_remaining)} period={income ? `Após compromissos até ${date(income.date)}` : committedPeriod} note="Saldo atual menos compromissos. Sem rendas futuras." negative={v.own_remaining !== null && Number(v.own_remaining) < 0} />
      <IndicatorCard label="Saldo projetado final" value={money(v.projected_final)} period={`Ao final de ${date(period.end)}`} note="Inclui entradas estimadas e saídas consideradas." negative={Number(v.projected_final) < 0} />
    </section>
    <div className="analysis-grid"><ProjectionChart days={data.chart_days} /><AlertsPanel alerts={data.alerts} period={period} /></div>
    <AssumptionsPanel assumptions={data.assumptions} warnings={data.warnings} />
  </>
}
