import { useRef, useState } from 'react'
import { createIncome, updateIncome } from '../services/api.js'

export default function IncomeForm({ income, onSaved, onCancel }) {
  const [values, setValues] = useState(income ? { ...income, amount: income.amount.replace('.', ','), scope: 'this', due_day: income.series_day || '' } : { description: '', amount: '', expected_date: '', frequency: 'single', end_date: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [errors, setErrors] = useState({})
  const sending = useRef(false)
  function change(event) { setValues((old) => ({ ...old, [event.target.name]: event.target.value })) }
  async function submit(event) {
    event.preventDefault()
    if (sending.current) return
    sending.current = true
    setBusy(true)
    setError('')
    setErrors({})
    try {
      const amount = values.amount.trim().replace(',', '.')
      if (!/^\d{1,12}(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0) throw new Error('Informe um valor positivo, com até duas casas decimais e sem separador de milhar.')
      const payload = { description: values.description.trim(), amount, expected_date: values.expected_date }
      if (income) await updateIncome(income.id, { ...payload, scope: values.scope, ...(values.scope === 'following' ? { due_day: Number(values.due_day) } : {}) })
      else await createIncome({ ...payload, frequency: values.frequency, ...(values.frequency === 'monthly' && values.end_date ? { end_date: values.end_date } : {}) })
      onSaved(income ? 'Previsão atualizada.' : 'Renda prevista cadastrada.')
    } catch (failure) { setError(failure.message); setErrors(failure.fields || {}) }
    finally { sending.current = false; setBusy(false) }
  }
  const fieldError = (name) => errors[name] && <span className="field-error">{errors[name].join(' ')}</span>
  const fieldProps = (name) => ({ id: `income-${name}`, name, value: values[name], onChange: change, 'aria-invalid': !!errors[name] })
  return <form className="expense-form" onSubmit={submit} aria-labelledby="income-form-title">
    <h3 id="income-form-title">{income ? 'Ajustar previsão' : 'Nova renda prevista'}</h3>
    <p className="muted">Uma previsão não garante o recebimento e não aumenta seu saldo atual.</p>
    <fieldset disabled={busy}><div className="expense-fields">
      <label htmlFor="income-description">Descrição<input {...fieldProps('description')} required maxLength={150} autoFocus />{fieldError('description')}</label>
      <label htmlFor="income-amount">Valor previsto (R$)<input {...fieldProps('amount')} required inputMode="decimal" placeholder="2200,00" />{fieldError('amount')}</label>
      <label htmlFor="income-expected_date">Data esperada<input {...fieldProps('expected_date')} onInput={change} type="date" required />{fieldError('expected_date')}</label>
      {!income && <label htmlFor="income-frequency">Frequência<select {...fieldProps('frequency')}><option value="single">Única</option><option value="monthly">Mensal</option></select>{fieldError('frequency')}</label>}
    </div>
    {!income && values.frequency === 'monthly' && <label className="scope-field" htmlFor="income-end_date">Última data esperada permitida (opcional)<input {...fieldProps('end_date')} onInput={change} type="date" min={values.expected_date} /><span className="muted">A primeira data define o início. Dias inexistentes usam o último dia do mês; não há ajuste por feriados.</span>{fieldError('end_date')}</label>}
    {income?.frequency === 'monthly' && <><label className="scope-field" htmlFor="income-scope">Aplicar alteração<select {...fieldProps('scope')}><option value="this">Somente esta ocorrência</option><option value="following">Esta e as próximas ainda não recebidas</option></select><span className="muted">Outras exceções, cancelamentos e recebimentos confirmados serão preservados.</span>{fieldError('scope')}</label>
      {values.scope === 'following' && <label className="scope-field" htmlFor="income-due_day">Dia esperado dos próximos meses<input {...fieldProps('due_day')} type="number" min="1" max="31" required />{fieldError('due_day')}</label>}
    </>}
    </fieldset>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="expense-actions"><button type="submit" disabled={busy}>{busy ? 'Salvando…' : 'Salvar previsão'}</button><button type="button" className="secondary-button" disabled={busy} onClick={onCancel}>Voltar</button></div>
  </form>
}
