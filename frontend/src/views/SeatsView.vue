<template>
  <div class="seats">
    <div class="page-head">
      <div>
        <h2 class="page-title">席位日报</h2>
        <p class="muted">{{ report.date || '暂无日期' }} ｜ 席位数据来自交易所公开排名 + 已有 rsstsx 结构化归档增强。</p>
      </div>
    </div>

    <div class="filters">
      <input v-model="filters.variety" placeholder="品种，如 RB / 玻璃 / IC" />
      <input v-model="filters.seat" placeholder="席位，如 中信 / 乾坤 / 摩根" />
      <select v-model="filters.exchange">
        <option value="">全部交易所</option>
        <option v-for="item in exchangeItems" :key="item.code" :value="item.code">{{ item.name }}</option>
      </select>
      <select v-model.number="filters.days">
        <option :value="3">近 3 日</option>
        <option :value="5">近 5 日</option>
        <option :value="10">近 10 日</option>
        <option :value="20">近 20 日</option>
      </select>
      <button @click="loadAll">筛选</button>
    </div>

    <div v-if="loading" class="notice">正在加载席位数据...</div>
    <div v-else-if="!hasAnySeatData" class="notice">暂无席位数据。可先生成日报；部分交易所/品种不披露席位排名时会保持为空。</div>

    <SectionCard title="Focus5 连续动作">
      <div class="section-note">来自你原先席位日报的结构化归档：乾坤 / 永安 / 摩根 / 瑞银 / 混沌，按净变化绝对值排序。</div>
      <div v-if="!trendRows.length" class="empty-state">暂无 Focus5 连续动作。可筛选具体席位或品种查看。</div>
      <SimpleTable v-else :columns="trendColumns" :data="trendRows" />
    </SectionCard>

    <div class="grid-2">
      <SectionCard title="净多变化 TOP">
        <SimpleTable :columns="archiveColumns" :data="netLongRows" />
      </SectionCard>
      <SectionCard title="净空变化 TOP">
        <SimpleTable :columns="archiveColumns" :data="netShortRows" />
      </SectionCard>
    </div>

    <SectionCard title="关注席位动向" style="margin-top: 16px;">
      <div v-if="!watchRows.length" class="empty-state">暂无关注席位动向。可在设置中维护关注席位，或等待席位排名采集完成。</div>
      <SimpleTable v-else :columns="watchColumns" :data="watchRows" />
    </SectionCard>

    <div class="grid-2">
      <SectionCard title="增多席位 TOP">
        <SimpleTable :columns="seatColumns" :data="longRows" />
      </SectionCard>
      <SectionCard title="增空席位 TOP">
        <SimpleTable :columns="seatColumns" :data="shortRows" />
      </SectionCard>
    </div>
    <SectionCard title="席位明细" style="margin-top: 16px;">
      <SimpleTable :columns="detailColumns" :data="detailRows" />
    </SectionCard>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api.js'
import SectionCard from '../components/SectionCard.vue'
import SimpleTable from '../components/SimpleTable.vue'
import { contractName, exchangeName, exchangeOptions } from '../exchange.js'

const loading = ref(false)
const report = ref({ seats: {} })
const details = ref([])
const archiveHistory = ref({ trend: [] })
const filters = ref({ variety: '', seat: '', exchange: '', days: 5 })
const seatColumns = ['交易所', '品种', '合约', '席位', '持仓', '变化']
const watchColumns = ['交易所', '品种', '合约', '多头席位', '多头变化', '空头席位', '空头变化']
const detailColumns = ['日期', '交易所', '品种', '排名', '多头席位', '多头变化', '空头席位', '空头变化']
const trendColumns = ['日期', '席位', '品种', '交易所', '净变化', '净头寸']
const archiveColumns = ['品种', '交易所', '多空比', '净变化', '方向', '多CR5', '空CR5']
const exchangeItems = exchangeOptions(['DCE', 'CZCE', 'SHFE', 'CFFEX', 'GFEX', 'INE'])

const archive = computed(() => report.value.seats?.archive || {})
const longRows = computed(() => (report.value.seats?.long_increase_top || []).map(row))
const shortRows = computed(() => (report.value.seats?.short_increase_top || []).map(row))
const watchRows = computed(() => (report.value.seats?.watchlist || []).map(x => [exchangeName(x.exchange), x.variety, contractName(x.contract, x.variety), x.long_party_name || '-', fmtSigned(x.long_open_interest_chg), x.short_party_name || '-', fmtSigned(x.short_open_interest_chg)]))
const detailRows = computed(() => details.value.map(x => [x.trade_date, exchangeName(x.exchange), x.variety, x.rank, x.long_party_name || '-', fmtSigned(x.long_open_interest_chg), x.short_party_name || '-', fmtSigned(x.short_open_interest_chg)]))
const trendRows = computed(() => (archiveHistory.value.trend || []).map(x => [formatDate(x.date), x.seat, x.variety, exchangeName(x.exchange), fmtSigned(x.netDelta), fmtSigned(x.netVol)]))
const netLongRows = computed(() => (archive.value.long_bias || []).slice(0, 8).map(archiveRow))
const netShortRows = computed(() => (archive.value.short_bias || []).slice(0, 8).map(archiveRow))
const hasAnySeatData = computed(() => longRows.value.length || shortRows.value.length || watchRows.value.length || detailRows.value.length || trendRows.value.length)

function row(x) { return [exchangeName(x.exchange), x.variety, contractName(x.contract, x.variety), x.seat, x.value ?? '-', fmtSigned(x.change)] }
function archiveRow(x) { return [x.displayName || x.name, exchangeName(x.exchange), x.longShortRatio ?? '-', fmtSigned(x.netDelta), x.netDir || '-', `${x.longCR5 ?? '-'}%`, `${x.shortCR5 ?? '-'}%`] }
function fmtSigned(v) { if (v == null) return '-'; const n = Number(v); if (!Number.isFinite(n)) return v; return n > 0 ? `+${n}` : String(n) }
function formatDate(v) { const s = String(v || ''); return /^\d{8}$/.test(s) ? `${s.slice(4, 6)}-${s.slice(6)}` : s }

async function loadDetails() {
  const params = { limit: 200 }
  if (filters.value.variety) params.variety = filters.value.variety
  if (filters.value.seat) params.seat = filters.value.seat
  if (filters.value.exchange) params.exchange = filters.value.exchange
  const rows = await api.get('/seats/rank-rows', { params })
  details.value = rows.data || []
}

async function loadArchiveHistory() {
  const date = report.value.date
  if (!date) return
  const params = { days: filters.value.days }
  if (filters.value.variety) params.variety = filters.value.variety
  if (filters.value.seat) params.seat = filters.value.seat
  const { data } = await api.get(`/seat-archive/${date}/history`, { params })
  archiveHistory.value = data || { trend: [] }
}

async function loadAll() {
  loading.value = true
  try {
    const latest = await api.get('/reports/latest')
    report.value = latest.data || { seats: {} }
    await Promise.all([loadDetails(), loadArchiveHistory()])
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-title { color: #1a1a2e; }
.muted { color: #888; margin-top: 4px; line-height: 1.6; }
.filters { display: grid; grid-template-columns: 1fr 1fr 160px 120px auto; gap: 8px; margin-bottom: 16px; }
.filters input, .filters select { border: 1px solid #ddd; border-radius: 8px; padding: 9px 10px; }
.filters button { background: #e94560; border: 0; color: white; border-radius: 8px; padding: 9px 14px; cursor: pointer; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
.notice { margin-bottom: 16px; padding: 11px 14px; background: #f6f8ff; color: #526184; border: 1px solid #e4e9ff; border-radius: 10px; }
.empty-state { padding: 24px; text-align: center; color: #888; background: #fafafa; border-radius: 10px; }
.section-note { color: #888; font-size: 13px; margin-bottom: 10px; }
@media (max-width: 900px) { .grid-2, .filters { grid-template-columns: 1fr; } }
</style>
