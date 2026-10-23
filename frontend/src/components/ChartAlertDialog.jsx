import { useEffect, useRef } from 'react'
import { date, money } from '../format.js'

export default function ChartAlertDialog({ selection, onClose }) {
  const dialog = useRef(null)
  useEffect(() => {
    const element = dialog.current
    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    element.showModal()
    return () => { element.close(); document.body.style.overflow = previousOverflow; previousFocus?.focus() }
  }, [])

  return <dialog ref={dialog} className="chart-alert-dialog" aria-label="Detalhes do alerta financeiro" onCancel={onClose} onClick={(event) => { if (event.target === event.currentTarget) { const box = event.currentTarget.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) onClose() } }}>
    <div className="chart-alert-toolbar"><strong>Alerta do gráfico</strong><button type="button" className="secondary-button" onClick={onClose} autoFocus aria-label="Fechar alerta">Fechar ×</button></div>
    <div className="chart-risk-summary">
      <h2>{selection.expenses.length === 1 ? 'Despesa em risco' : 'Despesas em risco'}</h2>
      {selection.expenses.map((expense) => <article key={expense.occurrence_id}><h3>{expense.description}</h3><p>{date(expense.original_date)} · <strong>{money(expense.amount)}</strong></p></article>)}
      {!selection.expenses.length && <p>O saldo já está negativo, sem nova despesa associada neste intervalo.</p>}
      <p className="chart-risk-shortfall">Em {date(selection.date)}, poderão faltar <strong>{money(selection.minimumBalance).replace('-', '')}</strong> para cobrir os compromissos considerados.</p>
    </div>
  </dialog>
}
