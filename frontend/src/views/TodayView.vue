<template>
  <div class="today">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ viewingDate ? '历史期货日报' : '今日期货日报' }}</h2>
        <p class="muted">{{ displayDate }} ｜ {{ report.meta?.generated_at || '暂无生成时间' }}</p>
      </div>
      <div class="actions">
        <router-link v-if="viewingDate" to="/" class="secondary">查看最新</router-link>
        <button class="primary" :disabled="loading" @click="generate">{{ loading ? '生成中...' : '生成日报' }}</button>
      </div>
    </div>

    <div v-if="error" class="notice error">{{ error }}</div>
    <div v-else-if="sourceTip" class="notice">{{ sourceTip }}</div>

    <SectionCard :title="report.overview?.stage || '暂无数据'">
      <div v-if="isEmptyReport" class="empty-state">
        暂无日报数据。点击右上角「生成日报」采集行情并生成概览。
      </div>
      <template v-else>
        <p class="summary">{{ report.overview?.summary }}</p>
        <div v-if="report.risk_flags?.length" class="flags">
          <div v-for="flag in report.risk_flags" :key="flag" class="flag">⚠ {{ flag }}</div>
        </div>
      </template>
    </SectionCard>

    <div class="kpi-row">
      <KpiCard label="综合分" :value="report.overview?.score ?? 0" color="#e94560" />
      <KpiCard label="上涨品种" :value="report.market?.up_count ?? 0" color="#16c79a" />
      <KpiCard label="下跌品种" :value="report.market?.down_count ?? 0" color="#0f3460" />
      <KpiCard label="数据覆盖" :value="report.data_quality?.coverage_pct ?? 0" unit="%" color="#f5a623" />
    </div>

    <SectionCard title="自选品种">
      <div v-if="!watchRows.length" class="empty-state small">暂无自选品种数据。可在设置中维护关注品种，或等待行情采集完成。</div>
      <SimpleTable v-else :columns="rankColumns" :data="watchRows" />
    </SectionCard>

    <SectionCard title="数据质量" style="margin-top:16px">
      <SimpleTable :columns="['交易所', '状态', '日行情', '席位', '错误']" :data="qualityRows" />
    </SectionCard>

    <SectionCard title="板块强弱" style="margin-top:16px">
      <SimpleTable :columns="['板块', '平均涨跌幅', '合约数']" :data="sectorRows" />
    </SectionCard>

    <SectionCard title="板块广度" style="margin-top:16px">
      <SimpleTable :columns="['板块', '合约数', '上涨', '下跌', '上涨占比', '成交量', '持仓量']" :data="breadthRows" />
    </SectionCard>

    <SectionCard title="席位结构信号" style="margin-top:16px">
      <div v-if="!seatSignalRows.length" class="empty-state small">暂无结构化席位信号。</div>
      <SimpleTable v-else :columns="['交易所', '品种', '净变化', '多空比', 'CR5', '方向']" :data="seatSignalRows" />
    </SectionCard>

    <div class="grid-2">
      <SectionCard title="涨幅 TOP10">
        <SimpleTable :columns="rankColumns" :data="gainerRows" />
      </SectionCard>
      <SectionCard title="跌幅 TOP10">
        <SimpleTable :columns="rankColumns" :data="loserRows" />
      </SectionCard>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api.js'
import KpiCard from '../components/KpiCard.vue'
import SectionCard from '../components/SectionCard.vue'
import SimpleTable from '../components/SimpleTable.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const error = ref('')
const report = ref(emptyReport())
const rankColumns = ['交易所', '品种', '合约', '板块', '收盘', '涨跌幅']
const viewingDate = computed(() => route.query.date ? String(route.query.date) : '')
const displayDate = computed(() => formatDate(report.value.date || viewingDate.value) || '暂无日期')
const isEmptyReport = computed(() => !report.value.date && !report.value.overview?.summary)

const watchRows = computed(() => rows(report.value.watch_symbols))
const sectorRows = computed(() => (report.value.sectors || []).map(x => [x.name, `${x.avg_change}%`, x.count]))
const breadthRows = computed(() => (report.value.structure?.sector_breadth || []).map(x => [x.name, x.count, x.up, x.down, `${x.up_ratio}%`, fmtNum(x.volume), fmtNum(x.open_interest)]))
const gainerRows = computed(() => rows(report.value.rankings?.gainers))
const loserRows = computed(() => rows(report.value.rankings?.losers))
const seatSignalRows = computed(() => (report.value.seats?.archive?.net_delta_top || []).slice(0, 8).map(x => [x.exchange, x.displayName || x.name, fmtSigned(x.netDelta), x.longShortRatio || '-', `${x.longCR5 ?? '-'} / ${x.shortCR5 ?? '-'}`, x.netDir || '-']))
const qualityRows = computed(() => (report.value.data_quality?.exchanges || []).map(x => [
  x.exchange,
  x.status,
  x.daily?.rows ?? 0,
  x.seat_rank?.rows ?? 0,
  x.daily?.error || x.seat_rank?.error || '-'
]))
const sourceTip = computed(() => {
  const quality = report.value.data_quality
  if (!quality || quality.status === 'empty') return ''
  const bad = (quality.exchanges || []).filter(x => x.status !== 'ok')
  if (!bad.length) return `数据来源：交易所/AKShare，覆盖 ${quality.coverage_pct ?? 0}%，未触发明显 fallback。`
  return `数据来源提示：${bad.map(x => `${x.exchange} ${x.status}`).join('、')}；部分交易所可能使用 fallback 或暂无数据。`
})

function emptyReport() {
  return { overview: {}, market: {}, meta: {}, sectors: [], rankings: {}, data_quality: {}, watch_symbols: [], risk_flags: [] }
}

function rows(items = []) {
  return (items || []).map(x => [x.exchange, x.symbol, x.contract, x.sector, x.close ?? '-', x.change_pct == null ? '-' : `${x.change_pct}%`])
}

function fmtSigned(v) { if (v == null) return '-'; const n = Number(v); return Number.isFinite(n) && n > 0 ? `+${n}` : `${v}` }

function fmtNum(value) {
  if (value == null) return '-'
  const n = Number(value)
  if (!Number.isFinite(n)) return value
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`
  return n.toFixed(0)
}

function formatDate(value) {
  if (!value) return ''
  const text = String(value)
  if (/^\d{8}$/.test(text)) return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6)}`
  return text
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const url = viewingDate.value ? `/reports/${viewingDate.value}` : '/reports/latest'
    const { data } = await api.get(url)
    report.value = data || emptyReport()
  } catch (err) {
    report.value = emptyReport()
    error.value = viewingDate.value ? `未找到 ${formatDate(viewingDate.value)} 的日报。` : '日报加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

async function generate() {
  loading.value = true
  error.value = ''
  try {
    await api.post('/reports/generate', null, { params: viewingDate.value ? { trade_date: viewingDate.value } : {} })
    if (viewingDate.value) await router.replace('/')
    await load()
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => route.query.date, load)
</script>

<style scoped>
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.page-title { color: #1a1a2e; }
.muted { color: #888; margin-top: 4px; }
.actions { display: flex; gap: 10px; align-items: center; }
.summary { font-size: 16px; line-height: 1.7; color: #333; }
.flags { margin-top: 12px; display: grid; gap: 8px; }
.flag { background: #fff7e6; border: 1px solid #ffd591; color: #8a5200; padding: 8px 10px; border-radius: 8px; }
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 16px 0; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
.primary { background: #e94560; color: white; border: 0; border-radius: 10px; padding: 10px 16px; font-weight: 700; cursor: pointer; }
.secondary { background: #fff; color: #e94560; border: 1px solid #ffd4dc; border-radius: 10px; padding: 9px 14px; font-weight: 700; text-decoration: none; }
.primary:disabled { opacity: .6; cursor: wait; }
.notice { margin-bottom: 16px; padding: 11px 14px; background: #f6f8ff; color: #526184; border: 1px solid #e4e9ff; border-radius: 10px; }
.notice.error { background: #fff0f0; color: #bd3434; border-color: #ffd6d6; }
.empty-state { padding: 28px; text-align: center; color: #888; background: #fafafa; border-radius: 10px; }
.empty-state.small { padding: 18px; }
@media (max-width: 900px) { .kpi-row, .grid-2 { grid-template-columns: 1fr; } .page-head { align-items: flex-start; gap: 12px; flex-direction: column; } }
</style>
