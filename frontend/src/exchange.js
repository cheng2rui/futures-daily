const EXCHANGE_NAMES = {
  SHFE: '上期所',
  DCE: '大商所',
  CZCE: '郑商所',
  CFFEX: '中金所',
  GFEX: '广期所',
  INE: '上期能源',
  ALL: '全部',
}

export function exchangeName(code) {
  const key = String(code || '').toUpperCase()
  return EXCHANGE_NAMES[key] || code || '-'
}

export function exchangeOptions(codes = []) {
  return codes.map(code => ({ code, name: exchangeName(code) }))
}
