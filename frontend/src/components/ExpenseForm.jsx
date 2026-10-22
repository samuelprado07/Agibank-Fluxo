import { useState } from 'react'
import { createExpense, updateExpense } from '../services/api.js'

const emptyExpense = { description: '', amount: '', category: '', due_date: '', essential: false, recurring: false, end_date: '' }

export default function ExpenseForm({ expense, onSaved, onCancel }) {
  const [values, setValues] = useState(expense ? { ...expense, amount: expense.amount.replace('.', ','), scope: 'this' } : emptyExpense)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)

  function change(event) {
    const { name, type, checked, value } = event.target
    setValues((previous) => ({ ...previous, [name]: type === 'checkbox' ? checked : value }))
  }

  async function submit(event) {
    event.preventDefault()
    if (saving) return
    setErrors({})
    setMessage('')
    const normalized = values.amount.trim().replace(',', '.')
    if (!/^\d+(\.\d{1,2})?$/.test(normalized) || Number(normalized) <= 0) {
      setErrors({ amount: ['Informe um valor positivo com até duas casas decimais, sem separador de milhar.'] })
      return
    }
    setSaving(true)
    try {
      const payload = { description: values.description.trim(), amount: normalized, category: values.category.trim(), due_date: values.due_date, essential: values.essential }
      if (expense) {
        await updateExpense(expense.id, { ...payload, scope: values.scope })
      } else {
        await createExpense({ ...payload, recurring: values.recurring, ...(values.recurring && values.end_date ? { end_date: values.end_date } : {}) })
      }
      onSaved(expense ? 'Despesa atualizada.' : 'Despesa cadastrada.')
    } catch (error) {
      setErrors(error.fields || {})
      setMessage(error.message)
    } finally {
      setSaving(false)
    }
  }

  const fieldError = (name) => errors[name] && <span className="field-error" id={`expense-${name}-error`}>{errors[name].join(' ')}</span>
  const fieldProps = (name) => ({ name, id: `expense-${name}`, value: values[name], onChange: change, 'aria-invalid': !!errors[name], 'aria-describedby': errors[name] ? `expense-${name}-error` : undefined })

  return <form className="expense-form" onSubmit={submit} aria-labelledby="expense-form-title">
    <h3 id="expense-form-title">{expense ? 'Editar despesa' : 'Nova despesa'}</h3>
    <p className="muted">Cadastre um compromisso pendente e informe se ele é essencial para você.</p>
    <fieldset disabled={saving}>
      <div className="expense-fields">
        <label htmlFor="expense-description">Descrição<input {...fieldProps('description')} required maxLength={150} autoComplete="off" autoFocus />{fieldError('description')}</label>
        <label htmlFor="expense-amount">Valor (R$)<input {...fieldProps('amount')} required inputMode="decimal" placeholder="120,35" autoComplete="off" />{fieldError('amount')}</label>
        <label htmlFor="expense-category">Categoria<input {...fieldProps('category')} maxLength={60} placeholder="Ex.: moradia" />{fieldError('category')}</label>
        <label htmlFor="expense-due_date">Vencimento<input {...fieldProps('due_date')} onInput={change} type="date" required />{fieldError('due_date')}</label>
      </div>
      {!expense && <>
        <label className="essential-choice"><input name="recurring" type="checkbox" checked={values.recurring} onChange={change} />Repetir mensalmente a partir deste vencimento</label>
        {values.recurring && <label className="end-date-field" htmlFor="expense-end_date">Último vencimento permitido (opcional)<input {...fieldProps('end_date')} onInput={change} type="date" min={values.due_date || undefined} />{fieldError('end_date')}<span className="muted">Sem término, a série continua nos períodos consultados. Dias inexistentes usam o último dia do mês.</span></label>}
      </>}
      {expense?.recurring && <label className="scope-field" htmlFor="expense-scope">Aplicar alteração<select id="expense-scope" name="scope" value={values.scope} onChange={change}><option value="this">Somente esta ocorrência</option><option value="following">Esta e as próximas</option></select><span className="muted">Exceções individuais, cancelamentos e pagamentos de outras ocorrências serão preservados. Na série, mantenha o mês e ajuste o dia de vencimento.</span>{fieldError('scope')}</label>}
      <label className="essential-choice"><input name="essential" type="checkbox" checked={values.essential} onChange={change} />Esta despesa é essencial para mim</label>
      {fieldError('essential')}
      <p className="muted">Situação: pendente. Esta operação não registra nem altera um pagamento.</p>
      {message && <p className="form-error" role="alert">{message}</p>}
      <div className="expense-actions"><button type="submit">{saving ? 'Salvando…' : 'Salvar despesa'}</button><button type="button" className="secondary-button" onClick={onCancel}>Fechar formulário</button></div>
    </fieldset>
  </form>
}
