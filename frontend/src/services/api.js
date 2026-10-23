export async function getHealth(signal) {
  const response = await fetch('/api/health/', {
    signal,
    headers: { Accept: 'application/json' },
  })
  if (response.status === 401) window.dispatchEvent(new Event('agibank:session-expired'))
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
  if (response.status === 401) window.dispatchEvent(new Event('agibank:session-expired'))
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
  if (response.status === 401) window.dispatchEvent(new Event('agibank:session-expired'))
  if (!response.ok) {
    const error = new Error(response.status === 403 ? 'A sessão de segurança expirou. Atualize a página e tente novamente.' : payload?.message || 'Não foi possível acessar as despesas. Tente novamente.')
    error.fields = payload?.errors || {}
    error.status = response.status
    throw error
  }
  return payload
}

export const getExpenses = (signal) => expenseRequest('/api/expenses/', { signal })

async function writeExpense(path, method, expense, signal, bootstrap = getExpenses) {
  let token = document.cookie.split('; ').find((cookie) => cookie.startsWith('csrftoken='))?.slice('csrftoken='.length)
  if (!token) {
    await bootstrap(signal)
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
export const getRecurrences = (signal) => expenseRequest('/api/recurrences/', { signal })
export const getRecurrence = (id, signal) => expenseRequest(`/api/recurrences/${id}/`, { signal })
export const updateRecurrence = (id, values, signal) => writeExpense(`/api/recurrences/${id}/`, 'PATCH', values, signal)
export const stopRecurrence = (id, values, signal) => writeExpense(`/api/recurrences/${id}/cancel/`, 'POST', values, signal)

export async function savePayment(id, action, values, signal) {
  const result = await writeExpense(`/api/expenses/${id}/payment/${action === 'undo' ? 'undo/' : ''}`, action === 'correct' ? 'PATCH' : 'POST', values, signal)
  if (result?.occurrence_id !== id || !Number.isInteger(result?.payment?.version)) {
    throw new Error('Não foi possível confirmar o resultado. Reenvie a mesma operação para consultar a confirmação.')
  }
  return result
}

export const getIncomes = (signal) => expenseRequest('/api/incomes/', { signal })
export const getIncome = (id, signal) => expenseRequest(`/api/incomes/${id}/`, { signal })
export const createIncome = (values, signal) => writeExpense('/api/incomes/', 'POST', values, signal)
export const updateIncome = (id, values, signal) => writeExpense(`/api/incomes/${id}/`, 'PATCH', values, signal)
export const cancelIncome = (id, signal) => writeExpense(`/api/incomes/${id}/cancel/`, 'POST', {}, signal)
export const stopIncomeSeries = (id, values, signal) => writeExpense(`/api/income-recurrences/${id}/cancel/`, 'POST', values, signal)

export async function saveReceipt(id, action, values, signal) {
  const result = await writeExpense(`/api/incomes/${id}/receipt/${action === 'undo' ? 'undo/' : ''}`, action === 'correct' ? 'PATCH' : 'POST', values, signal)
  if (result?.occurrence_id !== id || !Number.isInteger(result?.receipt?.version)) {
    throw new Error('Não foi possível consultar a confirmação. Reenvie a mesma operação.')
  }
  return result
}

export const getSimulationContext = (signal) => expenseRequest('/api/simulations/context/', { signal })
export const previewSimulation = (values, signal) => writeExpense('/api/simulations/preview/', 'POST', values, signal, getSimulationContext)
export async function applySimulation(values, signal) {
  const result = await writeExpense('/api/simulations/apply/', 'POST', values, signal, getSimulationContext)
  if (result?.applied !== true || !Number.isInteger(result?.application_id)) throw new Error('Não foi possível confirmar a aplicação. Consulte a mesma operação novamente.')
  return result
}

export const getAssistantContext = (signal) => expenseRequest('/api/assistant/context/', { signal })
export const sendAssistantMessage = (values, signal) => writeExpense('/api/assistant/messages/', 'POST', values, signal, getAssistantContext)

export const getSession = (signal) => expenseRequest('/api/auth/me/', { signal })
export const registerAccount = (values, signal) => writeExpense('/api/auth/register/', 'POST', values, signal, getSession)
export const logoutAccount = (signal) => writeExpense('/api/auth/logout/', 'POST', {}, signal, getSession)
