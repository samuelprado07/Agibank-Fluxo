import { useEffect, useState } from 'react'
import { cancelExpense, deleteExpense, getExpense, getExpenses } from '../services/api.js'
import { date, money } from '../format.js'
import ExpenseForm from './ExpenseForm.jsx'
import PaymentForm from './PaymentForm.jsx'

const statuses = { pending: 'Pendente', settled: 'Paga', cancelled: 'Cancelada' }

export default function ExpensesPanel({ onChanged }) {
  const [result, setResult] = useState({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [showForm, setShowForm] = useState(false)
  const [filter, setFilter] = useState('all')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState(null)
  const [action, setAction] = useState(null)
  const [scope, setScope] = useState('this')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [detail, setDetail] = useState(null)
  const [payment, setPayment] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    getExpenses(controller.signal)
      .then((data) => { if (active) setResult({ status: 'ready', ...data }) })
      .catch((error) => { if (active) setResult({ status: 'error', message: error.name === 'AbortError' ? 'A consulta demorou mais que o esperado.' : error.message }) })
      .finally(() => window.clearTimeout(timeout))
    return () => { active = false; controller.abort(); window.clearTimeout(timeout) }
  }, [attempt])

  function saved(message) {
    setPayment(null)
    setShowForm(false)
    setEditing(null)
    setAction(null)
    setDetail(null)
    setNotice(message)
    setResult({ status: 'loading' })
    setAttempt((value) => value + 1)
    onChanged()
  }

  async function confirmAction() {
    if (busy) return
    setBusy(true)
    setActionError('')
    try {
      if (action.type === 'cancel') await cancelExpense(action.expense.id, scope)
      else await deleteExpense(action.expense.id)
      saved(action.type === 'cancel' ? 'Cancelamento registrado.' : 'Despesa excluída.')
    } catch (error) { setActionError(error.message) }
    finally { setBusy(false) }
  }

  async function showDetails(expense) {
    setActionError('')
    setBusy(true)
    try { setDetail(await getExpense(expense.id)) }
    catch (error) { setActionError(error.message) }
    finally { setBusy(false) }
  }

  const expenses = (result.expenses || []).filter((expense) => filter === 'all' || expense.status === filter)
  function startPayment(expense, type) {
    setPayment({ expense, type })
    setShowForm(false)
    setAction(null)
    setDetail(null)
    setNotice('')
    setActionError('')
  }
  return <section className="panel expenses-panel" aria-labelledby="expenses-title">
    <div className="panel-heading"><div><p className="eyebrow">SEUS COMPROMISSOS</p><h2 id="expenses-title">Despesas e estimativas</h2></div><button type="button" disabled={!!payment} onClick={() => { setEditing(null); setShowForm(true); setNotice(''); setAction(null) }}>Nova despesa</button></div>
    <p className="muted">Acompanhe despesas e estimativas em datas definidas. Todas as pendências até a próxima renda entram no valor comprometido, sejam essenciais ou não. Gastos ausentes da simulação podem alterar o resultado.</p>
    {notice && <p className="success-notice" role="status">{notice}</p>}
    {payment && <PaymentForm key={`${payment.expense.id}-${payment.type}`} expense={payment.expense} action={payment.type} openingDate={result.opening_date} referenceDate={result.reference_date} onSaved={saved} onReload={() => saved('Lista atualizada. Confira os dados antes de continuar.')} onCancel={() => saved('Confira a situação atualizada na lista.')} />}
    {showForm && <ExpenseForm key={editing?.id || 'new'} expense={editing} onSaved={saved} onCancel={() => { setShowForm(false); setEditing(null) }} />}
    {actionError && <p className="form-error" role="alert">{actionError}</p>}
    {action && <div className="expense-confirm" role="group" aria-label="Confirmar alteração">
      <h3>{action.type === 'cancel' ? 'Cancelar despesa' : 'Excluir despesa sem histórico'}</h3><p>{action.expense.description} — {money(action.expense.amount)}, vencimento {date(action.expense.due_date)}.</p>
      {action.type === 'cancel' && action.expense.recurring ? <label className="scope-field">Alcance do cancelamento<select value={scope} onChange={(event) => setScope(event.target.value)} disabled={busy}><option value="this">Somente esta ocorrência</option><option value="following">Esta e as próximas</option></select></label> : <p className="muted">Esta ação afeta somente este compromisso.{action.expense.recurring && ' As próximas ocorrências mensais serão mantidas.'}</p>}
      <p className="muted">{action.type === 'cancel' ? 'O histórico será preservado e os compromissos cancelados sairão da projeção. Pagamentos registrados serão preservados.' : 'O compromisso será removido. Despesas com histórico não podem ser excluídas.'}</p>
      <div className="expense-actions"><button type="button" disabled={busy} onClick={confirmAction}>{busy ? 'Processando…' : 'Confirmar'}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => setAction(null)}>Voltar</button></div>
    </div>}
    {detail && <div className="expense-detail"><div className="panel-heading"><h3>Detalhes de {detail.description}</h3><button type="button" className="secondary-button" onClick={() => setDetail(null)}>Fechar detalhes</button></div>
      <p>{money(detail.amount)} · {date(detail.due_date)} · {statuses[detail.status]} · {detail.essential ? 'Essencial' : 'Não essencial'}</p>
      {detail.is_estimate && <p className="muted">{detail.status === 'settled' ? 'Valor originalmente estimado. O saldo considera o pagamento efetivo registrado abaixo.' : 'Estimativa de gasto na data informada. Não representa um pagamento realizado.'}</p>}
      <p className="muted">{detail.recurring ? `Mensal · competência ${date(detail.competence).slice(3)}${detail.is_exception ? ' · exceção individual' : ''}${detail.end_date ? ` · término ${date(detail.end_date)}` : ''}` : 'Despesa avulsa'}</p>
      {detail.payment && <p>Pagamento registrado: <strong>{money(detail.payment.amount)}</strong> em {date(detail.payment.date)}. Dados preservados; a edição da despesa não altera pagamentos.</p>}
      <h4>Histórico de pagamentos</h4>{detail.payment_history?.length ? <ul>{detail.payment_history.map((entry) => <li key={entry.id}><strong>{{ confirm: 'Confirmação', correct: 'Correção', undo: 'Desfazimento' }[entry.action]}</strong> em {new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(new Date(entry.created_at))}
        {entry.before.amount && <p className="muted">Antes: {money(entry.before.amount)} em {date(entry.before.date)} · {entry.before.is_voided ? 'desfeito' : 'ativo'}.</p>}
        <p className="muted">Depois: {money(entry.after.amount)} em {date(entry.after.date)} · {entry.after.is_voided ? 'desfeito; previsão restaurada' : 'ativo'}.</p>{entry.reason && <p>Motivo: {entry.reason}</p>}
      </li>)}</ul> : <p className="muted">Sem alterações de pagamento registradas neste módulo.</p>}
      <h4>Histórico de alterações</h4>{detail.history.length ? <ul>{detail.history.map((entry) => <li key={entry.id}><strong>{entry.action === 'cancel' ? 'Cancelamento' : 'Edição'}</strong> em {new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(new Date(entry.created_at))}<p className="muted">Antes: {entry.before.description}, {money(entry.before.amount)}, {date(entry.before.due_date)}, {statuses[entry.before.status]}.</p><p className="muted">Depois: {entry.after.description}, {money(entry.after.amount)}, {date(entry.after.due_date)}, {statuses[entry.after.status]}. Categoria: {entry.after.category || 'Sem categoria'}. Essencial: {entry.after.essential ? 'Sim' : 'Não'}.</p></li>)}</ul> : <p className="muted">Sem edições ou cancelamentos registrados neste módulo.</p>}
    </div>}
    {result.status === 'loading' && <p role="status">Carregando despesas…</p>}
    {result.status === 'error' && <div role="alert"><p>{result.message}</p><button type="button" onClick={() => { setResult({ status: 'loading' }); setAttempt((value) => value + 1) }}>Tentar novamente</button></div>}
    {result.status === 'ready' && !payment && <>
      <div className="expenses-filter"><label htmlFor="expense-filter">Situação</label><select id="expense-filter" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">Todas</option>{Object.entries(statuses).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select><span className="muted">Referência: {date(result.reference_date)}</span></div>
      {!expenses.length ? <p>Nenhuma despesa encontrada para esta seleção.</p> : <div className="table-scroll"><table className="expenses-table"><caption>Despesas e estimativas cadastradas, incluindo vencidas e lançamentos fora do horizonte do gráfico</caption><thead><tr>{['Descrição', 'Valor previsto', 'Categoria', 'Vencimento / data prevista', 'Essencial', 'Situação', 'Ações'].map((heading) => <th scope="col" key={heading}>{heading}</th>)}</tr></thead><tbody>{expenses.map((expense) => <tr key={expense.id}><th scope="row">{expense.description}<span className="recurrence-label">{expense.recurring ? `Mensal${expense.is_exception ? ' · exceção' : ''}` : 'Avulsa'}</span>{expense.is_estimate && <span className="estimate-label">{expense.status === 'settled' ? 'Originalmente estimado' : 'Estimativa de gasto'}</span>}</th><td>{money(expense.amount)}</td><td>{expense.category || 'Sem categoria'}</td><td>{date(expense.due_date)}{expense.status === 'pending' && expense.due_date < result.reference_date && <span className="overdue-label">Vencida</span>}</td><td>{expense.essential ? 'Sim' : 'Não'}</td><td><span className={`expense-status ${expense.status}`}>{statuses[expense.status]}</span></td><td><div className="row-actions">
        <button type="button" className="secondary-button" disabled={busy} onClick={() => showDetails(expense)} aria-label={`Ver detalhes de ${expense.description}`}>Detalhes</button>
        {expense.can_pay && <button type="button" className="secondary-button" onClick={() => startPayment(expense, 'confirm')} aria-label={`Registrar pagamento de ${expense.description}`}>Registrar pagamento</button>}
        {expense.can_correct_payment && <><button type="button" className="secondary-button" onClick={() => startPayment(expense, 'correct')}>Corrigir pagamento</button><button type="button" className="secondary-button" onClick={() => startPayment(expense, 'undo')}>Desfazer pagamento</button></>}
        {expense.can_edit && <><button type="button" className="secondary-button" onClick={() => { setEditing(expense); setShowForm(true); setAction(null); setNotice('') }} aria-label={`Editar ${expense.description}`}>Editar</button><button type="button" className="secondary-button" onClick={() => { setAction({ type: 'cancel', expense }); setScope('this'); setShowForm(false); setActionError('') }} aria-label={`Cancelar ${expense.description}`}>Cancelar</button></>}
        {expense.can_delete && <button type="button" className="secondary-button" onClick={() => { setAction({ type: 'delete', expense }); setShowForm(false); setActionError('') }} aria-label={`Excluir ${expense.description}`}>Excluir</button>}
      </div></td></tr>)}</tbody></table></div>}
    </>}
  </section>
}
