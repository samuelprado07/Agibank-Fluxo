import { useEffect, useState } from 'react'
import { getDashboard } from './services/api.js'
import Dashboard from './components/Dashboard.jsx'

export default function App() {
  const [result, setResult] = useState({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    let active = true

    getDashboard(controller.signal)
      .then((data) => { if (active) setResult({ status: 'ready', data }) })
      .catch((error) => { if (active) setResult({ status: error.code === 'no_scenario' ? 'empty' : 'error', message: error.name === 'AbortError' ? 'A conexão demorou mais que o esperado. Tente novamente.' : error.message }) })
      .finally(() => window.clearTimeout(timeout))

    return () => {
      active = false
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [attempt])

  return <>
    <header className="site-header"><div className="header-inner"><a className="brand" href="/" aria-label="Agibank Preventivo, início"><span className="brand-symbol" aria-hidden="true">a</span><span>agibank <strong>preventivo</strong></span></a><span className="badge">Demonstração local</span></div></header>
    <main>
      {result.status === 'ready' ? <Dashboard data={result.data} /> : <section className="panel state-panel" aria-live="polite">
        <p className="eyebrow">SEU PLANEJAMENTO</p>
        <h1>{result.status === 'loading' ? 'Preparando seu dashboard…' : result.status === 'empty' ? 'Seu cenário ainda não foi carregado' : 'Não conseguimos carregar o dashboard'}</h1>
        {result.message && <p role="status">{result.message}</p>}
        {result.status === 'empty' && <p>Carregue os dados fictícios pelo comando <code>manage.py load_demo</code> no backend.</p>}
        {result.status !== 'loading' && <button onClick={() => { setResult({ status: 'loading' }); setAttempt((value) => value + 1) }}>Tentar novamente</button>}
      </section>}
      <footer>Planejamento para cuidar do seu amanhã. <span>Dados fictícios · Sem acesso a contas reais</span></footer>
    </main>
  </>
}
