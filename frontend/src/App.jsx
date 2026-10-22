import { useEffect, useRef, useState } from 'react'
import { getDashboard } from './services/api.js'
import Dashboard from './components/Dashboard.jsx'
import ExpensesPanel from './components/ExpensesPanel.jsx'
import RecurrenceSettings from './components/RecurrenceSettings.jsx'
import Navigation from './components/Navigation.jsx'
import { pages } from './pages.js'
import { date } from './format.js'

const currentPage = () => Object.hasOwn(pages, window.location.hash.slice(1)) ? window.location.hash.slice(1) : 'overview'

export default function App() {
  const [page, setPage] = useState(currentPage)
  const [result, setResult] = useState({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [refreshMessage, setRefreshMessage] = useState('')
  const requestId = useRef(0)

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
      if (Object.hasOwn(pages, window.location.hash.slice(1))) { setPage(currentPage()); setRefreshMessage('') }
    }
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
      <header className="topbar"><div className="breadcrumb">Meu planejamento <span>/</span> <strong>{pages[page]}</strong></div><div className="topbar-meta">{result.data && <span>Referência <strong>{date(result.data.reference_date)}</strong></span>}<span className="avatar small" aria-label="Samuel">S</span></div></header>
      <main id="main-content" tabIndex="-1">
        {refreshMessage && <div className="dashboard-refresh"><p role="status">{refreshMessage}</p><button type="button" className="text-button" onClick={refreshDashboard}>Atualizar</button></div>}
        {result.status === 'ready' ? <>
          {page === 'overview' && <Dashboard data={result.data} />}
          {page === 'expenses' && <><div className="page-intro"><p className="eyebrow">ORGANIZAÇÃO DO DIA A DIA</p><h1>Seus compromissos, em ordem.</h1><p>Defina o que é essencial e acompanhe cada vencimento.</p></div><ExpensesPanel onChanged={refreshDashboard} /></>}
          {page === 'recurrences' && <RecurrenceSettings onChanged={refreshDashboard} />}
        </> : <section className="panel state-panel" aria-live="polite"><p className="eyebrow">MEU PLANEJAMENTO</p><h1>{result.status === 'loading' ? 'Preparando seu planejamento…' : result.status === 'empty' ? 'Seu planejamento começa aqui.' : 'Não foi possível carregar os dados.'}</h1>{result.message && <p role="status">{result.message}</p>}{result.status !== 'loading' && <button onClick={() => { setResult({ status: 'loading' }); setAttempt((value) => value + 1) }}>Tentar novamente</button>}</section>}
        <footer><span>agibank <strong>preventivo</strong></span><span>Previsibilidade para suas próximas escolhas.</span></footer>
      </main>
    </div>
  </div>
}
