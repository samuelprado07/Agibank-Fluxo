export default function AssumptionsPanel({ assumptions, warnings }) {
  return <section className="panel assumptions-panel" aria-labelledby="assumptions-title">
    <p className="eyebrow">ENTENDA ESTA ESTIMATIVA</p><h2 id="assumptions-title">Premissas e limites dos dados</h2>
    <div className="assumptions-grid"><div><h3>Como calculamos</h3><ul>{assumptions.map((item) => <li key={item}>{item}</li>)}</ul></div>
      <div><h3>O que merece sua atenção</h3>{warnings.length ? <ul>{warnings.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Sem inconsistências adicionais identificadas nos dados considerados.</p>}<p className="estimate-note">A projeção depende dos lançamentos cadastrados. Recebimentos e resultados futuros não são garantidos.</p></div></div>
  </section>
}
