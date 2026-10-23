import { useEffect, useState } from 'react'
import { getRecurrence, getRecurrences, stopRecurrence, updateRecurrence } from '../services/api.js'
import { date, money } from '../format.js'

const states = { active: 'Ativa', stopped: 'Encerrada', scheduled_stop: 'Encerramento agendado', ended: 'Vigência concluída' }

function SettingsForm({ series, reference, stopping, onSaved, onClose }) {
  const [values, setValues] = useState({ description: series.description, amount: series.amount.replace('.', ','), category: series.category, essential: series.essential, is_estimate: series.is_estimate, due_day: series.due_day, end_date: series.end_date || '', effective_month: (reference > series.start_date ? reference : series.start_date).slice(0, 7), from_date: reference, cancel_pending: false })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [fields, setFields] = useState({})
  const change = (event) => { const {name, value, type, checked} = event.target; setValues((previous) => ({...previous, [name]:type === 'checkbox' ? checked : value})) }
  const props = (name) => ({ id:`series-${name}`, name, value:values[name], onChange:change, 'aria-invalid':!!fields[name], 'aria-describedby':fields[name] ? `series-${name}-error` : undefined })
  const fieldError = (name) => fields[name] && <span className="field-error" id={`series-${name}-error`}>{fields[name].join(' ')}</span>

  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setFields({})
    try {
      if (stopping) {
        await stopRecurrence(series.id, { from_date:values.from_date, cancel_pending:values.cancel_pending })
      } else {
        await updateRecurrence(series.id, { description:values.description.trim(), amount:values.amount.trim().replace(',', '.'), category:values.category.trim(), essential:values.essential, is_estimate:values.is_estimate, due_day:Number(values.due_day), end_date:values.end_date || null, effective_from:`${values.effective_month}-01` })
      }
      onSaved(stopping ? 'Recorrência encerrada conforme a data e o alcance escolhidos.' : 'Configuração mensal atualizada. Pagamentos e exceções preservados.')
    } catch (failure) { setError(failure.message); setFields(failure.fields || {}) }
    finally { setBusy(false) }
  }

  return <form className="expense-form recurrence-editor" onSubmit={submit} aria-labelledby="series-form-title">
    <div className="panel-heading"><div><p className="eyebrow">CONFIGURAÇÃO MENSAL</p><h3 id="series-form-title">{stopping ? 'Encerrar recorrência' : 'Editar recorrência'}</h3></div><span className="period-tag">{series.description}</span></div>
    <fieldset disabled={busy}>
      {stopping ? <>
        <p>A partir da data escolhida, novos compromissos com vencimento nessa data ou depois dela não serão gerados.</p>
        <label className="scope-field" htmlFor="series-from_date">Encerrar a partir de<input {...props('from_date')} onInput={change} type="date" min={reference} required /></label>
        <label className="essential-choice"><input type="checkbox" name="cancel_pending" checked={values.cancel_pending} onChange={change} />Cancelar também as ocorrências pendentes já geradas com vencimento a partir dessa data</label>
        <p className="muted">Se não marcar esta opção, os compromissos existentes serão mantidos. Pagamentos anteriores e despesas pagas serão sempre preservados.</p>
      </> : <>
        <div className="expense-fields">
          <label htmlFor="series-description">Descrição<input {...props('description')} maxLength="150" required autoFocus />{fieldError('description')}</label>
          <label htmlFor="series-amount">Valor padrão (R$)<input {...props('amount')} inputMode="decimal" required />{fieldError('amount')}</label>
          <label htmlFor="series-category">Categoria<input {...props('category')} maxLength="60" />{fieldError('category')}</label>
          <label htmlFor="series-due_day">Dia de vencimento<input {...props('due_day')} type="number" min="1" max="31" required />{fieldError('due_day')}</label>
          <label htmlFor="series-effective_month">Aplicar a partir da competência<input {...props('effective_month')} onInput={change} type="month" min={series.start_date.slice(0,7)} required />{fieldError('effective_from')}</label>
          <label htmlFor="series-end_date">Último vencimento permitido (opcional)<input {...props('end_date')} onInput={change} type="date" min={series.start_date} />{fieldError('end_date')}</label>
        </div>
        <label className="essential-choice"><input type="checkbox" name="essential" checked={values.essential} onChange={change} />Esta despesa é essencial para mim</label>{fieldError('essential')}
        <label className="essential-choice"><input type="checkbox" name="is_estimate" checked={values.is_estimate} onChange={change} />Este valor é uma estimativa de gasto</label>{fieldError('is_estimate')}
        <p className="muted">Início preservado: {date(series.start_date)}. Alterações valem para pendentes sem pagamento, incluindo vencidas na competência escolhida ou posterior. Exceções individuais e cancelamentos são mantidos.</p>
        <p className="muted">Alterar o término não apaga ocorrências já geradas. Para retirá-las do planejamento, use o cancelamento. Dias inexistentes usam o último dia do mês.</p>
      </>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="expense-actions"><button type="submit">{busy ? 'Salvando…' : stopping ? 'Confirmar encerramento' : 'Salvar configuração'}</button><button type="button" className="secondary-button" onClick={onClose}>Voltar</button></div>
    </fieldset>
    {!stopping && series.history?.length > 0 && <details className="daily-details"><summary>Histórico da recorrência</summary><ul>{series.history.map((entry,index) => <li key={index}>{entry.action === 'stop' ? 'Encerramento' : 'Edição'} · {new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short',timeZone:'America/Sao_Paulo'}).format(new Date(entry.created_at))}</li>)}</ul></details>}
  </form>
}

export default function RecurrenceSettings({ onChanged }) {
  const [result, setResult] = useState({ status:'loading' })
  const [attempt, setAttempt] = useState(0)
  const [selected, setSelected] = useState(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [opening, setOpening] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const timeout = window.setTimeout(() => controller.abort(),10000)
    getRecurrences(controller.signal).then((data) => { if(active) setResult({ status:'ready',...data }) }).catch((failure) => { if(active) setResult({ status:'error',message:failure.message }) }).finally(() => window.clearTimeout(timeout))
    return () => { active=false; controller.abort(); window.clearTimeout(timeout) }
  },[attempt])

  async function open(series, stopping) {
    setError(''); setOpening(true); setNotice('')
    try { setSelected({series:await getRecurrence(series.id),stopping}) }
    catch(failure) { setError(failure.message) }
    finally { setOpening(false) }
  }
  function saved(message) { setNotice(message); setSelected(null); setResult({status:'loading'}); setAttempt((value)=>value+1); onChanged() }

  return <>
    <div className="page-intro"><p className="eyebrow">CONTINUIDADE SEM SURPRESAS</p><h1>Todo mês, sob controle.</h1><p>Organize as despesas que se repetem e preserve o histórico de cada compromisso.</p></div>
    <section className="panel" aria-labelledby="recurrences-title"><div className="panel-heading"><div><h2 id="recurrences-title">Suas recorrências</h2><p className="muted">A configuração orienta os próximos meses. Cada ocorrência tem valor, vencimento e situação próprios.</p></div><a className="button-link" href="#expenses">Cadastrar despesa</a></div>
      {notice && <p className="success-notice" role="status">{notice}</p>}{error && <p className="form-error" role="alert">{error}</p>}
      {selected && <SettingsForm key={`${selected.series.id}-${selected.stopping}`} series={selected.series} reference={result.reference_date} stopping={selected.stopping} onSaved={saved} onClose={()=>setSelected(null)} />}
      {result.status==='loading' && <p role="status">Carregando recorrências…</p>}
      {result.status==='error' && <div role="alert"><p>{result.message}</p><button onClick={()=>{setResult({status:'loading'});setAttempt((value)=>value+1)}}>Tentar novamente</button></div>}
      {result.status==='ready' && (!result.recurrences.length ? <div className="empty-state"><span aria-hidden="true">↻</span><h3>Nenhuma recorrência cadastrada.</h3><p>Ao cadastrar uma despesa, marque a opção de repetição mensal.</p><a href="#expenses">Ir para despesas →</a></div> : <div className="recurrences-list">{result.recurrences.map((series)=><article className="recurrence-card" key={series.id}>
        <div className="recurrence-mark" aria-hidden="true">↻</div><div className="recurrence-main"><div className="recurrence-title"><h3>{series.description}</h3><span className={`expense-status ${series.generation_status==='active'?'settled':'cancelled'}`}>{states[series.generation_status]}</span></div><p>{series.category || 'Sem categoria'} · {series.essential?'Essencial':'Não essencial'}</p><div className="recurrence-meta"><span>Dia <strong>{series.due_day}</strong> de cada mês</span><span>Desde {date(series.start_date)}</span><span>{series.end_date?`Até ${date(series.end_date)}`:'Sem término definido'}</span></div>{series.cancelled_from && <p className="muted">Novos vencimentos interrompidos a partir de {date(series.cancelled_from)}.</p>}<p className="scheduled-change">{series.next_change && <>A partir de {date(series.next_change.date)}: {money(series.next_change.amount)}, vencimento no dia {series.next_change.due_day}.</>}</p><p className="muted">{series.pending_count} ocorrência(s) pendente(s){series.next_due_date?` · próximo vencimento ${date(series.next_due_date)}`:''}</p></div>
        <div className="recurrence-value">{series.is_estimate && <span className="estimate-label">Estimativa de gasto</span>}<small>Valor padrão</small><strong>{money(series.amount)}</strong><div className="row-actions"><button className="secondary-button" disabled={opening} onClick={()=>open(series,false)} aria-label={`Configurar ${series.description}`}>Configurar</button><button className="text-button" disabled={opening} onClick={()=>open(series,true)} aria-label={`Encerrar ${series.description}`}>Encerrar</button></div></div>
      </article>)}</div>)}
    </section>
  </>
}

