import { useState } from 'react'
import { pages } from '../pages.js'

export function Icon({ name }) {
  const paths = {
    overview: <path d="m3 11 9-8 9 8v10h-6v-7H9v7H3Z" />,
    expenses: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z" /><path d="M9 8h6M9 12h6" /></>,
    incomes: <><path d="M12 3v12m-4-4 4 4 4-4M4 15v5h16v-5" /></>,
    recurrences: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2" /></>,
    simulations: <><path d="M4 6h16M4 18h16M8 3v6M16 15v6M4 12h16M14 9v6" /></>,
    assistant: <><path d="M21 11a8 8 0 0 1-8 8H7l-5 3 2-6a8 8 0 1 1 17-5Z" /><path d="M8 10h8M8 14h5" /></>,
  }
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

export default function Navigation({ page, user, onLogout }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function signOut() {
    if (busy) return
    setBusy(true); setError('')
    try { await onLogout() } catch { setError('Não foi possível sair. Tente novamente.') }
    finally { setBusy(false) }
  }
  return <aside className="sidebar">
    <a className="brand" href="#overview" aria-label="Agibank Fluxo, início"><span className="brand-symbol">a</span><span>agibank<small>FLUXO</small></span></a>
    <p className="nav-caption">MEU PLANEJAMENTO</p>
    <nav aria-label="Menu principal">{Object.entries(pages).map(([key, label]) => <a href={`#${key}`} key={key} className={`nav-link ${page === key ? 'active' : ''}`} aria-current={page === key ? 'page' : undefined}><Icon name={key} /><span>{key === 'overview' ? 'Início' : key === 'incomes' ? 'Renda' : label}</span>{page === key && <i aria-hidden="true" />}</a>)}</nav>
    <div className="sidebar-note"><span className="note-symbol" aria-hidden="true">↗</span><strong>Um passo à frente.</strong><p>Mais clareza para cuidar das suas próximas decisões.</p></div>
    <div className="sidebar-profile"><span className="avatar">{user?.name.slice(0, 1).toUpperCase()}</span><div><strong>{user?.name}</strong><small>Meu planejamento financeiro</small></div></div>
    <div className="signout-area"><button className="text-button" type="button" disabled={busy} onClick={signOut}>{busy ? 'Saindo…' : 'Sair da conta'}</button>{error && <p className="field-error" role="alert">{error}</p>}</div>
  </aside>
}
