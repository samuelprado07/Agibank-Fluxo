import { useRef, useState } from 'react'
import { registerAccount } from '../services/api.js'
import AuthLayout from './AuthLayout.jsx'

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
  return <AuthLayout title="Crie sua conta" titleId="register-title" description="Cadastre-se para organizar suas despesas e acompanhar sua renda em um só lugar.">
    {message && <p className="form-error" role="alert">{message}</p>}
    <form onSubmit={submit}><fieldset disabled={busy}>{fields.map(([key, label, type, autocomplete]) => <label key={key} htmlFor={`register-${key}`}>{label}<input id={`register-${key}`} type={type} autoComplete={autocomplete} value={values[key]} onChange={(event) => setValues((old) => ({ ...old, [key]: event.target.value }))} maxLength={key === 'name' || key === 'email' ? 150 : 128} minLength={key.startsWith('password') ? 8 : undefined} required aria-invalid={!!errors[key]} aria-describedby={errors[key] ? `error-${key}` : key === 'password' ? 'password-hint' : undefined} />{errors[key] && <span id={`error-${key}`} className="field-error">{errors[key].join(' ')}</span>}</label>)}<p id="password-hint" className="muted">Use pelo menos oito caracteres. Evite senhas comuns, apenas números ou informações pessoais.</p><label className="auth-show-password"><input type="checkbox" checked={showPassword} onChange={(event) => setShowPassword(event.target.checked)} />Mostrar senhas</label><button type="submit" className="auth-submit">{busy ? 'Criando sua conta…' : 'Criar conta'}</button></fieldset></form><p className="muted">Sua conta terá um planejamento separado, acessível somente durante sua sessão.</p><p className="auth-switch">Já tem uma conta? <a href="#login" aria-disabled={busy} onClick={(event) => { if (busy) event.preventDefault() }}>Entrar</a></p></AuthLayout>
}
