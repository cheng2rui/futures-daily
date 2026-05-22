export const STATUS_LABELS = {
  ok: '正常',
  missing: '缺失',
  partial: '部分覆盖',
  unrecoverable: '不可恢复',
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
  archive_signal: '结构信号',
  capital_flow: '资金流',
  basis: '基差',
  warehouse_receipt: '仓单',
  history_holding: '历史多空持仓',
  quhe_history_holding: '曲合历史持仓',
  warehouse_receipt_official: '官方仓单',
  basis_100ppi: '100ppi基差',
  seat_rank_fallback: '席位备用源',
}

export const REASON_LABELS = {
  archive_inactive_or_illiquid: '归档未覆盖冷门/低流动性品种',
  archive_source_not_covering_financial: '归档源不覆盖金融期货',
  archive_source_not_covering_ine: '归档源不覆盖能源中心品种',
  archive_mapping_or_source_gap: '归档映射或源缺口',
  external_inactive_or_illiquid: '增强源不覆盖冷门/低流动性品种',
  external_not_applicable_financial: '金融期货不适用该数据',
  external_not_applicable_index: '指数品种不适用该数据',
  external_source_gap: '增强源待补缺口',
  external_source_not_covering_basis_sparse: '当前基差源不覆盖',
  external_source_not_covering_dce_warehouse: 'DCE仓单源不覆盖',
  external_source_not_covering_financial: '增强源不覆盖金融期货',
  external_source_not_covering_ine: '增强源不覆盖能源中心品种',
  external_source_not_covering_new_variety: '新品种历史源未沉淀',
  external_third_party_empty: '第三方接口为空',
  inactive_or_illiquid: '冷门/停用/低流动性',
  third_party_empty: '第三方源为空',
  daily_not_collected: '日行情未采集',
  unknown_daily_gap: '日行情未知缺口',
  materialize_mapping_issue: '物化映射问题',
  third_party_mapping_missing: '第三方映射缺失',
  fallback_untried_or_empty: '备用源未命中或为空',
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
