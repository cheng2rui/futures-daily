export const STATUS_LABELS = {
  ok: '正常',
  missing: '缺失',
  partial: '部分覆盖',
  fallback: '备用源',
  not_supported: '不适用',
  unsupported: '不适用',
  unrecoverable: '暂时拿不到',
  failed: '失败',
  open: '待处理',
  resolved: '已解决',
  warning: '警告',
  error: '错误',
  success: '成功',
  running: '运行中',
}

export const KIND_LABELS = {
  daily: '日行情',
  seat_rank: '席位排名',
  archive_signal: '席位变化',
  capital_flow: '资金流向',
  basis: '现货价差',
  warehouse_receipt: '仓单变化',
  event_calendar: '事件日历',
  history_holding: '历史持仓',
  quhe_history_holding: '历史持仓',
  warehouse_receipt_official: '交易所仓单',
  basis_100ppi: '现货价差',
  seat_rank_fallback: '备用席位数据',
}

export const REASON_LABELS = {
  archive_inactive_or_illiquid: '冷门或成交太少，暂不统计',
  archive_source_not_covering_financial: '金融期货暂不提供这类席位整理',
  archive_source_not_covering_ine: '能源中心暂不提供这类席位整理',
  archive_mapping_or_source_gap: '品种映射还没对上，需要检查',
  external_inactive_or_illiquid: '冷门或成交太少，暂不统计',
  external_not_applicable_financial: '金融期货不适合看这项数据',
  external_not_applicable_index: '指数品种不适合看这项数据',
  external_source_gap: '这个数据源还没接上',
  external_source_not_covering_basis_sparse: '当前暂缺现货价差数据',
  external_source_not_covering_dce_warehouse: '大商所仓单数据暂缺',
  external_source_not_covering_financial: '金融期货暂缺这项数据',
  external_source_not_covering_ine: '能源中心暂缺这项数据',
  external_source_not_covering_new_variety: '新品种历史数据还不够',
  external_third_party_empty: '外部数据暂时没有返回',
  inactive_or_illiquid: '冷门、停用或成交太少',
  third_party_empty: '外部数据暂时为空',
  daily_not_collected: '当天行情还没拿到',
  unknown_daily_gap: '行情缺失，原因待确认',
  materialize_mapping_issue: '品种归类需要检查',
  third_party_mapping_missing: '外部数据品种没匹配上',
  fallback_untried_or_empty: '备用数据暂时也没有',
}

export function statusLabel(value) {
  const key = String(value || '').toLowerCase()
  return STATUS_LABELS[key] || value || '-'
}

export function kindLabel(value) {
  const key = String(value || '')
  return KIND_LABELS[key] || value || '-'
}

export function reasonLabel(value) {
  const key = String(value || '')
  return REASON_LABELS[key] || value || '-'
}
