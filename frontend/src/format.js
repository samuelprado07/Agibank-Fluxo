export const money = (value) => value == null ? 'Não disponível' : new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(value))
export const date = (value) => value ? new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`)) : 'Não informado'
export const shortDate = (value) => date(value).slice(0, 5)
