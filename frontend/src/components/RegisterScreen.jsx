import { useRef, useState } from 'react'
import { registerAccount } from '../services/api.js'

export default function RegisterScreen({ onRegistered }) {
  const [values, setValues] = useState({ name: '', email: '', password: '', password_confirmation: '' })
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const submitting = useRef(false)
  async function submit(event) {
    event.preventDefault()
    if (submitting.current) return
    if (values.password !== values.password_confirmation) { setErrors({ password_confirmation: ['As senhas não coincidem.'] }); return }
    submitting.current = true; setBusy(true); setErrors({}); setMessage('')
    try {
      const data = await registerAccount(values, AbortSignal.timeout(15000))
      onRegistered(data.user)
    } catch (error) { setMessage(error.message); setErrors(error.fields || {}) }
    finally { submitting.current = false; setBusy(false) }
  }
  const fields = [['name', 'Nome completo', 'text', 'name'], ['email', 'E-mail', 'email', 'email'], ['password', 'Senha', showPassword ? 'text' : 'password', 'new-password'], ['password_confirmation', 'Confirmar senha', showPassword ? 'text' : 'password', 'new-password']]
  return <main className="auth-page"><section className="auth-brand-panel"><a href="#" className="auth-brand" aria-label="Agibank Fluxo">agibank <span>FLUXO</span></a><div><p className="eyebrow">UM PASSO À FRENTE</p><h2>Seu dinheiro.<br />Seu planejamento.</h2><p>Mais clareza para organizar seus compromissos e cuidar das suas próximas decisões.</p></div><span>Previsibilidade para o seu dia a dia.</span></section><section className="auth-content" aria-labelledby="register-title"><div className="auth-card"><p className="eyebrow">BEM-VINDO AO AGIBANK FLUXO</p><h1 id="register-title">Crie sua conta</h1><p className="muted">Cadastre-se para organizar suas despesas e acompanhar sua renda em um só lugar.</p>
    {message && <p className="form-error" role="alert">{message}</p>}
    <form onSubmit={submit}><fieldset disabled={busy}>{fields.map(([key, label, type, autocomplete]) => <label key={key} htmlFor={`register-${key}`}>{label}<input id={`register-${key}`} type={type} autoComplete={autocomplete} value={values[key]} onChange={(event) => setValues((old) => ({ ...old, [key]: event.target.value }))} maxLength={key === 'name' || key === 'email' ? 150 : 128} minLength={key.startsWith('password') ? 8 : undefined} required aria-invalid={!!errors[key]} aria-describedby={errors[key] ? `error-${key}` : key === 'password' ? 'password-hint' : undefined} />{errors[key] && <span id={`error-${key}`} className="field-error">{errors[key].join(' ')}</span>}</label>)}<p id="password-hint" className="muted">Use pelo menos oito caracteres. Evite senhas comuns, apenas números ou informações pessoais.</p><label className="auth-show-password"><input type="checkbox" checked={showPassword} onChange={(event) => setShowPassword(event.target.checked)} />Mostrar senhas</label><button type="submit" className="auth-submit">{busy ? 'Criando sua conta…' : 'Criar conta'}</button></fieldset></form><p className="muted">Sua conta terá um planejamento separado, acessível somente durante sua sessão.</p></div></section></main>
}
