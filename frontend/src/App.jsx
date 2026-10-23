import { useEffect, useRef, useState } from 'react'
import { getDashboard } from './services/api.js'
import Dashboard from './components/Dashboard.jsx'
import ExpensesPanel from './components/ExpensesPanel.jsx'
import IncomePanel from './components/IncomePanel.jsx'
import RecurrenceSettings from './components/RecurrenceSettings.jsx'
import Navigation from './components/Navigation.jsx'
import SimulationPanel from './components/SimulationPanel.jsx'
import AssistantPanel from './components/AssistantPanel.jsx'
import { pages } from './pages.js'

const currentPage = () => Object.hasOwn(pages, window.location.hash.slice(1)) ? window.location.hash.slice(1) : 'overview'

export default function App() {
  const [page, setPage] = useState(currentPage)
  const [result, setResult] = useState({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [refreshMessage, setRefreshMessage] = useState('')
  const requestId = useRef(0)
  const [conversation, setConversation] = useState([])
  const [assistantAlternative, setAssistantAlternative] = useState(null)

  function explainAlternative(preview) {
    setAssistantAlternative({ preview_token: preview.preview_token, description: preview.occurrence.description })
    window.location.hash = 'assistant'
  }

  async function refreshDashboard() {
    const id = ++requestId.current
    setRefreshMessage('Atualizando seu planejamento…')
    try {
      const data = await getDashboard(AbortSignal.timeout(10000))
      if (id !== requestId.current) return
      setResult({ status: 'ready', data })
      setRefreshMessage('Seu planejamento está atualizado.')
    } catch {
      if (id === requestId.current) setRefreshMessage('Os dados foram salvos. Não foi possível atualizar a projeção; tente novamente.')
    }
  }

  useEffect(() => {
    const changePage = () => {
      if (Object.hasOwn(pages, window.location.hash.slice(1))) {
        setPage(currentPage())
        setRefreshMessage('')
        window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
      }
    }
    changePage()
    window.addEventListener('hashchange', changePage)
    return () => window.removeEventListener('hashchange', changePage)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const id = ++requestId.current
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    getDashboard(controller.signal)
      .then((data) => { if (active && id === requestId.current) setResult({ status: 'ready', data }) })
      .catch((error) => { if (active && id === requestId.current) setResult({ status: error.code === 'no_scenario' ? 'empty' : 'error', message: error.name === 'AbortError' ? 'A consulta demorou mais que o esperado. Tente novamente.' : error.message }) })
      .finally(() => window.clearTimeout(timeout))
    return () => { active = false; window.clearTimeout(timeout); controller.abort() }
  }, [attempt])

  return <div className="app-shell">
    <a href="#main-content" className="skip-link">Ir para o conteúdo</a>
    <Navigation page={page} />
    <div className="workspace">
      <main id="main-content" tabIndex="-1">
        {page !== 'overview' && <a href="#overview" className="back-home" aria-label="Voltar ao início"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 5-7 7 7 7" /></svg></a>}
        {refreshMessage && <div className="dashboard-refresh"><p role="status">{refreshMessage}</p><button type="button" className="text-button" onClick={refreshDashboard}>Atualizar</button></div>}
        {result.status === 'ready' ? <>
          {page === 'overview' && <Dashboard data={result.data} />}
          {page === 'expenses' && <><div className="page-intro"><p className="eyebrow">ORGANIZAÇÃO DO DIA A DIA</p><h1>Seus compromissos, em ordem.</h1><p>Defina o que é essencial e acompanhe cada vencimento.</p></div><ExpensesPanel onChanged={refreshDashboard} /></>}
          {page === 'incomes' && <><div className="page-intro"><p className="eyebrow">PLANEJE SUAS ENTRADAS</p><h1>Mais clareza sobre sua renda.</h1><p>Organize suas previsões e acompanhe o que já recebeu.</p></div><IncomePanel onChanged={refreshDashboard} /></>}
          {page === 'recurrences' && <RecurrenceSettings onChanged={refreshDashboard} />}
          {page === 'simulations' && <><div className="page-intro"><p className="eyebrow">AVALIE SUAS POSSIBILIDADES</p><h1>Simule antes de decidir.</h1><p>Compare uma alternativa com seu planejamento atual.</p></div><SimulationPanel onApplied={refreshDashboard} onExplain={explainAlternative} /></>}
          {page === 'assistant' && <AssistantPanel projectionVersion={result.data.projection_version} alternative={assistantAlternative} onClearAlternative={() => setAssistantAlternative(null)} conversation={conversation} setConversation={setConversation} />}
        </> : <section className="panel state-panel" aria-live="polite"><p className="eyebrow">MEU PLANEJAMENTO</p><h1>{result.status === 'loading' ? 'Preparando seu planejamento…' : result.status === 'empty' ? 'Seu planejamento começa aqui.' : 'Não foi possível carregar os dados.'}</h1>{result.message && <p role="status">{result.message}</p>}{result.status !== 'loading' && <button onClick={() => { setResult({ status: 'loading' }); setAttempt((value) => value + 1) }}>Tentar novamente</button>}</section>}
        <footer><span>agibank <strong>Fluxo</strong></span><span>Previsibilidade para suas próximas escolhas.</span></footer>
      </main>
    </div>
  </div>
}
