import { useEffect, useRef, useState } from 'react'
import { getAssistantContext, sendAssistantMessage } from '../services/api.js'
import { date } from '../format.js'

export default function AssistantPanel({ projectionVersion, alternative, onClearAlternative, conversation, setConversation }) {
  const [context, setContext] = useState(null)
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const mounted = useRef(false)
  const pending = useRef(false)
  const request = useRef(null)
  const bottom = useRef(null)
  const humanRequested = conversation.some((turn) => turn.kind === 'human-request')

  function requestHuman() {
    if (busy || humanRequested) return
    setConversation((old) => old.some((turn) => turn.kind === 'human-request') ? old : [...old.slice(-19), {
      id: crypto.randomUUID(), kind: 'human-request',
      text: 'Solicitação de atendimento humano registrada neste chat. O fluxo prevê que um atendente do Agibank dê continuidade ao protocolo.',
    }])
  }

  useEffect(() => {
    mounted.current = true
    let loading = false
    const update = async () => {
      if (loading || document.visibilityState === 'hidden') return
      loading = true
      try {
        const data = await getAssistantContext(AbortSignal.timeout(10000))
        if (mounted.current) setContext(data)
      } catch (failure) { if (mounted.current) setError(failure.message) }
      finally { loading = false }
    }
    update()
    const timer = window.setInterval(update, 15000)
    window.addEventListener('focus', update)
    document.addEventListener('visibilitychange', update)
    return () => { mounted.current = false; request.current?.abort(); window.clearInterval(timer); window.removeEventListener('focus', update); document.removeEventListener('visibilitychange', update) }
  }, [projectionVersion])

  useEffect(() => { if (conversation.length) bottom.current?.scrollIntoView({ block: 'nearest' }) }, [conversation.length])

  async function submit(event) {
    event.preventDefault()
    if (pending.current || !question.trim()) return
    pending.current = true; setBusy(true); setError('')
    const message = question.trim()
    const controller = new AbortController()
    request.current = controller
    try {
      const fresh = await getAssistantContext(AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]))
      if (!mounted.current) return
      setContext(fresh)
      const previous = conversation.findLast((turn) => turn.history_token)
      const response = await sendAssistantMessage({ message, projection_version: fresh.projection_version,
        history_token: previous?.history_token || null, alternative_token: alternative?.preview_token || null }, AbortSignal.any([controller.signal, AbortSignal.timeout(35000)]))
      if (!mounted.current) return
      setConversation((old) => [...old.slice(-19), { ...response, question: message, id: crypto.randomUUID() }])
      setQuestion('')
      if (response.current_projection_version !== fresh.projection_version) {
        const updated = await getAssistantContext(AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]))
        if (mounted.current) setContext(updated)
      }
    } catch (failure) {
      if (mounted.current && !controller.signal.aborted) setError(failure.name === 'TimeoutError' ? 'A resposta demorou mais que o esperado. Tente novamente.' : failure.message)
    } finally { pending.current = false; if (mounted.current) setBusy(false) }
  }

  return <section className="panel assistant-panel" aria-labelledby="assistant-title">
    <div className="panel-heading"><div><p className="eyebrow">ENTENDA SEU PLANEJAMENTO</p><h1 id="assistant-title">Assistente Fluxo</h1></div><span className="period-tag">Gemini</span></div>
    <p className="muted">Tire dúvidas sobre sua projeção e seus alertas. O assistente explica os cálculos; não realiza pagamentos nem altera seu planejamento.</p>
    <p className="assistant-data-note">Ao enviar, sua pergunta e os dados necessários do planejamento, incluindo descrições dos compromissos, são enviados ao Gemini. Evite informar documentos, senhas ou dados pessoais na pergunta. A conversa fica apenas nesta sessão, sem histórico salvo no banco.</p>
    {context && <p className="muted">Referência: {date(context.reference_date)} · análise de {date(context.period.start)} a {date(context.period.end)}.</p>}
    {alternative && <div className="assistant-alternative"><div><strong>Alternativa selecionada</strong><p>{alternative.description} · comparação calculada pelo backend.</p></div><button className="secondary-button" type="button" disabled={busy} onClick={onClearAlternative}>Usar cenário principal</button></div>}
    <div className="assistant-suggestions" aria-label="Sugestões de perguntas">{['Por que meu saldo pode ficar insuficiente?', 'Quais compromissos precisam de atenção?', alternative ? 'Explique a comparação desta alternativa.' : 'O que os dados ainda não permitem concluir?'].map((text) => <button type="button" key={text} className="secondary-button" disabled={busy} onClick={() => setQuestion(text)}>{text}</button>)}</div>
    <div className="assistant-conversation">{conversation.map((turn) => {
      if (turn.kind === 'human-request') return <article className="assistant-human-message" key={turn.id} role="status"><strong>Atendimento humano solicitado</strong><p>{turn.text}</p><small>Solicitação local: este ambiente ainda não está conectado à central de atendimento.</small></article>
      const stale = turn.stale || (context && turn.projection_version !== context.projection_version)
      return <article className="assistant-turn" key={turn.id}><p className="assistant-question"><strong>Você</strong>{turn.question}</p><div className="assistant-answer"><div className="assistant-answer-heading"><strong>Assistente Fluxo</strong><span className={stale ? 'assistant-old' : 'muted'}>{stale ? 'Projeção anterior' : 'Projeção consultada'}</span></div><p className="assistant-version">Referência {date(turn.reference_date)} · versão {turn.projection_version.slice(0, 8)}{turn.alternative_version && ' · inclui alternativa calculada'}</p><p className="assistant-text">{turn.text}</p><p className="muted">{turn.limitations}</p></div></article>
    })}<div ref={bottom} /></div>
    {error && <p role="alert" className="form-error">{error}</p>}
    <form className="assistant-form" onSubmit={submit}><label htmlFor="assistant-question">Sua pergunta<textarea id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} rows="3" required disabled={busy} placeholder="Ex.: por que aparece um alerta mesmo com saldo positivo no fim do dia?" /></label><div className="expense-actions assistant-actions"><button type="submit" disabled={busy || !question.trim()}>{busy ? 'Consultando o assistente…' : 'Enviar pergunta'}</button><button type="button" className="secondary-button" disabled={busy || !conversation.length} onClick={() => setConversation([])}>Limpar conversa</button><button type="button" className="assistant-human-button" disabled={busy || humanRequested} onClick={requestHuman}><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 13v-1a8 8 0 0 1 16 0v1M4 12H3v7h4v-7H4Zm16 0h1v7h-4v-7h3ZM20 19c0 2-3 3-6 3" /></svg>{humanRequested ? 'Atendimento solicitado' : 'Solicitar atendimento humano'}</button></div></form>
    {busy && <p role="status" className="muted">Aguarde. Os indicadores e alertas continuam sendo calculados pelo sistema.</p>}
  </section>
}
