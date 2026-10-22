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
