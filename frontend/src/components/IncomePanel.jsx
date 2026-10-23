import { useEffect, useState } from 'react'
import { cancelIncome, getIncome, getIncomes, stopIncomeSeries } from '../services/api.js'
import { date, money } from '../format.js'
import IncomeForm from './IncomeForm.jsx'
import ReceiptForm from './ReceiptForm.jsx'

const statuses = { pending: 'Previsto', settled: 'Recebido', cancelled: 'Cancelado' }
const receiptActions = { confirm: 'Confirmação', correct: 'Correção', undo: 'Desfazimento' }
const timestamp = (value) => new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(new Date(value))

export default function IncomePanel({ onChanged }) {
  const [result, setResult] = useState({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [form, setForm] = useState(null)
  const [receipt, setReceipt] = useState(null)
  const [action, setAction] = useState(null)
  const [detail, setDetail] = useState(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('all')
  const [cutoff, setCutoff] = useState('')
  const [cancelPending, setCancelPending] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    getIncomes(AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]))
      .then((data) => { if (!controller.signal.aborted) setResult({ status: 'ready', ...data }) })
      .catch((failure) => { if (!controller.signal.aborted) setResult({ status: 'error', message: failure.message }) })
    return () => controller.abort()
  }, [attempt])
  function clear() { setForm(null); setReceipt(null); setAction(null); setDetail(null); setError(''); setNotice('') }
  function saved(message) { clear(); setNotice(message); setResult({ status: 'loading' }); setAttempt((old) => old + 1); onChanged() }
  async function details(income) {
    clear(); setBusy(true)
    try { setDetail(await getIncome(income.id, AbortSignal.timeout(10000))) }
    catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  async function confirmAction(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try {
      if (action.type === 'cancel') await cancelIncome(action.income.id)
      else await stopIncomeSeries(action.income.series_id, { from_date: cutoff, cancel_pending: cancelPending })
      saved(action.type === 'cancel' ? 'Previsão cancelada.' : 'Encerramento da renda mensal registrado.')
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  function openAction(income, type) { clear(); setAction({ income, type }); setCutoff(result.reference_date < income.series_start ? income.series_start : result.reference_date); setCancelPending(false) }
  const rows = (result.incomes || []).filter((income) => filter === 'all' || (filter === 'overdue' ? income.overdue : income.status === filter))
  const editing = form || receipt || action
  return <section className="panel expenses-panel" aria-labelledby="incomes-title">
    <div className="panel-heading"><div><p className="eyebrow">SUAS ENTRADAS</p><h2 id="incomes-title">Renda prevista</h2></div><button type="button" disabled={!!editing || busy} onClick={() => { clear(); setForm({}) }}>Nova renda</button></div>
    <p className="muted">Confira suas próximas entradas e confirme somente o que já recebeu. Valores previstos não compõem seu saldo atual.</p>
    {notice && <p className="success-notice" role="status">{notice}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {form && <IncomeForm income={form.id ? form : null} onSaved={saved} onCancel={clear} />}
    {receipt && <ReceiptForm income={receipt.income} action={receipt.type} openingDate={result.opening_date} referenceDate={result.reference_date} onSaved={saved} onCancel={() => saved('Confira a situação atualizada na lista.')} onReload={() => saved('Lista atualizada. Confira os dados antes de continuar.')} />}
    {action && <form className="expense-form" onSubmit={confirmAction}>
      <h3>{action.type === 'cancel' ? 'Cancelar previsão' : 'Encerrar renda mensal'}</h3><p>{action.income.description} · {money(action.income.amount)}</p>
      {action.type === 'stop' ? <fieldset disabled={busy}><label className="scope-field" htmlFor="income-stop-date">Impedir novas ocorrências a partir de<input id="income-stop-date" type="date" required min={action.income.series_start} value={cutoff} onChange={(event) => setCutoff(event.target.value)} onInput={(event) => setCutoff(event.target.value)} /></label><label className="essential-choice"><input type="checkbox" checked={cancelPending} onChange={(event) => setCancelPending(event.target.checked)} />Também cancelar ocorrências pendentes com data esperada a partir dessa data</label><p className="muted">Recebimentos confirmados serão preservados. Sem marcar a opção, previsões já geradas permanecem pendentes.</p></fieldset> : <p className="muted">Somente esta ocorrência será cancelada. A renda sairá da projeção e o histórico será preservado.</p>}
      <div className="expense-actions"><button type="submit" disabled={busy}>{busy ? 'Processando…' : 'Confirmar'}</button><button type="button" className="secondary-button" disabled={busy} onClick={clear}>Voltar</button></div>
    </form>}
    {detail && <div className="expense-detail"><div className="panel-heading"><h3>{detail.description}</h3><button type="button" className="secondary-button" onClick={() => setDetail(null)}>Fechar detalhes</button></div>
      <p>Previsto: {money(detail.amount)} em {date(detail.expected_date)} · {statuses[detail.status]}{detail.overdue ? ' · Atrasado' : ''}</p>
      {detail.frequency === 'monthly' && <p className="muted">Competência {date(detail.competence).slice(3)} · {detail.is_exception ? 'exceção individual' : 'ocorrência mensal'} · início {date(detail.series_start)}{detail.series_end ? ` · término ${date(detail.series_end)}` : ''}{detail.series_cancelled_from ? ` · geração encerrada a partir de ${date(detail.series_cancelled_from)}` : ''}</p>}
      {detail.receipt && <p>Recebido: <strong>{money(detail.receipt.amount)}</strong> em {date(detail.receipt.date)}.</p>}
      <h4>Histórico da previsão</h4>{detail.history.length ? <ul>{detail.history.map((entry) => <li key={entry.id}><strong>{entry.action === 'cancel' ? 'Cancelamento' : 'Ajuste'}</strong> em {timestamp(entry.created_at)}<p className="muted">Antes: {entry.before.description}, {money(entry.before.amount)} em {date(entry.before.expected_date)}, {statuses[entry.before.status]}.</p><p className="muted">Depois: {entry.after.description}, {money(entry.after.amount)} em {date(entry.after.expected_date)}, {statuses[entry.after.status]}.</p></li>)}</ul> : <p className="muted">Sem ajustes registrados.</p>}
      <h4>Histórico de recebimentos</h4>{detail.receipt_history.length ? <ul>{detail.receipt_history.map((entry) => <li key={entry.id}><strong>{receiptActions[entry.action]}</strong> em {timestamp(entry.created_at)}{entry.before.amount && <p className="muted">Antes: {money(entry.before.amount)} em {date(entry.before.date)} · {entry.before.is_voided ? 'desfeito' : 'ativo'}.</p>}<p className="muted">Depois: {money(entry.after.amount)} em {date(entry.after.date)} · {entry.after.is_voided ? 'desfeito; previsão restaurada' : 'ativo'}.</p>{entry.reason && <p>Motivo: {entry.reason}</p>}</li>)}</ul> : <p className="muted">Sem alterações de recebimento registradas neste módulo.</p>}
    </div>}
    {result.status === 'loading' && <p role="status">Carregando rendas…</p>}
    {result.status === 'error' && <div role="alert"><p>{result.message}</p><button type="button" onClick={() => saved('Consultando rendas novamente…')}>Tentar novamente</button></div>}
    {result.status === 'ready' && !editing && <>
      <div className="expenses-filter"><label htmlFor="income-filter">Situação</label><select id="income-filter" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">Todas</option><option value="overdue">Atrasados</option>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span>Referência: {date(result.reference_date)}</span></div>
      {!rows.length ? <p>Nenhuma renda encontrada para esta seleção.</p> : <div className="table-scroll"><table className="expenses-table"><caption>Recebimentos cadastrados, incluindo atrasados e ocorrências fora do horizonte do gráfico</caption><thead><tr>{['Descrição', 'Valor previsto', 'Data esperada', 'Frequência', 'Situação', 'Recebido', 'Ações'].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{rows.map((income) => <tr key={income.id}><th scope="row">{income.description}{income.is_exception && <span className="recurrence-label">Exceção individual</span>}</th><td>{money(income.amount)}</td><td>{date(income.expected_date)}{income.overdue && <span className="overdue-label">Atrasado · fora da projeção</span>}</td><td>{income.frequency === 'monthly' ? `Mensal · ${date(income.competence).slice(3)}` : 'Única'}</td><td><span className={`expense-status ${income.status}`}>{statuses[income.status]}</span></td><td>{income.receipt ? <>{money(income.receipt.amount)}<span className="recurrence-label">{date(income.receipt.date)}</span></> : '—'}</td><td><div className="row-actions">
        <button type="button" className="secondary-button" disabled={busy} onClick={() => details(income)} aria-label={`Ver detalhes de ${income.description}`}>Detalhes</button>
        {income.can_edit && <><button type="button" className="secondary-button" onClick={() => { clear(); setForm(income) }} aria-label={`Ajustar previsão de ${income.description}`}>Ajustar previsão</button><button type="button" className="secondary-button" onClick={() => openAction(income, 'cancel')}>Cancelar previsão</button></>}
        {income.can_receive && <button type="button" className="secondary-button" onClick={() => { clear(); setReceipt({ income, type: 'confirm' }) }} aria-label={`Confirmar recebimento de ${income.description}`}>Confirmar recebimento</button>}
        {income.can_correct_receipt && <><button type="button" className="secondary-button" onClick={() => { clear(); setReceipt({ income, type: 'correct' }) }}>Corrigir recebimento</button><button type="button" className="secondary-button" onClick={() => { clear(); setReceipt({ income, type: 'undo' }) }}>Desfazer recebimento</button></>}
        {income.series_id && !income.series_cancelled_from && <button type="button" className="secondary-button" onClick={() => openAction(income, 'stop')}>Encerrar renda mensal</button>}
      </div></td></tr>)}</tbody></table></div>}
    </>}
  </section>
}
