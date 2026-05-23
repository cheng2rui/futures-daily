<template>
  <div class="metric-grid">
    <div class="metric-card accent-red">
      <div class="metric-label">综合温度</div>
      <div class="metric-main">{{ report.overview?.score ?? 0 }}</div>
      <div class="metric-sub">{{ report.overview?.heat || '暂无热度' }}</div>
    </div>
    <div class="metric-card accent-green">
      <div class="metric-label">上涨 / 下跌</div>
      <div class="metric-main">{{ dashboardMarket.up_count ?? 0 }} / {{ dashboardMarket.down_count ?? 0 }}</div>
      <div class="metric-sub">主力合约 {{ dashboardMarket.main_contracts ?? dashboardMarket.liquid_contracts ?? dashboardMarket.contracts ?? 0 }} 个</div>
    </div>
    <div class="metric-card accent-blue">
      <div class="metric-label">成交量</div>
      <div class="metric-main">{{ fmtNum(dashboardMarket.volume) }}</div>
      <div class="metric-sub">{{ activeDashboardMode === 'intraday' ? '最近一次更新' : '当日总成交' }}</div>
    </div>
    <div class="metric-card accent-orange">
      <div class="metric-label">数据完整度</div>
      <div class="metric-main">{{ qualityCoveragePct }}%</div>
      <div class="metric-sub">{{ qualityOkText }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  report: { type: Object, required: true },
  dashboardMarket: { type: Object, required: true },
  activeDashboardMode: { type: String, required: true },
  qualityCoveragePct: { type: [Number, String], default: 0 },
  qualityOkText: { type: String, default: '' },
})

function fmtNum(value) {
  if (value == null) return '-'
  const n = Number(value)
  if (!Number.isFinite(n)) return value
  if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(2)}亿`
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`
  return n.toFixed(0)
}
</script>

<style scoped>
.metric-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin:18px 0; }
.metric-card { background:#fff; border-radius:20px; padding:20px; box-shadow:0 12px 30px rgba(15,23,42,.07); border:1px solid #eef2f7; position:relative; overflow:hidden; }
.metric-card::after { content:''; position:absolute; inset:auto -30px -45px auto; width:120px; height:120px; border-radius:999px; opacity:.12; background:var(--accent); }
.accent-red { --accent:#e94560; } .accent-green { --accent:#16c79a; } .accent-blue { --accent:#3f5efb; } .accent-orange { --accent:#f5a623; }
.metric-label { color:#64748b; font-size:13px; font-weight:800; }
.metric-main { margin-top:8px; color:#0f172a; font-size:30px; font-weight:900; }
.metric-sub { margin-top:6px; color:#94a3b8; font-size:13px; }
@media (max-width:1100px) { .metric-grid { grid-template-columns:1fr 1fr; } }
@media (max-width:760px) { .metric-grid { grid-template-columns:1fr; } }
</style>
