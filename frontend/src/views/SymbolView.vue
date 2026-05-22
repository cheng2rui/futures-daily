<template>
  <div class="symbol-view">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ symbol }} 详情</h2>
        <p class="muted">来自 /api/markets/bars?symbol={{ symbol }} 的日行情数据</p>
      </div>
      <router-link to="/" class="back-link">返回今日</router-link>
    </div>

    <div class="kpi-row">
      <KpiCard label="记录数" :value="bars.length" color="#e94560" />
      <KpiCard label="最新收盘" :value="fmt(latest?.close)" color="#16c79a" />
      <KpiCard label="最高价" :value="fmt(stats.high)" color="#0f3460" />
      <KpiCard label="累计成交量" :value="fmt(stats.volume)" color="#f5a623" />
    </div>

    <SectionCard title="基础统计">
      <div v-if="loading" class="empty-state">正在加载 {{ symbol }} 行情...</div>
      <div v-else-if="!bars.length" class="empty-state">暂无 {{ symbol }} 日行情。可先生成日报或检查该品种是否已采集。</div>
      <div v-else class="info-grid">
        <div class="info-item"><label>最新交易日</label><span>{{ latest.trade_date }}</span></div>
        <div class="info-item"><label>交易所</label><span>{{ exchangeName(latest.exchange) }}</span></div>
        <div class="info-item"><label>最低价</label><span>{{ fmt(stats.low) }}</span></div>
        <div class="info-item"><label>累计持仓</label><span>{{ fmt(stats.openInterest) }}</span></div>
      </div>
    </SectionCard>

    <SectionCard title="日行情列表" style="margin-top: 16px;">
      <SimpleTable :columns="columns" :data="rows" />
    </SectionCard>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api.js'
import KpiCard from '../components/KpiCard.vue'
import SectionCard from '../components/SectionCard.vue'
import SimpleTable from '../components/SimpleTable.vue'
import { contractName, exchangeName } from '../exchange.js'

const route = useRoute()
const bars = ref([])
const loading = ref(false)
const symbol = computed(() => String(route.params.code || '').toUpperCase())
const latest = computed(() => bars.value[0] || null)
const columns = ['日期', '交易所', '合约', '开盘', '最高', '最低', '收盘', '成交量', '持仓量', '成交额']

const rows = computed(() => bars.value.map(x => [
  x.trade_date,
  exchangeName(x.exchange),
  contractName(x.contract, x.symbol),
  fmt(x.open),
  fmt(x.high),
  fmt(x.low),
  fmt(x.close),
  fmt(x.volume),
  fmt(x.open_interest),
  fmt(x.turnover),
]))

const stats = computed(() => {
  const nums = (key) => bars.value.map(x => Number(x[key])).filter(Number.isFinite)
  const highs = nums('high')
  const lows = nums('low')
  return {
    high: highs.length ? Math.max(...highs) : null,
    low: lows.length ? Math.min(...lows) : null,
    volume: nums('volume').reduce((sum, n) => sum + n, 0),
    openInterest: nums('open_interest').reduce((sum, n) => sum + n, 0),
  }
})

function fmt(value) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  if (!Number.isFinite(num)) return value
  return Math.abs(num) >= 10000 ? Math.round(num).toLocaleString() : num.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

async function load() {
  if (!symbol.value) return
  loading.value = true
  try {
    const { data } = await api.get('/markets/bars', { params: { symbol: symbol.value, limit: 300 } })
    bars.value = data || []
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(symbol, load)
</script>

<style scoped>
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.page-title { color: #1a1a2e; }
.muted { color: #888; margin-top: 4px; }
.back-link { color: #e94560; font-weight: 700; text-decoration: none; }
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
.info-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.info-item { display: flex; flex-direction: column; gap: 4px; padding: 16px; background: #fafafa; border-radius: 10px; }
.info-item label { font-size: 12px; color: #888; }
.info-item span { font-size: 18px; font-weight: 700; color: #1a1a2e; }
.empty-state { padding: 28px; text-align: center; color: #888; background: #fafafa; border-radius: 10px; }
@media (max-width: 900px) { .kpi-row, .info-grid { grid-template-columns: 1fr; } .page-head { align-items: flex-start; gap: 12px; flex-direction: column; } }
</style>
