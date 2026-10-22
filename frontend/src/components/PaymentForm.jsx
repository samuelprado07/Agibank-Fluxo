import { useRef, useState } from 'react'
import { savePayment } from '../services/api.js'
import { date, money } from '../format.js'

const titles = { confirm: 'Registrar pagamento', correct: 'Corrigir pagamento', undo: 'Desfazer pagamento' }
const messages = { confirm: 'Pagamento registrado. A previsão foi substituída pela saída efetiva.', correct: 'Pagamento corrigido e planejamento atualizado.', undo: 'Pagamento desfeito. A despesa voltou a ficar pendente.' }

export default function PaymentForm({ expense, action, openingDate, referenceDate, onSaved, onCancel, onReload }) {
  const [amount, setAmount] = useState((expense.payment?.amount || expense.amount).replace('.', ','))
  const [effectiveDate, setEffectiveDate] = useState(expense.payment?.date || referenceDate)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [error, setError] = useState('')
  const [fields, setFields] = useState({})
  const [conflict, setConflict] = useState(false)
  const attempt = useRef(null)
  const sending = useRef(false)

  async function submit(event) {
    event.preventDefault()
    if (sending.current || conflict) return
    setError('')
    setFields({})
    if (!attempt.current) {
      const normalized = amount.trim().replace(',', '.')
      if (action !== 'undo' && (!/^\d{1,12}(\.\d{1,2})?$/.test(normalized) || Number(normalized) <= 0)) {
        setFields({ amount: ['Informe um valor positivo, com até duas casas decimais e sem separador de milhar.'] })
        return
      }
      attempt.current = { key: crypto.randomUUID(), version: expense.payment_version, ...(action !== 'undo' ? { amount: normalized, date: effectiveDate } : {}), ...(action !== 'confirm' ? { reason: reason.trim() } : {}) }
    }
    sending.current = true
    setBusy(true)
    try {
      await savePayment(expense.id, action, attempt.current, AbortSignal.timeout(10000))
      onSaved(messages[action])
    } catch (failure) {
      const definitive = [400, 403, 404, 409, 415].includes(failure.status)
      if (definitive) attempt.current = null
      setUncertain(!definitive)
      setConflict(failure.status === 409 || failure.status === 404)
      setFields(failure.fields || {})
      setError(definitive ? failure.message : 'A confirmação não pôde ser consultada. Tente novamente: os mesmos dados e a mesma chave serão reenviados, sem duplicar o pagamento.')
    } finally {
      sending.current = false
      setBusy(false)
    }
  }

  const fieldError = (name) => fields[name] && <span className="field-error">{fields[name].join(' ')}</span>
  return <form className="expense-form payment-form" onSubmit={submit} aria-labelledby="payment-title">
    <h3 id="payment-title">{titles[action]}</h3>
    <p><strong>{expense.description}</strong> · valor previsto {money(expense.amount)} · vencimento {date(expense.due_date)}.</p>
    {expense.payment && <p>Pagamento atual: {money(expense.payment.amount)} em {date(expense.payment.date)}.</p>}
    <p className="muted">{action === 'undo' ? 'A saída efetiva deixará de compor o saldo. A previsão original voltará a ser considerada; se vencida, será tratada como imediata. O histórico será preservado.' : 'Informe o valor total efetivamente pago. Mesmo que diferente do previsto, ele quita toda esta ocorrência. As próximas contas não serão alteradas.'}</p>
    <fieldset disabled={busy || uncertain || conflict}>
      {action !== 'undo' && <div className="expense-fields">
        <label htmlFor="payment-amount">Valor efetivamente pago (R$)<input id="payment-amount" value={amount} onChange={(event) => setAmount(event.target.value)} required inputMode="decimal" autoComplete="off" aria-invalid={!!fields.amount} />{fieldError('amount')}</label>
        <label htmlFor="payment-date">Data efetiva<input id="payment-date" type="date" value={effectiveDate} min={openingDate} max={referenceDate} onChange={(event) => setEffectiveDate(event.target.value)} required aria-invalid={!!fields.date} />{fieldError('date')}</label>
      </div>}
      {action !== 'confirm' && <label className="scope-field" htmlFor="payment-reason">Motivo da alteração<textarea id="payment-reason" value={reason} onChange={(event) => setReason(event.target.value)} required maxLength={500} rows={3} aria-invalid={!!fields.reason} />{fieldError('reason')}</label>}
    </fieldset>
    <p className="muted">Referência: {date(referenceDate)}. Datas aceitas desde {date(openingDate)} até a referência. Este registro atualiza seu planejamento financeiro.</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="expense-actions">
      {!conflict && <button type="submit" disabled={busy}>{busy ? 'Processando…' : uncertain ? 'Consultar e tentar novamente' : titles[action]}</button>}
      {conflict && <button type="button" onClick={onReload}>Atualizar lista</button>}
      <button type="button" className="secondary-button" disabled={busy} onClick={onCancel}>{uncertain ? 'Fechar e conferir a lista' : 'Voltar'}</button>
    </div>
  </form>
}
