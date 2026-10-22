export async function getHealth(signal) {
  const response = await fetch('/api/health/', {
    signal,
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new Error('Não foi possível conectar ao serviço.')
  }
  const data = await response.json()
  if (data.status !== 'ok' || data.service !== 'agibank-preventivo') {
    throw new Error('O serviço retornou uma resposta inesperada.')
  }
  return data
}

export async function getDashboard(signal) {
  const response = await fetch('/api/dashboard/', { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const error = new Error(payload?.message || 'Não foi possível carregar o planejamento. Confira a conexão com o backend.')
    error.code = payload?.code
    throw error
  }
  return response.json()
}

async function expenseRequest(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...options,
    headers: { Accept: 'application/json', ...options.headers },
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const error = new Error(response.status === 403 ? 'A sessão de segurança expirou. Atualize a página e tente novamente.' : payload?.message || 'Não foi possível acessar as despesas. Tente novamente.')
    error.fields = payload?.errors || {}
    throw error
  }
  return payload
}

export const getExpenses = (signal) => expenseRequest('/api/expenses/', { signal })

async function writeExpense(path, method, expense, signal) {
  let token = document.cookie.split('; ').find((cookie) => cookie.startsWith('csrftoken='))?.slice('csrftoken='.length)
  if (!token) {
    await getExpenses(signal)
    token = document.cookie.split('; ').find((cookie) => cookie.startsWith('csrftoken='))?.slice('csrftoken='.length)
  }
  return expenseRequest(path, {
    method, signal,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token || '' },
    body: JSON.stringify(expense),
  })
}

export const createExpense = (expense, signal) => writeExpense('/api/expenses/', 'POST', expense, signal)
export const updateExpense = (id, expense, signal) => writeExpense(`/api/expenses/${id}/`, 'PATCH', expense, signal)
export const cancelExpense = (id, scope, signal) => writeExpense(`/api/expenses/${id}/cancel/`, 'POST', { scope }, signal)
export const deleteExpense = (id, signal) => writeExpense(`/api/expenses/${id}/`, 'DELETE', {}, signal)
export const getExpense = (id, signal) => expenseRequest(`/api/expenses/${id}/`, { signal })
