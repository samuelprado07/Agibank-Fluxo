import { useEffect, useState } from 'react'
import { getHealth } from './services/api.js'

export default function App() {
  const [connection, setConnection] = useState('loading')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    let active = true

    getHealth(controller.signal)
      .then(() => { if (active) setConnection('connected') })
      .catch(() => { if (active) setConnection('error') })
      .finally(() => window.clearTimeout(timeout))

    return () => {
      active = false
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [attempt])

  const messages = {
    loading: 'Verificando conexão com o serviço…',
    connected: 'Conexão estabelecida com o serviço.',
    error: 'Não foi possível conectar. Confira se o backend está em execução e tente novamente.',
  }

  return (
    <main>
      <header>
        <span className="brand">Agibank Preventivo</span>
        <span className="badge">Ambiente demonstrativo</span>
      </header>
      <section aria-labelledby="welcome-title">
        <p className="eyebrow">Planejamento financeiro preventivo</p>
        <h1 id="welcome-title">Mais clareza para planejar seus próximos passos.</h1>
        <p className="intro">
          Acompanhe seus compromissos e perceba possíveis dificuldades com antecedência.
          Este projeto está na etapa de preparação do ambiente.
        </p>
        <div className={`connection ${connection}`}>
          <h2>Conexão do ambiente</h2>
          <p role="status" aria-live="polite">{messages[connection]}</p>
          {connection === 'error' && (
            <button onClick={() => {
              setConnection('loading')
              setAttempt((value) => value + 1)
            }}>Tentar novamente</button>
          )}
        </div>
        <p className="notice">
          Demonstração local, sem acesso a contas reais. O dashboard, as projeções
          e o assistente serão implementados nas próximas etapas.
        </p>
      </section>
    </main>
  )
}
