import { useState } from 'react'
import { createExpense, updateExpense } from '../services/api.js'

const emptyExpense = { description: '', amount: '', category: '', due_date: '', essential: false, is_estimate: false, recurring: false, end_date: '' }

export default function ExpenseForm({ expense, onSaved, onCancel }) {
  const [values, setValues] = useState(expense ? { ...expense, amount: expense.amount.replace('.', ','), scope: 'this', due_day: expense.series_day || '' } : emptyExpense)
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
      const payload = { description: values.description.trim(), amount: normalized, category: values.category.trim(), due_date: values.due_date, essential: values.essential, is_estimate: values.is_estimate }
      if (expense) {
        await updateExpense(expense.id, { ...payload, scope: values.scope, ...(values.scope === 'following' ? { due_day: Number(values.due_day) } : {}) })
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
    <p className="muted">Cadastre uma despesa ou estimativa com valor e data definidos. Todas as pendências até a próxima renda entram no valor comprometido.</p>
    <fieldset disabled={saving}>
      <div className="expense-fields">
        <label htmlFor="expense-description">Descrição<input {...fieldProps('description')} required maxLength={150} autoComplete="off" autoFocus />{fieldError('description')}</label>
        <label htmlFor="expense-amount">Valor (R$)<input {...fieldProps('amount')} required inputMode="decimal" placeholder="120,35" autoComplete="off" />{fieldError('amount')}</label>
        <label htmlFor="expense-category">Categoria<input {...fieldProps('category')} maxLength={60} placeholder="Ex.: moradia" />{fieldError('category')}</label>
        <label htmlFor="expense-due_date">{values.is_estimate ? 'Data prevista do gasto' : 'Vencimento'}<input {...fieldProps('due_date')} onInput={change} type="date" required />{fieldError('due_date')}</label>
      </div>
      {!expense && <>
        <label className="essential-choice"><input name="recurring" type="checkbox" checked={values.recurring} onChange={change} />Repetir mensalmente a partir deste vencimento</label>
        {values.recurring && <label className="end-date-field" htmlFor="expense-end_date">Último vencimento permitido (opcional)<input {...fieldProps('end_date')} onInput={change} type="date" min={values.due_date || undefined} />{fieldError('end_date')}<span className="muted">Sem término, a série continua nos períodos consultados. Dias inexistentes usam o último dia do mês.</span></label>}
      </>}
      {expense?.recurring && <label className="scope-field" htmlFor="expense-scope">Aplicar alteração<select id="expense-scope" name="scope" value={values.scope} onChange={change}><option value="this">Somente esta ocorrência</option><option value="following">Esta e as próximas ainda não realizadas</option></select><span className="muted">Outras exceções, cancelamentos e pagamentos serão preservados. A ocorrência selecionada receberá a alteração solicitada.</span>{fieldError('scope')}</label>}
      {expense?.recurring && values.scope === 'following' && <label className="scope-field" htmlFor="expense-due_day">Dia padrão dos próximos vencimentos<input id="expense-due_day" name="due_day" type="number" min="1" max="31" value={values.due_day} onChange={change} required /><span className="muted">Dias inexistentes usam o último dia do mês, mantendo o dia padrão nos meses seguintes.</span>{fieldError('due_day')}</label>}
      <label className="essential-choice"><input name="essential" type="checkbox" checked={values.essential} onChange={change} />Esta despesa é essencial para mim</label>
      {fieldError('essential')}
      <label className="essential-choice"><input name="is_estimate" type="checkbox" checked={values.is_estimate} onChange={change} />Este valor é uma estimativa de gasto</label>
      {fieldError('is_estimate')}
      {values.is_estimate && <p className="muted">O valor será projetado na data informada, sem distribuição automática. Estimativas não são pagamentos realizados. Para deixar de considerá-la, cancele; se precisar novamente, cadastre outra.</p>}
      <p className="muted">Cada cadastro representa um gasto adicional. Se o mesmo gasto já estiver cadastrado, ajuste ou cancele uma das entradas. A categoria não identifica duplicidades.</p>
      <p className="muted">Situação: pendente. Esta operação não registra nem altera um pagamento.</p>
      {message && <p className="form-error" role="alert">{message}</p>}
      <div className="expense-actions"><button type="submit">{saving ? 'Salvando…' : 'Salvar despesa'}</button><button type="button" className="secondary-button" onClick={onCancel}>Fechar formulário</button></div>
    </fieldset>
  </form>
}
