<template>
  <div class="today">
    <div class="hero">
      <div>
        <div class="eyebrow">Futures Daily · {{ displayDate }}</div>
        <h1>{{ report.overview?.stage || (viewingDate ? '历史期货日报' : '今日期货日报') }}</h1>
        <p>{{ report.overview?.summary || '暂无日报数据。点击右上角生成日报，系统会采集行情、席位和结构化归档后生成市场概览。' }}</p>
      </div>
      <div class="actions">
        <router-link v-if="viewingDate" to="/" class="secondary">查看最新</router-link>
        <button class="primary" :disabled="loading" @click="generate">{{ generateButtonText }}</button>
      </div>
    </div>

    <div v-if="error" class="notice error">{{ error }}</div>
    <div v-else-if="sourceTip" class="notice">{{ sourceTip }}</div>

    <div class="metric-grid">
      <div class="metric-card accent-red"><div class="metric-label">综合温度</div><div class="metric-main">{{ report.overview?.score ?? 0 }}</div><div class="metric-sub">{{ report.overview?.heat || '暂无热度' }}</div></div>
      <div class="metric-card accent-green"><div class="metric-label">上涨 / 下跌</div><div class="metric-main">{{ report.market?.up_count ?? 0 }} / {{ report.market?.down_count ?? 0 }}</div><div class="metric-sub">主力合约 {{ report.market?.main_contracts ?? report.market?.liquid_contracts ?? report.market?.contracts ?? 0 }} 个</div></div>
      <div class="metric-card accent-blue"><div class="metric-label">成交量</div><div class="metric-main">{{ fmtNum(report.market?.volume) }}</div><div class="metric-sub">总成交</div></div>
      <div class="metric-card accent-orange"><div class="metric-label">数据覆盖</div><div class="metric-main">{{ report.data_quality?.coverage_pct ?? 0 }}%</div><div class="metric-sub">{{ qualityOkText }}</div></div>
    </div>

    <div v-if="isEmptyReport" class="empty-state large">暂无日报数据。建议先生成日报，再查看市场结构、席位信号和数据资产。</div>

    <template v-else>
      <div v-if="report.risk_flags?.length" class="risk-strip">
        <div v-for="flag in report.risk_flags" :key="flag" class="risk-chip">⚠ {{ flag }}</div>
      </div>

      <div v-if="reportBrief" class="brief-card">
        <div class="brief-title">{{ reportBrief.title }}</div>
        <p>{{ reportBrief.conclusion }}</p>
        <div class="brief-bullets">
          <div v-for="item in reportBrief.bullets" :key="item.label" class="brief-bullet">
            <b>{{ item.label }}</b>
            <span>{{ item.text }}</span>
          </div>
        </div>
      </div>

      <div class="layout-grid">
        <SectionCard title="市场风向">
          <div class="signal-stack">
            <div v-for="item in marketSignals" :key="item.label" class="signal-item"><span class="signal-name">{{ item.label }}</span><strong :class="item.tone">{{ item.value }}</strong></div>
          </div>
        </SectionCard>
        <SectionCard title="板块强弱 Top">
          <div class="sector-list">
            <div v-for="s in sectorStrengthTop" :key="s.name" class="sector-row">
              <div class="sector-head"><span>{{ s.name }}</span><b :class="toneClass(s.avg_change)">{{ signedPct(s.avg_change) }}</b></div>
              <div class="bar"><span :style="{ width: barWidth(s.avg_change), background: barColor(s.avg_change) }"></span></div>
            </div>
          </div>
        </SectionCard>
      </div>

      <div class="chart-grid">
        <SectionCard title="板块成交 / 持仓"><BaseChart :option="sectorVolumeOption" /></SectionCard>
        <SectionCard title="成交量 TOP10"><BaseChart :option="volumeTopOption" /></SectionCard>
      </div>
      <div class="chart-grid">
        <SectionCard title="席位多头增仓 TOP"><BaseChart :option="longSeatOption" /></SectionCard>
        <SectionCard title="席位空头增仓 TOP"><BaseChart :option="shortSeatOption" /></SectionCard>
      </div>

      <div class="layout-grid three">
        <SectionCard title="涨幅 TOP10"><SimpleTable :columns="rankColumns" :data="gainerRows" /></SectionCard>
        <SectionCard title="跌幅 TOP10"><SimpleTable :columns="rankColumns" :data="loserRows" /></SectionCard>
        <SectionCard title="结构信号 TOP">
          <div v-if="!seatSignalCards.length" class="empty-state small">暂无结构化席位信号。</div>
          <div v-else class="seat-cards">
            <div v-for="x in seatSignalCards" :key="`${x.exchange}-${x.name}`" class="seat-card">
              <div class="seat-title"><span>{{ x.name }}</span><em>{{ x.exchange }}</em></div>
              <div class="seat-main" :class="toneClass(x.netDelta)">{{ fmtSigned(x.netDelta) }}</div>
              <div class="seat-sub">多空比 {{ x.longShortRatio || '-' }} · 方向 {{ x.netDir || '-' }}</div>
            </div>
          </div>
        </SectionCard>
      </div>

      <SectionCard title="自选品种" style="margin-top:16px">
        <div v-if="!watchRows.length" class="empty-state small">暂无自选品种数据。可在设置中维护关注品种，或等待行情采集完成。</div>
        <SimpleTable v-else :columns="rankColumns" :data="watchRows" />
      </SectionCard>

      <div class="layout-grid" style="margin-top:16px">
        <SectionCard title="板块广度"><SimpleTable :columns="['板块', '合约数', '上涨', '下跌', '上涨占比', '成交量', '持仓量']" :data="breadthRows" /></SectionCard>
        <SectionCard title="数据质量"><SimpleTable :columns="['交易所', '状态', '日行情', '席位', '错误']" :data="qualityRows" /></SectionCard>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api.js'
import BaseChart from '../components/BaseChart.vue'
import SectionCard from '../components/SectionCard.vue'
import SimpleTable from '../components/SimpleTable.vue'
import { contractName, exchangeName } from '../exchange.js'
import { statusLabel } from '../labels.js'

const route = useRoute()
const loading = ref(false)
const error = ref('')
const report = ref(emptyReport())
const rankColumns = ['交易所', '品种', '合约', '板块', '收盘', '涨跌幅']
const viewingDate = computed(() => route.query.date ? String(route.query.date) : '')
const displayDate = computed(() => formatDate(report.value.date || viewingDate.value) || '暂无日期')
const isEmptyReport = computed(() => !report.value.date && !report.value.overview?.summary)
const generateButtonText = computed(() => {
  if (loading.value) return viewingDate.value ? '抓取中...' : '生成中...'
  return viewingDate.value ? '抓取信息并重建' : '生成日报'
})

const watchRows = computed(() => rows(report.value.watch_symbols).slice(0, 14))
const breadthRows = computed(() => (report.value.structure?.sector_breadth || []).map(x => [x.name, x.count, x.up, x.down, `${x.up_ratio}%`, fmtNum(x.volume), fmtNum(x.open_interest)]))
const gainerRows = computed(() => rows(report.value.rankings?.gainers))
const loserRows = computed(() => rows(report.value.rankings?.losers))
const seatSignalCards = computed(() => (report.value.seats?.archive?.net_delta_top || []).slice(0, 6).map(x => ({ exchange: exchangeName(x.exchange), name: x.displayName || x.name, netDelta: x.netDelta, longShortRatio: x.longShortRatio, netDir: x.netDir })))
const qualityRows = computed(() => (report.value.data_quality?.exchanges || []).map(x => [exchangeName(x.exchange), statusLabel(x.status), x.daily?.rows ?? 0, x.seat_rank?.rows ?? 0, x.daily?.error || x.seat_rank?.error || '-']))
const sectorStrengthTop = computed(() => [...(report.value.sectors || [])].sort((a, b) => Math.abs(Number(b.avg_change || 0)) - Math.abs(Number(a.avg_change || 0))).slice(0, 8))
const sectorBreadth = computed(() => report.value.structure?.sector_breadth || [])
const qualityOkText = computed(() => { const q = report.value.data_quality; if (!q || q.status === 'empty') return '暂无质量数据'; const bad = (q.exchanges || []).filter(x => x.status !== 'ok').length; return bad ? `${bad} 个交易所需关注` : '覆盖良好' })
const marketSignals = computed(() => [
  { label: '市场阶段', value: report.value.overview?.stage || '-', tone: '' },
  { label: '风险状态', value: report.value.overview?.risk || '-', tone: 'tone-warn' },
  { label: '最活跃板块', value: activeSector.value, tone: 'tone-up' },
  { label: '席位关注', value: seatSignalCards.value[0] ? `${seatSignalCards.value[0].name} ${fmtSigned(seatSignalCards.value[0].netDelta)}` : '-', tone: 'tone-warn' },
])
const activeSector = computed(() => { const x = [...sectorBreadth.value].sort((a, b) => Number(b.volume || 0) - Number(a.volume || 0))[0]; return x ? `${x.name} ${fmtNum(x.volume)}` : '-' })
const sourceTip = computed(() => { const quality = report.value.data_quality; if (!quality || quality.status === 'empty') return ''; const bad = (quality.exchanges || []).filter(x => x.status !== 'ok'); if (!bad.length) return `数据来源：交易所/AKShare/增强源，覆盖 ${quality.coverage_pct ?? 0}%。`; return `数据来源提示：${bad.map(x => `${exchangeName(x.exchange)} ${statusLabel(x.status)}`).join('、')}；部分交易所可能使用 fallback 或暂无数据。` })
const reportBrief = computed(() => report.value.report_brief || null)

const sectorVolumeOption = computed(() => barOption({ names: sectorBreadth.value.map(x => x.name), series: [
  { name: '成交量', data: sectorBreadth.value.map(x => Number(x.volume || 0)), color: '#3f5efb' },
  { name: '持仓量', data: sectorBreadth.value.map(x => Number(x.open_interest || 0)), color: '#16c79a' },
] }))
const volumeTopOption = computed(() => horizontalBarOption((report.value.rankings?.volume || []).slice(0, 10).map(x => ({ name: `${x.symbol} ${x.name || ''}`, value: Number(x.volume || 0) })), '#3f5efb'))
const longSeatOption = computed(() => horizontalBarOption((report.value.seats?.long_increase_top || []).slice(0, 10).map(x => ({ name: `${x.variety} ${x.seat}`, value: Number(x.change || 0) })), '#16c79a'))
const shortSeatOption = computed(() => horizontalBarOption((report.value.seats?.short_increase_top || []).slice(0, 10).map(x => ({ name: `${x.variety} ${x.seat}`, value: Number(x.change || 0) })), '#e94560'))

function emptyReport() { return { overview: {}, market: {}, meta: {}, sectors: [], rankings: {}, data_quality: {}, watch_symbols: [], risk_flags: [] } }
function rows(items = []) { return (items || []).map(x => [exchangeName(x.exchange), x.symbol, contractName(x.contract, x.symbol), x.sector, x.close ?? '-', x.change_pct == null ? '-' : signedPct(x.change_pct)]) }
function signedPct(v) { if (v == null) return '-'; const n = Number(v); return Number.isFinite(n) && n > 0 ? `+${n}%` : `${v}%` }
function fmtSigned(v) { if (v == null) return '-'; const n = Number(v); return Number.isFinite(n) && n > 0 ? `+${n}` : `${v}` }
function fmtNum(value) { if (value == null) return '-'; const n = Number(value); if (!Number.isFinite(n)) return value; if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(2)}亿`; if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`; return n.toFixed(0) }
function compactNumber(v) { const n = Number(v || 0); if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(1)}亿`; if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`; return String(Math.round(n)) }
function toneClass(v) { const n = Number(v || 0); return n > 0 ? 'tone-up' : n < 0 ? 'tone-down' : 'tone-flat' }
function barWidth(v) { return `${Math.min(100, Math.max(6, Math.abs(Number(v || 0)) * 12))}%` }
function barColor(v) { return Number(v || 0) >= 0 ? 'linear-gradient(90deg,#18b785,#5ee0b6)' : 'linear-gradient(90deg,#e94560,#ff9aa9)' }
function chartTextStyle() { return { color: '#64748b', fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' } }
function barOption({ names, series }) { return { color: series.map(x => x.color), tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: compactNumber }, legend: { top: 0, textStyle: chartTextStyle() }, grid: { top: 42, left: 48, right: 18, bottom: 34 }, xAxis: { type: 'category', data: names, axisLabel: { ...chartTextStyle(), interval: 0 }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } } }, yAxis: { type: 'value', axisLabel: { ...chartTextStyle(), formatter: compactNumber }, splitLine: { lineStyle: { color: '#eef2f7' } } }, series: series.map(x => ({ name: x.name, type: 'bar', data: x.data, barMaxWidth: 18, itemStyle: { borderRadius: [7, 7, 0, 0] } })) } }
function horizontalBarOption(items, color) { const rows = [...items].filter(x => Number.isFinite(x.value)).sort((a, b) => a.value - b.value); return { color: [color], tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: compactNumber }, grid: { top: 10, left: 92, right: 24, bottom: 24 }, xAxis: { type: 'value', axisLabel: { ...chartTextStyle(), formatter: compactNumber }, splitLine: { lineStyle: { color: '#eef2f7' } } }, yAxis: { type: 'category', data: rows.map(x => x.name), axisLabel: { ...chartTextStyle(), width: 86, overflow: 'truncate' }, axisTick: { show: false }, axisLine: { show: false } }, series: [{ type: 'bar', data: rows.map(x => x.value), barMaxWidth: 16, itemStyle: { borderRadius: [0, 8, 8, 0] } }] } }
function formatDate(value) { if (!value) return ''; const text = String(value); if (/^\d{8}$/.test(text)) return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6)}`; return text }

async function load() { loading.value = true; error.value = ''; try { const url = viewingDate.value ? `/reports/${viewingDate.value}` : '/reports/latest'; const { data } = await api.get(url); report.value = data || emptyReport() } catch (err) { report.value = emptyReport(); error.value = viewingDate.value ? `未找到 ${formatDate(viewingDate.value)} 的日报。` : '日报加载失败，请稍后重试。' } finally { loading.value = false } }
async function generate() { loading.value = true; error.value = ''; try { await api.post('/reports/generate', null, { params: viewingDate.value ? { trade_date: viewingDate.value, collect: true } : {} }); await load() } finally { loading.value = false } }
onMounted(load)
watch(() => route.query.date, load)
</script>

<style scoped>
.today { max-width:1480px; margin:0 auto; }
.hero { display:flex; justify-content:space-between; gap:24px; align-items:flex-start; padding:26px; border-radius:24px; color:#fff; background:radial-gradient(circle at top left,#3f5efb 0,#1a1a2e 42%,#111827 100%); box-shadow:0 18px 48px rgba(17,24,39,.18); }
.eyebrow { color:#a8c7ff; font-size:13px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
.hero h1 { margin:8px 0 10px; font-size:32px; line-height:1.2; }
.hero p { max-width:860px; margin:0; color:#dbeafe; line-height:1.8; }
.actions { display:flex; gap:10px; align-items:center; flex-shrink:0; }
.primary { background:#e94560; color:white; border:0; border-radius:12px; padding:11px 18px; font-weight:800; cursor:pointer; box-shadow:0 10px 28px rgba(233,69,96,.32); }
.secondary { background:rgba(255,255,255,.12); color:#fff; border:1px solid rgba(255,255,255,.28); border-radius:12px; padding:10px 16px; font-weight:800; text-decoration:none; }
.primary:disabled { opacity:.6; cursor:wait; }
.metric-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin:18px 0; }
.metric-card { background:#fff; border-radius:20px; padding:20px; box-shadow:0 12px 30px rgba(15,23,42,.07); border:1px solid #eef2f7; position:relative; overflow:hidden; }
.metric-card::after { content:''; position:absolute; inset:auto -30px -45px auto; width:120px; height:120px; border-radius:999px; opacity:.12; background:var(--accent); }
.accent-red { --accent:#e94560; } .accent-green { --accent:#16c79a; } .accent-blue { --accent:#3f5efb; } .accent-orange { --accent:#f5a623; }
.metric-label { color:#64748b; font-size:13px; font-weight:800; }
.metric-main { margin-top:8px; color:#0f172a; font-size:30px; font-weight:900; }
.metric-sub { margin-top:6px; color:#94a3b8; font-size:13px; }
.notice { margin:16px 0; padding:12px 14px; background:#f6f8ff; color:#526184; border:1px solid #e4e9ff; border-radius:12px; }
.notice.error { background:#fff0f0; color:#bd3434; border-color:#ffd6d6; }
.risk-strip { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:16px; }
.risk-chip { background:#fff7e6; border:1px solid #ffd591; color:#8a5200; padding:9px 12px; border-radius:999px; font-weight:700; }
.brief-card { margin:16px 0; background:#fff; border:1px solid #e8edf5; border-radius:20px; padding:18px; box-shadow:0 10px 24px rgba(15,23,42,.06); }
.brief-title { font-size:18px; font-weight:900; color:#0f172a; margin-bottom:8px; }
.brief-card p { margin:0; color:#334155; line-height:1.75; }
.brief-bullets { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:14px; }
.brief-bullet { background:#f8fafc; border:1px solid #eef2f7; border-radius:14px; padding:12px; display:grid; gap:6px; }
.brief-bullet b { color:#1e293b; }
.brief-bullet span { color:#64748b; line-height:1.55; font-size:13px; }
.layout-grid, .chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }
.layout-grid.three { grid-template-columns:1fr 1fr 1fr; }
.signal-stack { display:grid; gap:12px; }
.signal-item { display:flex; justify-content:space-between; gap:12px; padding:12px 0; border-bottom:1px solid #f1f5f9; }
.signal-item:last-child { border-bottom:none; }
.signal-name { color:#64748b; }
.tone-up { color:#16a06f; } .tone-down { color:#d93655; } .tone-flat { color:#64748b; } .tone-warn { color:#b7791f; }
.sector-list { display:grid; gap:13px; }
.sector-head { display:flex; justify-content:space-between; margin-bottom:7px; font-weight:800; color:#1f2937; }
.bar { height:8px; background:#f1f5f9; border-radius:999px; overflow:hidden; }
.bar span { display:block; height:100%; border-radius:999px; }
.seat-cards { display:grid; gap:10px; }
.seat-card { padding:12px; border:1px solid #eef2f7; border-radius:14px; background:#fbfdff; }
.seat-title { display:flex; justify-content:space-between; gap:8px; font-weight:900; }
.seat-title em { color:#94a3b8; font-style:normal; font-size:12px; }
.seat-main { margin-top:8px; font-size:22px; font-weight:900; }
.seat-sub { margin-top:4px; color:#64748b; font-size:12px; }
.empty-state { padding:28px; text-align:center; color:#888; background:#fafafa; border-radius:14px; }
.empty-state.large { margin:18px 0; padding:48px; }
.empty-state.small { padding:18px; }
@media (max-width:1100px) { .metric-grid, .layout-grid, .layout-grid.three, .chart-grid, .brief-bullets { grid-template-columns:1fr 1fr; } }
@media (max-width:760px) { .hero { flex-direction:column; } .metric-grid, .layout-grid, .layout-grid.three, .chart-grid, .brief-bullets { grid-template-columns:1fr; } .hero h1 { font-size:26px; } }
</style>
