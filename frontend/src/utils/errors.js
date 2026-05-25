export function normalizeError(value, limit = 120) {
  const text = String(value || 'unknown').replace(/\s+/g, ' ').trim()
  if (text.includes('fallback unavailable')) return '备用数据也拿不到，需要等交易所恢复或接商业数据'
  if (text.includes('not_collected')) return '未采集到数据'
  if (text.includes('timeout')) return '请求超时'
  if (text.includes('Network Error')) return '网络连接失败'
  return text.slice(0, limit)
}

export function normalizeApiError(err, fallback = '请求失败') {
  const data = err?.response?.data
  const detail = Array.isArray(data?.detail)
    ? data.detail.map(x => x?.msg || x?.message || JSON.stringify(x)).join('；')
    : data?.detail
  return normalizeError(detail || data?.message || data?.error || err?.message || fallback)
}
