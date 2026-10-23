import { useState } from 'react'
import { date, money } from '../format.js'

export default function DailyProjectionDetails({ chartDays, analysisDays = chartDays, referenceDate, assumptionDetails = {} }) {
  const [showAnalysis, setShowAnalysis] = useState(false)
  const days = showAnalysis ? analysisDays : chartDays
  const extended = analysisDays.length > chartDays.length
  return <details className="daily-details">
    <summary>Ver movimentações e valores por dia</summary>
    <div className="projection-detail-intro">
      <p>Referência: <strong>{date(referenceDate || chartDays[0].date)}</strong>. Período desta tabela: <strong>{date(days[0].date)} a {date(days.at(-1).date)}</strong>, inclusive.</p>
      <p>Na referência, a abertura é o saldo atual, já incluindo as movimentações realizadas até essa data. Nos demais dias, é o fechamento projetado do dia anterior.</p>
      <p>Saídas antes de entradas no mesmo dia, com desempate por identificador. Essa ordem é uma premissa da simulação; não representa horários bancários nem prioridade de pagamento.</p>
      {extended && <label className="essential-choice"><input type="checkbox" checked={showAnalysis} onChange={(event) => setShowAnalysis(event.target.checked)} />Mostrar os {analysisDays.length} dias da análise completa, incluindo os dias além do gráfico</label>}
    </div>
    <div className="table-scroll"><table className="projection-details-table">
      <caption>Projeção diária de {date(days[0].date)} a {date(days.at(-1).date)}. Valores em reais; eventos considerados na ordem exibida.</caption>
      <thead><tr>{['Data', 'Abertura', 'Entradas previstas', 'Saídas previstas', 'Menor saldo', 'Fechamento', 'Eventos e premissas'].map((heading) => <th scope="col" key={heading}>{heading}</th>)}</tr></thead>
      <tbody>{days.map((day) => <tr key={day.date}>
        <th scope="row">{date(day.date)}</th><td>{money(day.opening_balance)}</td><td>{money(day.income)}</td><td>{money(day.expenses)}</td>
        <td className={Number(day.minimum_balance) < 0 ? 'negative' : ''}>{money(day.minimum_balance)}{Number(day.minimum_balance) < 0 && <span className="overdue-label">Insuficiência durante a sequência</span>}</td>
        <td>{money(day.closing_balance)}</td>
        <td><details className="day-events"><summary>{day.events?.length ? `${day.events.length} evento(s) · ver sequência` : 'Sem eventos · ver premissas'}</summary>
          {day.events?.length > 0 && <ol>{day.events.map((event) => <li key={event.occurrence_id}>
            <strong>{event.description}</strong> · {event.direction === 'income' ? 'Entrada prevista' : event.is_estimate ? 'Estimativa de saída' : 'Saída prevista'}: {money(event.amount)}
            <p>Data original: {date(event.original_date)}. Considerado em {date(event.effective_date)}.</p>
            {event.is_recurring && <p>Ocorrência mensal · competência {date(event.competence).slice(3)}. A configuração não é somada novamente.</p>}
            <p>Saldo após a etapa {event.sequence}: <strong>{money(event.balance_after)}</strong>.</p>
          </li>)}</ol>}
          <h4>Premissas deste dia</h4><ul>{(day.assumption_codes || []).map((code) => <li key={code}>{assumptionDetails[code] || code}</li>)}</ul>
        </details></td>
      </tr>)}</tbody>
    </table></div>
  </details>
}
