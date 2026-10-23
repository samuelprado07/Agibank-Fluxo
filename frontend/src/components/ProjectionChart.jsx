import { useId, useState } from 'react'
import { date, money, shortDate } from '../format.js'
import ChartAlertDialog from './ChartAlertDialog.jsx'

const compactMoney = (value) => new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 }).format(value)

export default function ProjectionChart({ days, analysisDays, referenceDate, alerts = [] }) {
  const id = useId()
  const [selected, setSelected] = useState(0)
  const [alertSelection, setAlertSelection] = useState(null)
  const index = Math.min(selected, days.length - 1)
  const active = days[index]
  const values = days.flatMap((day) => [Number(day.closing_balance), Number(day.minimum_balance)])
  const low = Math.min(0, ...values), high = Math.max(100, ...values)
  const range = high - low
  const min = low - range * .12, max = high + range * .2

  function openAlert(day, dayIndex) {
    setSelected(dayIndex)
    const points = [{ sequence: 0, balance: day.opening_balance }, ...(day.events || []).map((event) => ({ sequence: event.sequence, balance: event.balance_after }))]
    const sequences = points.filter((point) => Number(point.balance) === Number(day.minimum_balance)).map((point) => point.sequence)
    const matching = alerts.filter((alert) => alert.type === 'insufficient' && alert.date <= day.date && (alert.end_date || day.date) >= day.date && sequences.some((sequence) => (alert.date < day.date || sequence >= alert.start_sequence) && ((alert.end_date || day.date) > day.date || sequence <= alert.end_sequence)))
    if (matching.length) {
      const expenses = (analysisDays || days).filter((item) => item.date <= day.date).flatMap((item) => (item.events || []).filter((event) => event.direction === 'expense' && Number(event.balance_after) < 0 && matching.some((alert) => item.date >= alert.date && item.date <= alert.end_date && (item.date !== alert.date || event.sequence >= alert.start_sequence) && (item.date !== alert.end_date || event.sequence <= alert.end_sequence))))
      setAlertSelection({ expenses, date: day.date, minimumBalance: day.minimum_balance })
    }
  }

  function graph(compact) {
    const width = compact ? 380 : 1100, height = compact ? 340 : 410
    const left = compact ? 48 : 100, right = compact ? 22 : 55, top = 94, bottom = height - 38
    const x = (i) => left + i * (width - left - right) / Math.max(1, days.length - 1)
    const y = (value) => bottom - (Number(value) - min) / (max - min) * (bottom - top)
    const line = days.map((day, i) => `${x(i)},${y(day.closing_balance)}`).join(' ')
    const ticks = [...new Set([0, high / 2, high, ...(low < -range * .12 ? [low] : [])])].sort((a, b) => a - b)
    const suffix = compact ? 'mobile' : 'desktop'
    const fillId = `${id}-${suffix}-fill`
    const tooltipX = Math.max(left, Math.min(width - right - 190, x(index) - 95))
    return <svg viewBox={`0 0 ${width} ${height}`} role="group" aria-label={`Saldo de fechamento de ${date(days[0].date)} a ${date(days.at(-1).date)}. Selecione um dia para consultar os valores.`}>
      <defs><linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#1b3dc1" stopOpacity=".18" /><stop offset="100%" stopColor="#1b3dc1" stopOpacity=".02" /></linearGradient></defs>
      {low < 0 && <rect x={left} y={y(0)} width={width - left - right} height={bottom - y(0)} fill="#fff1ef" />}
      {ticks.map((tick) => <g key={tick}><line x1={left} x2={width - right} y1={y(tick)} y2={y(tick)} className={tick === 0 ? 'zero-line' : 'grid-line'} /><text x={left - 9} y={y(tick) + 4} textAnchor="end" className="axis-text">{compact ? compactMoney(tick) : money(tick)}</text></g>)}
      <text x={left - 9} y="82" textAnchor="end" className="axis-text">R$</text>
      <polygon points={`${x(0)},${y(0)} ${line} ${x(days.length - 1)},${y(0)}`} fill={`url(#${fillId})`} />
      <polyline points={line} fill="none" stroke="#1b3dc1" strokeWidth={compact ? 2.8 : 3} strokeLinejoin="round" strokeLinecap="round" />
      <line x1={x(index)} x2={x(index)} y1={top} y2={bottom} className="chart-cursor" />
      {days.map((day, i) => <g key={day.date}>
        {!compact && <text x={x(i)} y={y(day.closing_balance) - (i % 2 ? 32 : 15)} textAnchor="middle" className={`point-value ${Number(day.closing_balance) < 0 ? 'negative-value' : ''}`}>{money(day.closing_balance)}</text>}
        <circle cx={x(i)} cy={y(day.closing_balance)} r={i === index ? 5.5 : 3} fill={i === index ? '#1b3dc1' : '#fff'} stroke="#1b3dc1" strokeWidth="2" />
        {Number(day.minimum_balance) <= 0 && <path d={`M ${x(i)} ${y(day.minimum_balance) - 5} l 5 5 l -5 5 l -5 -5 Z`} fill={Number(day.minimum_balance) < 0 ? '#b3261e' : '#9c701c'}><title>Menor saldo: {money(day.minimum_balance)}</title></path>}
        {(!compact || [0, Math.floor(days.length / 2), days.length - 1].includes(i)) && <text x={x(i)} y={height - 10} textAnchor="middle" className="axis-text">{shortDate(day.date)}</text>}
        <rect x={x(i) - (width - left - right) / Math.max(1, days.length - 1) / 2} y={top} width={(width - left - right) / Math.max(1, days.length - 1)} height={bottom - top} fill="transparent" className="chart-hit" role="button" tabIndex={i === index ? 0 : -1} aria-pressed={i === index} aria-label={`${date(day.date)}: fechamento ${money(day.closing_balance)}, menor saldo ${money(day.minimum_balance)}`} onClick={() => setSelected(i)} onFocus={() => setSelected(i)} onPointerEnter={(event) => { if (event.pointerType === 'mouse') setSelected(i) }} onKeyDown={(event) => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); setSelected(i) } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); setSelected((current) => Math.max(0, Math.min(days.length - 1, current + (event.key === 'ArrowRight' ? 1 : -1)))) } }} />
      </g>)}
      {days.map((day, i) => Number(day.minimum_balance) < 0 && <g key={`alert-${day.date}`} role="button" tabIndex="0" aria-label={`Abrir alerta de insuficiência de ${date(day.date)}`} onClick={() => openAlert(day, i)} onKeyDown={(event) => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); openAlert(day, i) } }} className="chart-alert-marker">
        <circle cx={x(i)} cy={y(day.minimum_balance)} r={compact ? 13 : 11} fill="transparent" />
        <path d={`M ${x(i)} ${y(day.minimum_balance) - 6} l 6 6 l -6 6 l -6 -6 Z`} fill="#b3261e" stroke="white" strokeWidth="1.5" />
      </g>)}
      <g className="chart-tooltip" transform={`translate(${tooltipX}, 8)`} pointerEvents="none">
        <rect width="190" height="66" rx="9" fill="white" stroke={Number(active.minimum_balance) < 0 ? '#edc8c3' : '#dce3f7'} />
        <text x="12" y="17" className="tooltip-date">{shortDate(active.date)} · fechamento</text>
        <text x="12" y="37" className="tooltip-value">{money(active.closing_balance)}</text>
        <text x="12" y="55" className={Number(active.minimum_balance) < 0 ? 'tooltip-risk' : 'tooltip-minimum'}>Menor saldo: {money(active.minimum_balance)}</text>
      </g>
    </svg>
  }

  return <section className="panel chart-panel" aria-labelledby={`${id}-title`}>
    <div className="panel-heading"><div><p className="eyebrow">UM OLHAR ADIANTE</p><h2 id={`${id}-title`}>Evolução do seu saldo</h2><p className="chart-period">{shortDate(days[0].date)} a {shortDate(days.at(-1).date)} · fechamento diário</p></div><span className="period-tag">{days.length} dias</span></div>
    <div className="mobile-chart">{graph(true)}</div>
    <div className="chart-scroll">{graph(false)}</div>
    <p className="chart-interaction-hint" role="status">{date(active.date)} · Fechamento {money(active.closing_balance)} · Menor saldo {money(active.minimum_balance)}. Toque nos pontos para explorar.</p>
    <div className="chart-legend"><span><i /> Saldo de fechamento</span><span><b>◆</b> Menor saldo sem margem ou negativo</span></div>
    <p className="projection-reference">Referência: {date(referenceDate || days[0].date)}. Realizações até essa data já estão no saldo atual. Projeção condicionada às entradas e saídas previstas; o fechamento positivo não elimina uma insuficiência durante o dia.</p>
    {alertSelection && <ChartAlertDialog selection={alertSelection} onClose={() => setAlertSelection(null)} />}
  </section>
}
