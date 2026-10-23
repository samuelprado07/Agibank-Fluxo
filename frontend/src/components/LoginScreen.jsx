import { useRef, useState } from 'react'
import { getSession, loginAccount } from '../services/api.js'
import AuthLayout from './AuthLayout.jsx'

export default function LoginScreen({ onSignedIn }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [errors, setErrors] = useState({})
  const submitting = useRef(false)
  const alert = useRef(null)
  async function submit(event) {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true; setBusy(true); setMessage(''); setErrors({})
    try {
      const data = await loginAccount({ email, password }, AbortSignal.timeout(15000))
      setPassword('')
      onSignedIn(data.user)
    } catch (error) {
      // A lost response does not mean the server failed to create the session.
      try {
        const session = await getSession(AbortSignal.timeout(5000))
        if (session.user) {
          setPassword('')
          onSignedIn(session.user)
          return
        }
      } catch { /* Keep the original login error if session recovery also fails. */ }
      setMessage(error.name === 'TimeoutError' ? 'A consulta demorou mais que o esperado. Tente entrar novamente.' : error.message)
      setErrors(error.fields || {})
      window.requestAnimationFrame(() => alert.current?.focus())
    } finally { submitting.current = false; setBusy(false) }
  }
  return <AuthLayout title="Entre na sua conta" titleId="login-title" description="Acesse seu planejamento e continue cuidando das suas próximas decisões.">
    {message && <p className="form-error" role="alert" tabIndex="-1" ref={alert}>{message}</p>}
    <form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="login-email">E-mail<input id="login-email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={150} required aria-invalid={!!errors.email} aria-describedby={errors.email ? 'login-email-error' : undefined} />{errors.email && <span className="field-error" id="login-email-error">{errors.email.join(' ')}</span>}</label>
      <label htmlFor="login-password">Senha<input id="login-password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} maxLength={128} required aria-invalid={!!errors.password} aria-describedby={errors.password ? 'login-password-error' : undefined} />{errors.password && <span className="field-error" id="login-password-error">{errors.password.join(' ')}</span>}</label>
      <label className="auth-show-password"><input type="checkbox" checked={showPassword} onChange={(event) => setShowPassword(event.target.checked)} />Mostrar senha</label>
      <button type="submit" className="auth-submit">{busy ? 'Entrando…' : 'Entrar'}</button>
    </fieldset></form><p className="auth-switch">Ainda não tem uma conta? <a href="#register" aria-disabled={busy} onClick={(event) => { if (busy) event.preventDefault() }}>Criar conta</a></p>
  </AuthLayout>
}
