import { date, money, shortDate } from '../format.js'

export default function ProjectionChart({ days }) {
  const values = days.flatMap((d) => [Number(d.closing_balance), Number(d.minimum_balance)])
  const low = Math.min(0, ...values), high = Math.max(100, ...values), padding = (high - low) * .12
  const min = low - padding, max = high + padding
  const x = (i) => 100 + i * 670 / Math.max(1, days.length - 1)
  const y = (v) => 225 - (Number(v) - min) / (max - min) * 197
  const line = days.map((d, i) => `${x(i)},${y(d.closing_balance)}`).join(' ')
  return <section className="panel chart-panel" aria-labelledby="projection-title">
    <div className="panel-heading"><div><p className="eyebrow">PRÓXIMOS 15 DIAS</p><h2 id="projection-title">Seu saldo, dia a dia</h2></div><span className="period-tag">{shortDate(days[0].date)} — {shortDate(days.at(-1).date)}</span></div>
    <p className="muted">Saldo no fechamento de cada dia. Os marcadores indicam o menor saldo na sequência diária.</p>
    <div className="chart-scroll"><svg viewBox="0 0 800 280" role="img" aria-labelledby="chart-title chart-description">
      <title id="chart-title">Projeção diária de saldo</title><desc id="chart-description">De {date(days[0].date)} a {date(days.at(-1).date)}. A linha pontilhada representa saldo zero. Consulte os valores na tabela abaixo.</desc>
      {[0, high, ...(low < 0 ? [low] : [])].map((tick) => <g key={tick}><line x1="100" x2="770" y1={y(tick)} y2={y(tick)} className={tick === 0 ? 'zero-line' : 'grid-line'} /><text x="88" y={y(tick) + 4} textAnchor="end" className="axis-text">{money(tick)}</text></g>)}
      <polygon points={`${x(0)},${y(0)} ${line} ${x(days.length - 1)},${y(0)}`} fill="#e1eee7" opacity=".6" />
      <polyline points={line} fill="none" stroke="#276749" strokeWidth="3" strokeLinejoin="round" />
      {days.map((d, i) => <g key={d.date}><circle cx={x(i)} cy={y(d.closing_balance)} r="3.5" fill="#276749"><title>{date(d.date)}: fechamento {money(d.closing_balance)}</title></circle>
        {Number(d.minimum_balance) <= 0 && <path d={`M ${x(i)} ${y(d.minimum_balance) - 6} l 6 6 l -6 6 l -6 -6 Z`} fill={Number(d.minimum_balance) < 0 ? '#b13f32' : '#93610f'}><title>{date(d.date)}: menor saldo {money(d.minimum_balance)}</title></path>}
        {(i % 3 === 0 || i === days.length - 1) && <text x={x(i)} y="255" textAnchor="middle" className="axis-text">{shortDate(d.date)}</text>}
      </g>)}
    </svg></div>
    <div className="chart-legend"><span>━ Saldo de fechamento</span><span>◆ Insuficiência ou ausência de margem</span></div>
    <details className="daily-details"><summary>Consultar valores por dia</summary><div className="table-scroll"><table>
      <caption>Valores projetados nos 15 dias do gráfico</caption><thead><tr>{['Data', 'Entradas', 'Saídas', 'Menor saldo', 'Fechamento'].map((h) => <th scope="col" key={h}>{h}</th>)}</tr></thead>
      <tbody>{days.map((d) => <tr key={d.date}><th scope="row">{date(d.date)}</th><td>{money(d.income)}</td><td>{money(d.expenses)}</td><td>{money(d.minimum_balance)}</td><td>{money(d.closing_balance)}</td></tr>)}</tbody>
    </table></div></details>
  </section>
}
