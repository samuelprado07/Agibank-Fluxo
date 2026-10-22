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
