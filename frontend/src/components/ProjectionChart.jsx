import { useState } from 'react'
import { date, money, shortDate } from '../format.js'
import DailyProjectionDetails from './DailyProjectionDetails.jsx'

export default function ProjectionChart({ days, analysisDays, referenceDate, assumptionDetails }) {
  const [selected, setSelected] = useState(null)
  const values = days.flatMap((day) => [Number(day.closing_balance), Number(day.minimum_balance)])
  const low = Math.min(0, ...values), high = Math.max(100, ...values)
  const padding = (high - low) * .22
  const min = low - padding * .3, max = high + padding
  const width = 1100, left = 90, right = 50, baseline = 284
  const x = (index) => left + index * (width - left - right) / Math.max(1, days.length - 1)
  const y = (value) => baseline - (Number(value) - min) / (max - min) * 240
  const line = days.map((day, index) => `${x(index)},${y(day.closing_balance)}`).join(' ')
  const ticks = [...new Set([0, Math.round(high / 2), high, ...(low < 0 ? [low] : [])])]
  const active = selected === null ? null : days[selected]

  return <section className="panel chart-panel" aria-labelledby="projection-title">
    <div className="panel-heading"><div><p className="eyebrow">UM OLHAR ADIANTE</p><h2 id="projection-title">Evolução do seu saldo</h2></div><span className="period-tag"><span className="calendar-icon" aria-hidden="true">▦</span> {shortDate(days[0].date)} a {shortDate(days.at(-1).date)} <i /> 15 dias</span></div>
    <div className="chart-description"><p>Projeção diária a partir das entradas, despesas e estimativas cadastradas.</p><span><i /> Saldo previsto</span></div>
    <p className="projection-reference">Referência: {date(referenceDate || days[0].date)}. A projeção parte do saldo atual, com realizações dessa data já incluídas.</p>
    <p className="chart-selected" role="status">{active ? <>{date(active.date)} · Fechamento <strong>{money(active.closing_balance)}</strong> · Menor saldo {money(active.minimum_balance)}</> : '\u00a0'}</p>
    <div className="chart-scroll" tabIndex="0" aria-label="Gráfico com rolagem horizontal e valores por dia"><svg viewBox={`0 0 ${width} 340`} role="img" aria-labelledby="chart-title chart-description">
      <title id="chart-title">Saldo previsto nos próximos 15 dias</title><desc id="chart-description">Valores de fechamento visíveis em cada ponto. De {date(days[0].date)} a {date(days.at(-1).date)}. Marcadores em losango indicam ausência de margem ou insuficiência. Tabela detalhada abaixo.</desc>
      <defs><linearGradient id="balance-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4b7fde" stopOpacity=".16" /><stop offset="100%" stopColor="#4b7fde" stopOpacity=".01" /></linearGradient></defs>
      {ticks.map((tick) => <g key={tick}><line x1={left} x2={width - right} y1={y(tick)} y2={y(tick)} className={tick === 0 ? 'zero-line' : 'grid-line'} /><text x={left - 18} y={y(tick) + 4} textAnchor="end" className="axis-text">{money(tick)}</text></g>)}
      <polygon points={`${x(0)},${y(0)} ${line} ${x(days.length - 1)},${y(0)}`} fill="url(#balance-fill)" />
      <polyline points={line} fill="none" stroke="#3266be" strokeWidth="3" strokeLinejoin="round" />
      {days.map((day, index) => <g key={day.date}>
        <text x={x(index)} y={y(day.closing_balance) - (index % 2 === 0 ? 17 : 37)} textAnchor="middle" className={`point-value ${Number(day.closing_balance) < 0 ? 'negative-value' : ''}`}>{money(day.closing_balance)}</text>
        <circle cx={x(index)} cy={y(day.closing_balance)} r={selected === index ? 6 : 4.5} fill="white" stroke="#3266be" strokeWidth="2.5" tabIndex="0" aria-label={`${date(day.date)}: saldo ${money(day.closing_balance)}`} onMouseEnter={() => setSelected(index)} onMouseLeave={() => setSelected(null)} onFocus={() => setSelected(index)} onBlur={() => setSelected(null)}><title>{date(day.date)}: {money(day.closing_balance)}</title></circle>
        {Number(day.minimum_balance) <= 0 && <path d={`M ${x(index)} ${y(day.minimum_balance) - 6} l 6 6 l -6 6 l -6 -6 Z`} fill={Number(day.minimum_balance) < 0 ? '#b8413b' : '#9c701c'}><title>Menor saldo em {date(day.date)}: {money(day.minimum_balance)}</title></path>}
        <text x={x(index)} y="321" textAnchor="middle" className="axis-text">{shortDate(day.date)}</text>
      </g>)}
    </svg></div>
    <div className="chart-footnote"><span>◆ Marcadores indicam insuficiência ou ausência de margem.</span><span>Valores sujeitos às entradas e saídas previstas.</span></div>
    <DailyProjectionDetails chartDays={days} analysisDays={analysisDays} referenceDate={referenceDate} assumptionDetails={assumptionDetails} />
  </section>
}
