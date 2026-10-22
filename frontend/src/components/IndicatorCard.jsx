export default function IndicatorCard({ label, value, period, note, emphasis = false, negative = false }) {
  return <article className={`indicator ${emphasis ? 'indicator-primary' : ''}`}>
    <h2>{label}</h2><p className={`indicator-value ${negative ? 'negative' : ''}`}>{value}</p>
    <p className="indicator-period">{period}</p><p className="indicator-note">{note}</p>
  </article>
}
