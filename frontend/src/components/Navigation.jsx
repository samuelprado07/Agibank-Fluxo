import { pages } from '../pages.js'

function Icon({ name }) {
  const paths = {
    overview: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    expenses: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z" /><path d="M9 8h6M9 12h6" /></>,
    recurrences: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2" /></>,
  }
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

export default function Navigation({ page }) {
  return <aside className="sidebar">
    <a className="brand" href="#overview" aria-label="Agibank Preventivo, início"><span className="brand-symbol">a</span><span>agibank<small>PREVENTIVO</small></span></a>
    <p className="nav-caption">MEU PLANEJAMENTO</p>
    <nav aria-label="Menu principal">{Object.entries(pages).map(([key, label]) => <a href={`#${key}`} key={key} className={`nav-link ${page === key ? 'active' : ''}`} aria-current={page === key ? 'page' : undefined}><Icon name={key} /><span>{label}</span>{page === key && <i aria-hidden="true" />}</a>)}</nav>
    <div className="sidebar-note"><span className="note-symbol" aria-hidden="true">↗</span><strong>Um passo à frente.</strong><p>Mais clareza para cuidar das suas próximas decisões.</p></div>
    <div className="sidebar-profile"><span className="avatar">S</span><div><strong>Samuel</strong><small>Meu planejamento financeiro</small></div></div>
  </aside>
}
