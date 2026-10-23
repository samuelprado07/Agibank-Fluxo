import { useEffect, useRef, useState } from 'react'
import { applySimulation, getSimulationContext, previewSimulation } from '../services/api.js'
import { date, money } from '../format.js'
import ProjectionChart from './ProjectionChart.jsx'
import AlertsPanel from './AlertsPanel.jsx'

function Summary({ result }) {
  return <>
    <p><strong>{result.first_deficit_date ? `Primeira insuficiência: ${date(result.first_deficit_date)}` : 'Sem insuficiência no período comparado.'}</strong></p>
    <p>Maior falta estimada: <strong>{money(result.max_shortfall)}</strong>.</p>
    {result.has_no_margin && <p className="muted">Há ausência de margem em algum ponto da sequência.</p>}
  </>
}

export default function SimulationPanel({ onApplied }) {
  const [context, setContext] = useState(null)
  const [reload, setReload] = useState(0)
  const [selectedId, setSelectedId] = useState('')
  const [amount, setAmount] = useState('')
  const [when, setWhen] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [blocked, setBlocked] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const sending = useRef(false)
  const application = useRef(null)
  useEffect(() => {
    const controller = new AbortController()
    getSimulationContext(AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]))
      .then((data) => { if (!controller.signal.aborted) setContext(data) })
      .catch((failure) => { if (!controller.signal.aborted) setError(failure.message) })
    return () => controller.abort()
  }, [reload])
  const selected = context?.occurrences.find((row) => String(row.id) === selectedId)
  function select(event) {
    const value = event.target.value
    const row = context.occurrences.find((entry) => String(entry.id) === value)
    setSelectedId(value); setAmount(row?.amount.replace('.', ',') || ''); setWhen(row?.date || '')
    setError(''); setNotice('')
  }
  function discard(refresh = false) {
    setPreview(null); setError(''); setUncertain(false); setBlocked(false); application.current = null
    setNotice('Alternativa descartada. Nenhuma alteração foi aplicada por esta prévia.')
    if (refresh) { setContext(null); setSelectedId(''); setAmount(''); setWhen(''); setReload((old) => old + 1) }
  }
  async function calculate(event) {
    event.preventDefault()
    if (sending.current || !selected) return
    sending.current = true; setBusy(true); setError(''); setNotice('')
    try {
      const normalized = amount.trim().replace(',', '.')
      if (!/^\d{1,12}(\.\d{1,2})?$/.test(normalized) || Number(normalized) <= 0) throw new Error('Informe um valor positivo com até duas casas decimais e sem separador de milhar.')
      const result = await previewSimulation({ occurrence_id: selected.id, changes: { amount: normalized, date: when } }, AbortSignal.timeout(15000))
      if (!result?.preview_token || !result.comparison) throw new Error('A prévia não pôde ser consultada. Tente novamente; o planejamento não foi alterado por esta simulação.')
      setPreview(result); application.current = null; setBlocked(false); setUncertain(false)
    } catch (failure) { setError(failure.message) }
    finally { sending.current = false; setBusy(false) }
  }
  async function apply() {
    if (sending.current || blocked || !preview) return
    if (!application.current) application.current = { preview_token: preview.preview_token, key: crypto.randomUUID() }
    sending.current = true; setBusy(true); setError('')
    try {
      await applySimulation(application.current, AbortSignal.timeout(15000))
      setPreview(null); application.current = null; setUncertain(false)
      setNotice('Alterações aplicadas ao planejamento local. Projeção e alertas foram recalculados. O dashboard volta a usar sua regra habitual de horizonte.')
      setContext(null); setSelectedId(''); setAmount(''); setWhen(''); setReload((old) => old + 1)
      onApplied?.()
    } catch (failure) {
      const definitive = [400, 403, 404, 409, 415].includes(failure.status)
      setUncertain(!definitive); setBlocked(definitive)
      setError(definitive ? failure.message : 'O resultado da aplicação não pôde ser confirmado. Tente consultar novamente: a mesma operação será reenviada, sem aplicar as alterações duas vezes.')
    } finally { sending.current = false; setBusy(false) }
  }
  const unchanged = selected && Number(amount.trim().replace(',', '.')) === Number(selected.amount) && when === selected.date
  return <section className="panel simulation-panel" aria-labelledby="simulation-title">
    <div className="panel-heading"><div><p className="eyebrow">AVALIE ANTES DE DECIDIR</p><h2 id="simulation-title">Simular uma alternativa</h2></div><span className="period-tag">Uma ocorrência por vez</span></div>
    <p className="muted">Teste outro valor ou data sem alterar seu planejamento. Somente a aplicação explícita salva as alterações. Alterar uma data aqui não modifica vencimentos, acordos ou condições reais do compromisso.</p>
    {notice && <p className="success-notice" role="status">{notice}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {context && error && !preview && <button type="button" className="secondary-button" onClick={() => { setError(''); setContext(null); setSelectedId(''); setAmount(''); setWhen(''); setReload((old) => old + 1) }}>Atualizar previsões</button>}
    {!context && !error && <p role="status">Carregando previsões para simular…</p>}
    {!context && error && <button type="button" onClick={() => { setError(''); setReload((old) => old + 1) }}>Atualizar previsões</button>}
    {context && !context.occurrences.length && <p>Nenhuma ocorrência pendente disponível. Cadastre uma despesa ou renda prevista para testar alternativas.</p>}
    {context?.occurrences.length > 0 && <form onSubmit={calculate}>
      <fieldset className="simulation-fields" disabled={busy || !!preview}>
        <label htmlFor="simulation-occurrence">Despesa ou recebimento previsto<select id="simulation-occurrence" value={selectedId} onChange={select} required><option value="">Selecione uma ocorrência</option>{context.occurrences.map((row) => <option key={row.id} value={row.id}>{row.direction === 'income' ? 'Entrada prevista' : row.is_estimate ? 'Estimativa de saída' : 'Despesa'} · {row.description} · {money(row.amount)} · {date(row.date)}</option>)}</select></label>
        <div className="expense-fields">
          <label htmlFor="simulation-amount">Valor na alternativa (R$)<input id="simulation-amount" value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" required disabled={!selected || busy || !!preview} /></label>
          <label htmlFor="simulation-date">Data na alternativa<input id="simulation-date" type="date" value={when} onChange={(event) => setWhen(event.target.value)} onInput={(event) => setWhen(event.target.value)} required disabled={!selected || busy || !!preview} /></label>
        </div>
        {selected?.is_recurring && <p className="muted">Apenas esta ocorrência mensal será alterada. A configuração, os demais meses e os realizados serão preservados.</p>}
      </fieldset>
      {!preview && <button type="submit" disabled={busy || !selected || unchanged}>{busy ? 'Calculando…' : 'Calcular alternativa'}</button>}
    </form>}
    {preview && <div className="simulation-result">
      <h3>Comparação antes e depois</h3>
      <p>Referência {date(preview.reference_date)} · período fixo de {date(preview.period.start)} a {date(preview.period.end)}, inclusive. Ambos usam o mesmo motor e as mesmas regras.</p>
      <p><strong>{preview.occurrence.description}</strong>: {money(preview.occurrence.original_amount)} em {date(preview.occurrence.original_date)} → {money(preview.occurrence.changes.amount)} em {date(preview.occurrence.changes.date)}.</p>
      <div className="simulation-comparison"><article><h4>Antes</h4><Summary result={preview.comparison.before} /></article><article><h4>Alternativa</h4><Summary result={preview.comparison.after} /></article></div>
      {preview.warnings.map((warning) => <p className="simulation-warning" key={warning}>{warning}</p>)}
      <details className="simulation-projection"><summary>Ver projeção e alertas da alternativa</summary><ProjectionChart days={preview.after.chart_days} analysisDays={preview.after.days} referenceDate={preview.reference_date} assumptionDetails={preview.after.assumption_details} alerts={preview.after.alerts} period={preview.period} /><AlertsPanel alerts={preview.after.alerts} period={preview.period} referenceDate={preview.reference_date} assumptionDetails={preview.after.assumption_details} /></details>
      <div className="expense-actions">
        {!blocked && <button type="button" onClick={apply} disabled={busy}>{busy ? 'Processando…' : uncertain ? 'Consultar aplicação novamente' : 'Aplicar alternativa ao planejamento'}</button>}
        {!uncertain && <button type="button" className="secondary-button" disabled={busy} onClick={() => discard(blocked)}>{blocked ? 'Descartar e atualizar previsões' : 'Descartar alternativa'}</button>}
      </div>
    </div>}
  </section>
}
