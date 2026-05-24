<template>
  <div class="metric-grid">
    <div class="metric-card accent-red">
      <div class="metric-label">综合温度</div>
      <div class="metric-main">{{ report.overview?.score ?? 0 }}</div>
      <div class="metric-sub">{{ report.overview?.heat || '暂无热度' }}</div>
    </div>
    <div class="metric-card market-breadth-card">
      <div class="metric-label breadth-label"><span class="up-text">上涨</span> / <span class="down-text">下跌</span></div>
      <div class="breadth-body">
        <svg class="breadth-rings" viewBox="0 0 72 72" aria-hidden="true">
          <circle class="ring ring-up" cx="36" cy="36" r="28" :stroke-dasharray="upRing" stroke-dashoffset="18" />
          <circle class="ring ring-down" cx="36" cy="36" r="20" :stroke-dasharray="downRing" stroke-dashoffset="13" />
        </svg>
        <div class="breadth-number">
          <span class="up-text">{{ upCount }}</span><i>/</i><span class="down-text">{{ downCount }}</span>
        </div>
      </div>
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
import { computed } from 'vue'

const props = defineProps({
  report: { type: Object, required: true },
  dashboardMarket: { type: Object, required: true },
  activeDashboardMode: { type: String, required: true },
  qualityCoveragePct: { type: [Number, String], default: 0 },
  qualityOkText: { type: String, default: '' },
})

const upCount = computed(() => Number(props.dashboardMarket.up_count || 0))
const downCount = computed(() => Number(props.dashboardMarket.down_count || 0))
const breadthTotal = computed(() => Math.max(1, upCount.value + downCount.value))
const upRing = computed(() => ringDash(28, upCount.value / breadthTotal.value))
const downRing = computed(() => ringDash(20, downCount.value / breadthTotal.value))

function ringDash(radius, ratio) {
  const circumference = 2 * Math.PI * radius
  const visible = Math.max(0.08, Math.min(0.96, Number(ratio) || 0)) * circumference
  return `${visible.toFixed(1)} ${(circumference - visible).toFixed(1)}`
}

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
.accent-red { --accent:#e94560; } .accent-blue { --accent:#3f5efb; } .accent-orange { --accent:#f5a623; }
.metric-label { color:#64748b; font-size:13px; font-weight:800; }
.metric-main { margin-top:8px; color:#0f172a; font-size:30px; font-weight:900; }
.metric-sub { margin-top:6px; color:#94a3b8; font-size:13px; }
.market-breadth-card { --accent:#e94560; }
.breadth-label { color:#94a3b8; }
.breadth-body { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:6px; min-height:58px; }
.breadth-rings { width:66px; height:66px; flex:0 0 66px; overflow:visible; transform:rotate(-90deg); }
.ring { fill:none; stroke-linecap:round; }
.ring-up { stroke:#e03a3e; stroke-width:7; }
.ring-down { stroke:#16a05d; stroke-width:5; }
.breadth-number { display:flex; align-items:baseline; gap:7px; font-size:32px; font-weight:950; letter-spacing:-.04em; white-space:nowrap; }
.breadth-number i { color:#111827; font-style:normal; font-weight:850; font-size:.72em; }
.up-text { color:#e03a3e; }
.down-text { color:#16a05d; }
@media (max-width:1100px) { .metric-grid { grid-template-columns:1fr 1fr; } }
@media (max-width:760px) { .metric-grid { grid-template-columns:1fr; } }
</style>
