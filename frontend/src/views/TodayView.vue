<template>
  <div class="today">
    <TodayHero
      :report="report"
      :display-date="displayDate"
      :viewing-date="viewingDate"
      :push-text="pushText"
      :loading="loading"
      :pushing="pushing"
      :copy-button-text="copyButtonText"
      :push-button-text="pushButtonText"
      :generate-button-text="generateButtonText"
      @copy-push-digest="copyPushDigest"
      @push-report="pushReport"
      @generate="generate"
    />

    <div v-if="error" class="notice error">{{ error }}</div>
    <div v-else-if="notice" class="notice success">{{ notice }}</div>
    <div v-else-if="sourceTip" class="notice">{{ sourceTip }}</div>

    <MetricGrid
      :report="report"
      :dashboard-market="dashboardMarket"
      :active-dashboard-mode="activeDashboardMode"
      :quality-coverage-pct="qualityCoveragePct"
      :quality-ok-text="qualityOkText"
    />

    <div v-if="isEmptyReport" class="empty-state large">暂无日报数据。建议先生成日报，再查看市场变化、席位动向和数据完整度。</div>

    <template v-else>
      <section class="daily-workbench">
        <article v-for="item in workbenchCards" :key="item.title" class="workbench-card" :class="item.tone">
          <div class="workbench-label">{{ item.title }}</div>
          <div class="workbench-main">{{ item.main }}</div>
          <div class="workbench-sub">{{ item.sub }}</div>
        </article>
      </section>

      <section class="ask-daily-card">
        <div class="ask-head">
          <div>
            <b>问日报</b>
            <span>直接问今天的市场、重点品种、席位变化或数据是否齐全。</span>
          </div>
          <button class="secondary light" :disabled="askingDaily" @click="askDaily()">{{ askingDaily ? '回答中...' : '提问' }}</button>
        </div>
        <div class="ask-input-row">
          <input v-model="dailyQuestion" placeholder="例如：今天哪些品种最异常？明天重点看什么？" @keyup.enter="askDaily()" />
        </div>
        <div class="ask-chips">
          <button v-for="q in quickQuestions" :key="q" type="button" @click="askDaily(q)">{{ q }}</button>
        </div>
        <div v-if="dailyAnswer" class="ask-answer">
          <div class="ask-answer-title">{{ dailyAnswer.title }}</div>
          <p>{{ dailyAnswer.headline }}</p>
          <ul><li v-for="item in dailyAnswer.bullets" :key="item">{{ item }}</li></ul>
        </div>
      </section>

      <section v-if="pushText" class="push-preview-card">
        <div class="push-preview-head">
          <div>
            <b>推送预览</b>
            <span>{{ pushDigestTitle }} · 发送前先确认最终文案，复制和推送按钮在顶部。</span>
          </div>
          <button class="secondary light" @click="showPushPreview = !showPushPreview">{{ showPushPreview ? '收起预览' : '展开预览' }}</button>
        </div>
        <pre v-if="showPushPreview" class="push-preview-text">{{ pushText }}</pre>
      </section>

      <div v-if="report.risk_flags?.length" class="risk-strip">
        <div v-for="flag in report.risk_flags" :key="flag" class="risk-chip">⚠ {{ flag }}</div>
      </div>

      <div class="dashboard-toolbar">
        <div>
          <b>今日看板</b>
          <span>{{ dashboardEditing ? '拖动卡片调整顺序，取消勾选可隐藏模块。布局会自动保存。' : activeDashboardMode === 'intraday' ? '盘中看最新行情变化、涨跌排行和自选品种。' : '复盘看今天发生了什么、哪些品种值得明天继续盯。' }}</span>
        </div>
        <div class="dashboard-actions">
          <div class="mode-switch" role="tablist" aria-label="今日看板视图">
            <button :class="{ active: activeDashboardMode === 'intraday' }" @click="setDashboardMode('intraday')">盘中</button>
            <button :class="{ active: activeDashboardMode === 'review' }" @click="setDashboardMode('review')">复盘</button>
          </div>
          <div v-if="activeDashboardMode === 'intraday'" class="intraday-actions">
            <span>{{ intraday.updated_at ? `更新 ${intraday.updated_at}` : '暂无最新行情' }}</span>
            <label><input v-model="intradayAutoRefresh" type="checkbox" /> 自动刷新</label>
            <button class="secondary light" :disabled="intradayLoading" @click="loadIntraday(false)">{{ intradayLoading ? '刷新中...' : '刷新页面' }}</button>
            <button class="secondary light collect" :disabled="intradayLoading" @click="loadIntraday(true)">{{ intradayLoading ? '获取中...' : '重新获取行情' }}</button>
          </div>
          <button class="secondary light" @click="dashboardEditing = !dashboardEditing">{{ dashboardEditing ? '完成编辑' : '编辑看板' }}</button>
          <button v-if="dashboardEditing" class="secondary light" @click="resetDashboardLayout">恢复默认</button>
        </div>
      </div>

      <div v-if="activeDashboardMode === 'intraday'" class="intraday-disclaimer">{{ intraday.disclaimer || '这里不是实时行情，只展示最近一次成功获取的数据。' }}</div>

      <div v-if="reportVersionWarning" class="notice version-warning version-rebuild">
        <span>这份日报是旧版本生成的，建议重新生成一次，让分析规则更新到最新版。</span>
        <button class="mini-action" :disabled="loading" @click="rebuildCurrentReport">{{ loading ? '生成中...' : '重新生成' }}</button>
      </div>

      <div v-if="dashboardEditing" class="module-picker">
        <label v-for="card in modeDashboardCards" :key="card.id">
          <input type="checkbox" :checked="!hiddenDashboardCards.includes(card.id)" @change="toggleDashboardCard(card.id)" />
          <span>{{ card.title }}</span>
        </label>
      </div>

      <div class="dashboard-masonry" :class="{ editing: dashboardEditing }">
        <article
          v-for="card in visibleDashboardCards"
          :key="card.id"
          class="dashboard-card"
          :class="[`card-${card.size || 'normal'}`, { dragging: draggingCardId === card.id }]"
          :draggable="dashboardEditing"
          @dragstart="onDashboardDragStart(card.id)"
          @dragend="onDashboardDragEnd"
          @dragover.prevent
          @drop="onDashboardDrop(card.id)"
        >
          <div class="dashboard-card-head">
            <div>
              <span v-if="dashboardEditing" class="drag-handle">⋮⋮</span>
              <b>{{ card.title }}</b>
            </div>
            <div class="card-head-actions">
              <button v-if="isExpandableCard(card.id)" class="expand-card" @click="toggleExpandCard(card.id)">{{ isCardExpanded(card.id) ? '收起' : '展开' }}</button>
              <button v-if="dashboardEditing" class="hide-card" title="隐藏模块" @click="toggleDashboardCard(card.id)">×</button>
            </div>
          </div>

          <template v-if="card.id === 'brief'">
            <div v-if="reportBrief" class="brief-card inline">
              <div class="brief-title">{{ reportBrief.title }}</div>
              <p>{{ reportBrief.conclusion }}</p>
              <div class="brief-bullets">
                <div v-for="item in visibleItems(reportBrief.bullets, card, 3)" :key="item.label" class="brief-bullet">
                  <b>{{ item.label }}</b>
                  <span>{{ item.text }}</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-state small">暂无日报摘要。</div>
          </template>

          <template v-else-if="card.id === 'abnormal'">
            <div class="positioning">{{ report.intelligence?.positioning || '汇总行情、席位、仓单、现货价差和资讯，帮你找出今天最值得关注的变化。' }}</div>
            <div v-if="!abnormalCards.length" class="empty-state small">暂时没有特别明显的异动。等更多行情、席位或现货数据补齐后会更完整。</div>
            <div v-else class="abnormal-grid dashboard-inner-grid">
              <div v-for="item in visibleItems(abnormalCards, card, 3)" :key="`${item.exchange}-${item.symbol}`" class="abnormal-card">
                <div class="abnormal-head">
                  <div><b>{{ item.name || item.symbol }}</b><span>{{ item.symbol }} · {{ exchangeName(item.exchange) }} · {{ item.sector || '-' }}</span></div>
                  <em>{{ item.main_contract || '-' }}</em>
                </div>
                <div class="card-section-label">结论</div>
                <div class="abnormal-signal" :class="`bias-${item.bias || 'neutral'}`">{{ item.signal }}</div>
                <div v-if="item.evidence_chain?.length" class="evidence-chain prominent">
                  <div class="card-section-label evidence-title">主要证据</div>
                  <div v-for="ev in visibleItems(item.evidence_chain || [], card, 4)" :key="ev.key || ev.label" class="evidence-row">
                    <b>{{ ev.label }}</b><span>{{ ev.text }}</span>
                  </div>
                </div>
                <div v-if="item.history_context?.highlights?.length" class="history-context">
                  <div class="card-section-label">历史位置</div>
                  <span v-for="h in visibleItems(item.history_context.highlights || [], card, 3)" :key="`${h.key}-${h.window}`">
                    {{ h.label }}近{{ h.window }}日分位 {{ h.percentile }}%
                  </span>
                </div>
                <div v-if="item.dimensions?.length" class="dimension-tags">
                  <span v-for="dim in item.dimensions" :key="dim.name">{{ dim.name }} {{ dim.score }}</span>
                </div>
                <div v-if="item.reasons?.length" class="reason-list">
                  <div class="card-section-label">可能原因</div>
                  <ul><li v-for="reason in visibleItems(item.reasons || [], card, 2)" :key="reason">{{ reason }}</li></ul>
                </div>
                <div v-if="isCardExpanded(card.id) && item.news_viewpoint" class="viewpoint-chip" :class="`bias-${item.news_viewpoint.bias || 'neutral'}`">资讯观点：{{ item.news_viewpoint.summary }}</div>
                <div v-if="item.watch_next" class="watch-next"><b>明天看：</b>{{ item.watch_next }}</div>
              </div>
            </div>
          </template>

          <template v-else-if="card.id === 'watchFocus'">
            <div v-if="!watchFocusRows.length" class="empty-state small">暂无自选品种。可在设置中批量导入 TA2609 / RU2609 / RB 等关注项。</div>
            <div v-else class="watch-focus-grid">
              <div v-for="item in watchFocusRows" :key="`${item.exchange}-${item.contract}`" class="watch-focus-card">
                <div class="watch-focus-head"><b>{{ item.name || item.symbol }}</b><span>{{ item.contract || item.main_contract || item.symbol }}</span></div>
                <div class="watch-focus-price">{{ item.close ?? '-' }}</div>
                <div class="watch-focus-meta">
                  <em :class="toneClass(item.change_pct)">{{ item.change_pct == null ? '-' : signedPct(item.change_pct) }}</em>
                  <span>{{ exchangeName(item.exchange) }} · {{ item.sector || '-' }}</span>
                </div>
                <div class="watch-focus-sub">成交 {{ fmtNum(item.volume) }}｜持仓 {{ fmtNum(item.open_interest) }}</div>
              </div>
            </div>
          </template>

          <template v-else-if="card.id === 'watchDigest'">
            <div class="positioning">{{ watchDigest.summary || '集中查看你关注品种的价格变化、席位变化、仓单、现货价差和资讯观点。' }}</div>
            <div v-if="!watchDigestItems.length" class="empty-state small">暂无自选品种日报。可在设置中维护关注品种。</div>
            <div v-else class="watch-digest-grid dashboard-inner-grid">
              <div v-for="item in visibleItems(watchDigestItems, card, 4)" :key="item.symbol" class="watch-digest-card" :class="`bias-${item.bias || 'neutral'}`">
                <div class="watch-digest-head">
                  <div><b>{{ item.name || item.symbol }}</b><span>{{ item.symbol }} · {{ item.main_contract || '-' }}</span></div>
                  <em>{{ item.change_pct == null ? '-' : signedPct(item.change_pct) }}</em>
                </div>
                <div class="watch-digest-signal">{{ item.signal || item.summary }}</div>
                <div v-if="item.evidence_chain?.length" class="evidence-chain compact">
                  <div v-for="ev in visibleItems(item.evidence_chain || [], card, 3)" :key="ev.key || ev.label" class="evidence-row">
                    <b>{{ ev.label }}</b><span>{{ ev.text }}</span>
                  </div>
                </div>
                <ul v-if="item.reasons?.length"><li v-for="reason in visibleItems(item.reasons || [], card, 2)" :key="reason">{{ reason }}</li></ul>
                <div v-if="isCardExpanded(card.id) && item.news_viewpoint" class="viewpoint-chip" :class="`bias-${item.news_viewpoint.bias || 'neutral'}`">{{ item.news_viewpoint.summary }}</div>
                <div v-if="isCardExpanded(card.id)" class="watch-next">次日观察：{{ item.watch_next }}</div>
              </div>
            </div>
          </template>

          <template v-else-if="card.id === 'news'">
            <div v-if="!newsViewpoints.length && !newsItems.length" class="empty-state small">暂无资讯摘要。生成日报时会尝试读取公开财经资讯。</div>
            <div v-if="newsViewpoints.length" class="viewpoint-list">
              <div v-for="item in visibleItems(newsViewpoints, card, 5)" :key="item.symbol" class="viewpoint-item" :class="`bias-${item.bias || 'neutral'}`">
                <b>{{ item.name }} · {{ biasLabel(item.bias) }}</b><span>{{ item.summary }}</span>
              </div>
            </div>
            <div v-else class="news-list">
              <a v-for="item in visibleItems(newsItems, card, 5)" :key="item.url || item.title" :href="item.url" target="_blank" rel="noreferrer" class="news-item">
                <b>{{ item.title }}</b><span>{{ item.source }} · {{ (item.symbols || []).join(' / ') || '全市场' }}</span>
              </a>
            </div>
          </template>

          <template v-else-if="card.id === 'tomorrow'">
            <div v-if="!tomorrowWatch.length" class="empty-state small">暂无明日观察清单。</div>
            <div v-else class="watch-list tomorrow-list">
              <div v-for="item in visibleItems(tomorrowWatch, card, 5)" :key="`${item.type}-${item.title}`" class="watch-item tomorrow-item" :class="item.priority === 'high' ? 'high' : ''">
                <div class="tomorrow-top"><em>{{ item.category || '观察' }}</em><strong>{{ item.priority === 'high' ? '重点' : '关注' }}</strong></div>
                <b>{{ item.title }}</b><span>{{ item.body }}</span>
                <ul v-if="item.evidence?.length" class="tomorrow-evidence"><li v-for="ev in item.evidence" :key="ev">{{ ev }}</li></ul>
                <div v-if="item.impact" class="tomorrow-impact">影响：{{ item.impact }}</div>
              </div>
            </div>
          </template>

          <template v-else-if="card.id === 'signals'">
            <div class="signal-stack">
              <div v-for="item in marketSignals" :key="item.label" class="signal-item"><span class="signal-name">{{ item.label }}</span><strong :class="item.tone">{{ item.value }}</strong></div>
            </div>
          </template>

          <template v-else-if="card.id === 'sectors'">
            <div class="sector-list">
              <div v-for="s in sectorStrengthTop" :key="s.name" class="sector-row">
                <div class="sector-head"><span>{{ s.name }}</span><b :class="toneClass(s.avg_change)">{{ signedPct(s.avg_change) }}</b></div>
                <div class="bar"><span :style="{ width: barWidth(s.avg_change), background: barColor(s.avg_change) }"></span></div>
              </div>
            </div>
          </template>

          <template v-else-if="card.id === 'sectorVolume'"><BaseChart :option="sectorVolumeOption" /></template>
          <template v-else-if="card.id === 'volumeTop'"><BaseChart :option="volumeTopOption" /></template>
          <template v-else-if="card.id === 'longSeat'"><BaseChart :option="longSeatOption" /></template>
          <template v-else-if="card.id === 'shortSeat'"><BaseChart :option="shortSeatOption" /></template>
          <template v-else-if="card.id === 'gainers'"><SimpleTable :columns="rankColumns" :data="gainerRows" /></template>
          <template v-else-if="card.id === 'losers'"><SimpleTable :columns="rankColumns" :data="loserRows" /></template>

          <template v-else-if="card.id === 'seatSignals'">
            <div v-if="!seatSignalCards.length" class="empty-state small">暂无席位变化信号。</div>
            <div v-else class="seat-cards">
              <div v-for="x in seatSignalCards" :key="`${x.exchange}-${x.name}`" class="seat-card">
                <div class="seat-title"><span>{{ x.name }}</span><em>{{ x.exchange }}</em></div>
                <div class="seat-main" :class="toneClass(x.netDelta)">{{ fmtSigned(x.netDelta) }}</div>
                <div class="seat-sub">多空比 {{ x.longShortRatio || '-' }} · 方向 {{ x.netDir || '-' }}</div>
              </div>
            </div>
          </template>

          <template v-else-if="card.id === 'watchRows'">
            <div v-if="!watchRows.length" class="empty-state small">暂无自选品种数据。可在设置中维护关注品种，或等待行情采集完成。</div>
            <SimpleTable v-else :columns="rankColumns" :data="watchRows" />
          </template>

          <template v-else-if="card.id === 'breadth'"><SimpleTable :columns="['板块', '合约数', '上涨', '下跌', '上涨占比', '成交量', '持仓量']" :data="breadthRows" /></template>

          <template v-else-if="card.id === 'quality'">
            <div class="quality-actions">
              <span>{{ qualityActionText }}</span>
              <button class="mini-action" :disabled="historyBackfilling || loading" @click="backfillRecentHistory">{{ historyBackfilling ? '补采中...' : '补近5日历史' }}</button>
              <button class="mini-action" :disabled="loading || bulkRecollecting || !recoverableQualityRows.length" @click="recollectFailedOnly">{{ bulkRecollecting ? '补齐中...' : '只补缺失数据' }}</button>
            </div>
            <div class="quality-table">
              <table>
                <thead><tr><th>交易所</th><th>状态</th><th>行情</th><th>席位</th><th>备用数据</th><th>说明</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-for="x in qualityExchangeRows" :key="x.exchange">
                    <td>{{ exchangeName(x.exchange) }}</td>
                    <td :class="statusClass(x.status, x)">{{ qualityStatusLabel(x) }}</td>
                    <td>{{ sourceRows(x.daily) }}</td>
                    <td>{{ sourceRows(x.seat_rank) }}</td>
                    <td>{{ sourceRows(x.seat_rank_fallback) }}</td>
                    <td class="quality-note">{{ x.note || x.daily?.error || x.seat_rank?.error || x.seat_rank_fallback?.error || '-' }}</td>
                    <td><button class="mini-action" :disabled="loading || recollecting[x.exchange] || !isRecoverableQualityRow(x)" @click="recollectExchange(x)">{{ recollecting[x.exchange] ? '补齐中...' : recollectButtonText(x) }}</button></td>
                  </tr>
                  <tr v-if="!qualityExchangeRows.length"><td colspan="7" class="empty-cell">暂无数据检查记录</td></tr>
                </tbody>
              </table>
            </div>
          </template>
        </article>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api.js'
import BaseChart from '../components/BaseChart.vue'
import MetricGrid from '../components/today/MetricGrid.vue'
import TodayHero from '../components/today/TodayHero.vue'
import SimpleTable from '../components/SimpleTable.vue'
import { contractName, exchangeName } from '../exchange.js'
import { statusLabel } from '../labels.js'

const route = useRoute()
const loading = ref(false)
const pushing = ref(false)
const copied = ref(false)
const error = ref('')
const notice = ref('')
const dailyQuestion = ref('')
const dailyAnswer = ref(null)
const askingDaily = ref(false)
const showPushPreview = ref(false)
const quickQuestions = ['今天哪些品种最异常？', '我的自选品种怎么样？', '明天重点看什么？', '数据够不够用？', '席位有什么变化？']
const recollecting = ref({})
const bulkRecollecting = ref(false)
const historyBackfilling = ref(false)
const report = ref(emptyReport())
const intraday = ref(emptyIntraday())
const intradayLoading = ref(false)
const intradayAutoRefresh = ref(false)
let intradayTimer = null
const rankColumns = ['交易所', '品种', '合约', '板块', '收盘', '涨跌幅']
const DASHBOARD_LAYOUT_KEY = 'futures-daily.today.dashboard.v1'
const DASHBOARD_MODE_KEY = 'futures-daily.today.dashboard.mode.v1'
const defaultDashboardCards = [
  { id: 'watchFocus', title: '我的关注', size: 'wide', mode: 'intraday' },
  { id: 'signals', title: '市场风向', mode: 'intraday' },
  { id: 'sectors', title: '强弱板块', mode: 'intraday' },
  { id: 'abnormal', title: '值得关注的异动', size: 'wide', mode: 'intraday' },
  { id: 'watchDigest', title: '自选品种提醒', size: 'wide', mode: 'intraday' },
  { id: 'gainers', title: '涨得最多', mode: 'intraday' },
  { id: 'losers', title: '跌得最多', mode: 'intraday' },
  { id: 'volumeTop', title: '成交最活跃', size: 'chart', mode: 'intraday' },
  { id: 'watchRows', title: '自选列表', mode: 'intraday' },
  { id: 'news', title: '相关资讯', mode: 'intraday' },
  { id: 'brief', title: '今天总结', size: 'wide', mode: 'review' },
  { id: 'tomorrow', title: '明天重点看什么', mode: 'review' },
  { id: 'sectorVolume', title: '板块成交和持仓', size: 'chart', mode: 'review' },
  { id: 'longSeat', title: '多头加仓最多', size: 'chart', mode: 'review' },
  { id: 'shortSeat', title: '空头加仓最多', size: 'chart', mode: 'review' },
  { id: 'seatSignals', title: '席位变化信号', mode: 'review' },
  { id: 'breadth', title: '板块涨跌分布', mode: 'review' },
  { id: 'quality', title: '数据完整度', size: 'wide', mode: 'review' },
]
const dashboardCards = ref(loadDashboardLayout())
const hiddenDashboardCards = ref(loadHiddenDashboardCards())
const dashboardEditing = ref(false)
const draggingCardId = ref('')
const expandedDashboardCards = ref([])
const activeDashboardMode = ref(loadDashboardMode())
const appVersion = ref('0.2.3')
const viewingDate = computed(() => route.query.date ? String(route.query.date) : '')
const displayDate = computed(() => formatDate(report.value.date || viewingDate.value) || '暂无日期')
const isEmptyReport = computed(() => !report.value.date && !report.value.overview?.summary)
const generateButtonText = computed(() => {
  if (loading.value) return viewingDate.value ? '抓取中...' : '生成中...'
  return viewingDate.value ? '重新获取并生成' : '生成日报'
})
const pushText = computed(() => report.value.push_digest?.brief || report.value.push_digest?.text || '')
const pushDigestTitle = computed(() => report.value.push_digest?.title || `期货日报 ${displayDate.value}`)
const copyButtonText = computed(() => copied.value ? '已复制' : '复制推送文案')
const pushButtonText = computed(() => pushing.value ? '推送中...' : '推送日报')
const topFocus = computed(() => abnormalCards.value[0] || watchDigestItems.value[0] || null)
const topFocusText = computed(() => topFocus.value ? `${topFocus.value.name || topFocus.value.symbol || '重点品种'}：${topFocus.value.signal || topFocus.value.summary || '有变化，建议关注'}` : '暂无特别突出的品种异动')
const tomorrowText = computed(() => {
  const item = tomorrowWatch.value[0]
  if (item) return `${item.category ? item.category + '｜' : ''}${item.title}：${item.body}`
  const focus = topFocus.value
  return focus?.watch_next ? `${focus.name || focus.symbol}：${focus.watch_next}` : '暂无明确观察项，可先关注自选品种和成交活跃品种'
})
const dataReadinessText = computed(() => {
  const q = report.value.data_quality || {}
  if (!q || q.status === 'empty') return { main: '暂无检查结果', sub: '生成日报后会显示数据是否齐全', tone: 'neutral' }
  const pct = q.overall_coverage_pct ?? q.coverage_pct ?? 0
  const bad = (q.exchanges || []).filter(x => x.status !== 'ok')
  if (Number(pct) >= 80 && !bad.length) return { main: '数据够用', sub: `完整度 ${pct}%｜主要交易所已覆盖`, tone: 'good' }
  if (Number(pct) >= 50) return { main: '部分缺失', sub: `完整度 ${pct}%｜${bad.length || '部分'} 个交易所需留意`, tone: 'warn' }
  return { main: '谨慎解读', sub: `完整度 ${pct}%｜缺失较多，建议先补数据`, tone: 'bad' }
})
const workbenchCards = computed(() => [
  { title: '今日一句话', main: report.value.overview?.stage || '暂无判断', sub: report.value.overview?.summary || '生成日报后会给出市场概览', tone: 'market' },
  { title: '最值得关注', main: topFocus.value?.name || topFocus.value?.symbol || '暂无突出品种', sub: topFocusText.value, tone: 'focus' },
  { title: '明天重点看', main: tomorrowWatch.value[0]?.title || topFocus.value?.name || '暂无明确重点', sub: tomorrowText.value, tone: 'tomorrow' },
  { title: '数据够不够用', main: dataReadinessText.value.main, sub: dataReadinessText.value.sub, tone: dataReadinessText.value.tone },
])

const modeDashboardCards = computed(() => dashboardCards.value.filter(card => card.mode === activeDashboardMode.value))
const visibleDashboardCards = computed(() => modeDashboardCards.value.filter(card => !hiddenDashboardCards.value.includes(card.id)))
const dashboardMarket = computed(() => activeDashboardMode.value === 'intraday' ? intraday.value.market || {} : report.value.market || {})
const reportVersion = computed(() => report.value.meta?.version || '')
const reportVersionWarning = computed(() => activeDashboardMode.value === 'review' && reportVersion.value && appVersion.value && reportVersion.value !== appVersion.value)
const watchFocusRows = computed(() => (activeDashboardMode.value === 'intraday' ? intraday.value.watch_symbols || [] : report.value.watch_symbols || []).slice(0, 12))
const watchRows = computed(() => rows(activeDashboardMode.value === 'intraday' ? intraday.value.watch_symbols : report.value.watch_symbols).slice(0, 14))
const breadthRows = computed(() => (activeDashboardMode.value === 'intraday' ? intraday.value.sectors || [] : report.value.structure?.sector_breadth || []).map(x => [x.name, x.count, x.up, x.down, x.up_ratio != null ? `${x.up_ratio}%` : '-', fmtNum(x.volume), fmtNum(x.open_interest)]))
const gainerRows = computed(() => rows(activeDashboardMode.value === 'intraday' ? intraday.value.rankings?.gainers : report.value.rankings?.gainers))
const loserRows = computed(() => rows(activeDashboardMode.value === 'intraday' ? intraday.value.rankings?.losers : report.value.rankings?.losers))
const seatSignalCards = computed(() => (report.value.seats?.archive?.net_delta_top || []).slice(0, 6).map(x => ({ exchange: exchangeName(x.exchange), name: x.displayName || x.name, netDelta: x.netDelta, longShortRatio: x.longShortRatio, netDir: x.netDir })))
const qualityExchangeRows = computed(() => report.value.data_quality?.exchanges || [])
const recoverableQualityRows = computed(() => qualityExchangeRows.value.filter(isRecoverableQualityRow))
const unrecoverableQualityRows = computed(() => qualityExchangeRows.value.filter(x => x.unrecoverable_kinds?.length))
const qualityActionText = computed(() => {
  const recoverable = recoverableQualityRows.value.length
  const unrecoverable = unrecoverableQualityRows.value.length
  if (!recoverable && !unrecoverable) return '当前数据看起来比较完整。'
  if (!recoverable && unrecoverable) return `${unrecoverable} 个数据项暂时拿不到，可能需要等交易所恢复或接入商业数据。`
  return `${recoverable} 个数据项可以继续尝试补齐${unrecoverable ? `，${unrecoverable} 个暂时拿不到` : ''}。`
})
const sectorStrengthTop = computed(() => [...(activeDashboardMode.value === 'intraday' ? intraday.value.sectors || [] : report.value.sectors || [])].sort((a, b) => Math.abs(Number(b.avg_change || 0)) - Math.abs(Number(a.avg_change || 0))).slice(0, 8))
const sectorBreadth = computed(() => activeDashboardMode.value === 'intraday' ? intraday.value.sectors || [] : report.value.structure?.sector_breadth || [])
const qualityCoveragePct = computed(() => report.value.data_quality?.overall_coverage_pct ?? report.value.data_quality?.coverage_pct ?? 0)
const qualityOkText = computed(() => {
  const q = report.value.data_quality
  if (!q || q.status === 'empty') return '暂无质量数据'
  if (q.expected) return `行情 ${q.daily_available ?? 0}/${q.expected}｜席位 ${q.seat_available ?? 0}/${q.expected}`
  const bad = (q.exchanges || []).filter(x => x.status !== 'ok').length
  return bad ? `${bad} 个交易所需关注` : '覆盖良好'
})
const marketSignals = computed(() => [
  { label: '市场阶段', value: report.value.overview?.stage || '-', tone: '' },
  { label: '风险状态', value: report.value.overview?.risk || '-', tone: 'tone-warn' },
  { label: '最活跃板块', value: activeSector.value, tone: 'tone-up' },
  { label: '席位关注', value: seatSignalCards.value[0] ? `${seatSignalCards.value[0].name} ${fmtSigned(seatSignalCards.value[0].netDelta)}` : '-', tone: 'tone-warn' },
])
const activeSector = computed(() => { const x = [...sectorBreadth.value].sort((a, b) => Number(b.volume || 0) - Number(a.volume || 0))[0]; return x ? `${x.name} ${fmtNum(x.volume)}` : '-' })
const sourceTip = computed(() => {
  const quality = report.value.data_quality
  if (!quality || quality.status === 'empty') return ''
  if (quality.summary) return `数据来源提示：${quality.summary}。`
  const bad = (quality.exchanges || []).filter(x => x.status !== 'ok')
  if (!bad.length) return `数据检查：主要交易所数据已拿到，完整度 ${quality.coverage_pct ?? 0}%。`
  return `数据检查：${bad.map(x => `${exchangeName(x.exchange)} ${statusLabel(x.status)}`).join('、')}；有些交易所可能暂时缺数据或只拿到了备用数据。`
})
const reportBrief = computed(() => report.value.report_brief || null)
const abnormalCards = computed(() => report.value.intelligence?.abnormal_cards || [])
const tomorrowWatch = computed(() => report.value.intelligence?.tomorrow_watch || [])
const newsItems = computed(() => (report.value.intelligence?.news_digest?.items || []).slice(0, 8))
const newsViewpoints = computed(() => (report.value.intelligence?.news_digest?.viewpoints || []).slice(0, 8))
const watchDigest = computed(() => report.value.intelligence?.watch_digest || {})
const watchDigestItems = computed(() => watchDigest.value.items || [])

const sectorVolumeOption = computed(() => barOption({ names: sectorBreadth.value.map(x => x.name), series: [
  { name: '成交量', data: sectorBreadth.value.map(x => Number(x.volume || 0)), color: '#3f5efb' },
  { name: '持仓量', data: sectorBreadth.value.map(x => Number(x.open_interest || 0)), color: '#16c79a' },
] }))
const volumeTopOption = computed(() => horizontalBarOption(((activeDashboardMode.value === 'intraday' ? intraday.value.rankings?.volume : report.value.rankings?.volume) || []).slice(0, 10).map(x => ({ name: `${x.symbol} ${x.name || ''}`, value: Number(x.volume || 0) })), '#3f5efb'))
const longSeatOption = computed(() => horizontalBarOption((report.value.seats?.long_increase_top || []).slice(0, 10).map(x => ({ name: `${x.variety} ${x.seat}`, value: Number(x.change || 0) })), '#d93655'))
const shortSeatOption = computed(() => horizontalBarOption((report.value.seats?.short_increase_top || []).slice(0, 10).map(x => ({ name: `${x.variety} ${x.seat}`, value: Number(x.change || 0) })), '#12966b'))

function emptyReport() { return { overview: {}, market: {}, meta: {}, sectors: [], rankings: {}, data_quality: {}, watch_symbols: [], risk_flags: [], intelligence: {} } }
function emptyIntraday() { return { mode: 'intraday', trade_date: '', updated_at: '', disclaimer: '这里不是实时行情，只展示最近一次成功获取的数据。', market: {}, rankings: {}, sectors: [], watch_symbols: [] } }
function loadDashboardLayout() {
  try {
    const saved = JSON.parse(localStorage.getItem(DASHBOARD_LAYOUT_KEY) || '{}')
    const order = Array.isArray(saved.order) ? saved.order : []
    const byId = new Map(defaultDashboardCards.map(card => [card.id, card]))
    const ordered = order.map(id => byId.get(id)).filter(Boolean)
    const missing = defaultDashboardCards.filter(card => !order.includes(card.id))
    return [...ordered, ...missing]
  } catch {
    return [...defaultDashboardCards]
  }
}
function loadHiddenDashboardCards() {
  try {
    const saved = JSON.parse(localStorage.getItem(DASHBOARD_LAYOUT_KEY) || '{}')
    return Array.isArray(saved.hidden) ? saved.hidden.filter(id => defaultDashboardCards.some(card => card.id === id)) : []
  } catch {
    return []
  }
}
function loadDashboardMode() {
  try {
    const saved = localStorage.getItem(DASHBOARD_MODE_KEY)
    return ['intraday', 'review'].includes(saved) ? saved : 'intraday'
  } catch {
    return 'intraday'
  }
}
function saveDashboardLayout() {
  localStorage.setItem(DASHBOARD_LAYOUT_KEY, JSON.stringify({ order: dashboardCards.value.map(card => card.id), hidden: hiddenDashboardCards.value }))
  localStorage.setItem(DASHBOARD_MODE_KEY, activeDashboardMode.value)
}
function setDashboardMode(mode) {
  activeDashboardMode.value = mode === 'review' ? 'review' : 'intraday'
  saveDashboardLayout()
}
function resetDashboardLayout() {
  dashboardCards.value = [...defaultDashboardCards]
  hiddenDashboardCards.value = []
  saveDashboardLayout()
}
function toggleDashboardCard(id) {
  hiddenDashboardCards.value = hiddenDashboardCards.value.includes(id)
    ? hiddenDashboardCards.value.filter(x => x !== id)
    : [...hiddenDashboardCards.value, id]
  saveDashboardLayout()
}
function isExpandableCard(id) { return ['brief', 'abnormal', 'watchDigest', 'news', 'tomorrow', 'quality'].includes(id) }
function isCardExpanded(id) { return expandedDashboardCards.value.includes(id) }
function toggleExpandCard(id) {
  expandedDashboardCards.value = isCardExpanded(id)
    ? expandedDashboardCards.value.filter(x => x !== id)
    : [...expandedDashboardCards.value, id]
}
function visibleItems(items = [], card, limit = 4) {
  const list = items || []
  return isCardExpanded(card.id) ? list : list.slice(0, limit)
}
function onDashboardDragStart(id) { draggingCardId.value = id }
function onDashboardDragEnd() { draggingCardId.value = '' }
function onDashboardDrop(targetId) {
  const sourceId = draggingCardId.value
  if (!sourceId || sourceId === targetId) return
  const cards = [...dashboardCards.value]
  const from = cards.findIndex(card => card.id === sourceId)
  const to = cards.findIndex(card => card.id === targetId)
  if (from < 0 || to < 0) return
  const [moved] = cards.splice(from, 1)
  cards.splice(to, 0, moved)
  dashboardCards.value = cards
  saveDashboardLayout()
  draggingCardId.value = ''
}
function rows(items = []) { return (items || []).map(x => [exchangeName(x.exchange), x.symbol, contractName(x.contract, x.symbol), x.sector, x.close ?? '-', x.change_pct == null ? '-' : signedPct(x.change_pct)]) }
function signedPct(v) { if (v == null) return '-'; const n = Number(v); return Number.isFinite(n) && n > 0 ? `+${n}%` : `${v}%` }
function fmtSigned(v) { if (v == null) return '-'; const n = Number(v); return Number.isFinite(n) && n > 0 ? `+${n}` : `${v}` }
function fmtNum(value) { if (value == null) return '-'; const n = Number(value); if (!Number.isFinite(n)) return value; if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(2)}亿`; if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`; return n.toFixed(0) }
function sourceRows(item) { if (!item || !item.rows) return '-'; const suffix = item.ok ? '' : '!'; return `${item.rows}${suffix}` }
function isRecoverableQualityRow(x) { return recollectKinds(x).length > 0 }
function recollectKinds(x) { const kinds = []; if (x.unrecoverable_kinds?.includes('daily')) return []; if (!x.daily?.ok) kinds.push('daily'); if (!x.unrecoverable_kinds?.includes('seat_rank') && !x.seat_rank?.ok && !x.seat_rank_fallback?.ok) kinds.push('seat_rank'); return kinds }
function recollectButtonText(x) { if (!isRecoverableQualityRow(x)) return '暂时补不了'; const kinds = recollectKinds(x); if (kinds.length === 1 && kinds[0] === 'daily') return '补行情'; if (kinds.length === 1 && kinds[0] === 'seat_rank') return '补席位'; return '重新获取' }
function qualityStatusLabel(x) { return x.unrecoverable_kinds?.length ? '部分拿到·暂时缺项' : statusLabel(x.status) }
function statusClass(status, x = {}) { if (x.unrecoverable_kinds?.length) return 'unrecoverable-text'; return status === 'ok' ? 'positive-text' : status === 'failed' ? 'negative-text' : 'warn-text' }
function compactNumber(v) { const n = Number(v || 0); if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(1)}亿`; if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`; return String(Math.round(n)) }
function toneClass(v) { const n = Number(v || 0); return n > 0 ? 'tone-up' : n < 0 ? 'tone-down' : 'tone-flat' }
function barWidth(v) { return `${Math.min(100, Math.max(6, Math.abs(Number(v || 0)) * 12))}%` }
function barColor(v) { return Number(v || 0) >= 0 ? 'linear-gradient(90deg,#e94560,#ff9aa9)' : 'linear-gradient(90deg,#18b785,#5ee0b6)' }
function biasLabel(v) { return ({ positive: '偏多', negative: '偏空', mixed: '分歧', neutral: '中性' })[v] || '中性' }
function chartTextStyle() { return { color: '#64748b', fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' } }
function barOption({ names, series }) { return { color: series.map(x => x.color), tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: compactNumber }, legend: { top: 0, textStyle: chartTextStyle() }, grid: { top: 42, left: 48, right: 18, bottom: 34 }, xAxis: { type: 'category', data: names, axisLabel: { ...chartTextStyle(), interval: 0 }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } } }, yAxis: { type: 'value', axisLabel: { ...chartTextStyle(), formatter: compactNumber }, splitLine: { lineStyle: { color: '#eef2f7' } } }, series: series.map(x => ({ name: x.name, type: 'bar', data: x.data, barMaxWidth: 18, itemStyle: { borderRadius: [7, 7, 0, 0] } })) } }
function horizontalBarOption(items, color) { const rows = [...items].filter(x => Number.isFinite(x.value)).sort((a, b) => a.value - b.value); return { color: [color], tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: compactNumber }, grid: { top: 10, left: 92, right: 24, bottom: 24 }, xAxis: { type: 'value', axisLabel: { ...chartTextStyle(), formatter: compactNumber }, splitLine: { lineStyle: { color: '#eef2f7' } } }, yAxis: { type: 'category', data: rows.map(x => x.name), axisLabel: { ...chartTextStyle(), width: 86, overflow: 'truncate' }, axisTick: { show: false }, axisLine: { show: false } }, series: [{ type: 'bar', data: rows.map(x => x.value), barMaxWidth: 16, itemStyle: { borderRadius: [0, 8, 8, 0] } }] } }
function formatDate(value) { if (!value) return ''; const text = String(value); if (/^\d{8}$/.test(text)) return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6)}`; return text }

async function copyPushDigest() {
  if (!pushText.value) return
  error.value = ''
  notice.value = ''
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(pushText.value)
    } else {
      const el = document.createElement('textarea')
      el.value = pushText.value
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    copied.value = true
    notice.value = '推送文案已复制。'
    setTimeout(() => { copied.value = false }, 1800)
  } catch (err) {
    error.value = '复制失败，请手动选中文字复制。'
  }
}

async function pushReport() {
  if (!report.value.date) return
  pushing.value = true
  error.value = ''
  notice.value = ''
  try {
    const url = viewingDate.value ? `/reports/${viewingDate.value}/push` : '/reports/latest/push'
    const { data } = await api.post(url)
    const failed = (data?.dispatch || []).filter(x => x.ok === false)
    if (failed.length) {
      error.value = `推送完成，但有些通知没发出去：${failed.map(x => x.channel || x.error).join('、')}`
    } else {
      notice.value = '日报已推送，可在任务记录查看发送结果。'
    }
  } catch (err) {
    error.value = '推送失败，请检查通知配置或服务日志。'
  } finally {
    pushing.value = false
  }
}

async function loadHealth() { try { const { data } = await api.get('/health'); appVersion.value = data?.version || appVersion.value } catch {} }
async function askDaily(question = '') {
  const q = question || dailyQuestion.value
  if (!q.trim() || askingDaily.value) return
  dailyQuestion.value = q
  askingDaily.value = true
  error.value = ''
  try {
    const { data } = await api.post('/assistant/ask', { question: q, trade_date: report.value.date || viewingDate.value || null })
    dailyAnswer.value = data
  } catch (err) {
    error.value = '暂时回答不了，请先确认日报已经生成。'
  } finally {
    askingDaily.value = false
  }
}
async function load() { loading.value = true; error.value = ''; try { const url = viewingDate.value ? `/reports/${viewingDate.value}` : '/reports/latest'; const { data } = await api.get(url); report.value = data || emptyReport(); dailyAnswer.value = null } catch (err) { report.value = emptyReport(); error.value = viewingDate.value ? `未找到 ${formatDate(viewingDate.value)} 的日报。` : '日报加载失败，请稍后重试。' } finally { loading.value = false } }
async function loadIntraday(refresh = false) {
  intradayLoading.value = true
  try {
    const params = { trade_date: viewingDate.value || undefined }
    const { data } = refresh
      ? await api.post('/markets/intraday/refresh', null, { params })
      : await api.get('/markets/intraday', { params })
    intraday.value = data || emptyIntraday()
    if (refresh && data?.job_id) notice.value = `最新行情已更新，任务 #${data.job_id}。`
  } catch (err) {
    if (activeDashboardMode.value === 'intraday') error.value = '最新行情加载失败，请稍后重试。'
  } finally {
    intradayLoading.value = false
  }
}
async function generate() { loading.value = true; error.value = ''; notice.value = ''; try { await api.post('/reports/generate', null, { params: viewingDate.value ? { trade_date: viewingDate.value, collect: true } : {} }); await load(); await loadIntraday(false); notice.value = '日报已生成。' } finally { loading.value = false } }
async function rebuildCurrentReport() {
  const tradeDate = report.value.date || viewingDate.value
  if (!tradeDate) return
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    await api.post('/reports/generate', null, { params: { trade_date: tradeDate, collect: false } })
    await load()
    notice.value = '日报已重新生成。'
  } catch (err) {
    error.value = '日报生成失败，请到任务记录里看失败原因。'
  } finally {
    loading.value = false
  }
}
async function recollectExchange(x) {
  if (!report.value.date || !x?.exchange || !isRecoverableQualityRow(x)) return
  error.value = ''
  notice.value = ''
  recollecting.value = { ...recollecting.value, [x.exchange]: true }
  try {
    const { data } = await runRecollect(x, true)
    await load()
    notice.value = data?.summary || `${exchangeName(x.exchange)} 数据已补齐。`
  } catch (err) {
    error.value = `${exchangeName(x.exchange)} 数据没补上，请到任务记录里看原因。`
  } finally {
    recollecting.value = { ...recollecting.value, [x.exchange]: false }
  }
}
async function recollectFailedOnly() {
  const rows = [...recoverableQualityRows.value]
  if (!report.value.date || !rows.length) return
  error.value = ''
  notice.value = ''
  bulkRecollecting.value = true
  try {
    for (const row of rows) {
      recollecting.value = { ...recollecting.value, [row.exchange]: true }
      await runRecollect(row, false)
      recollecting.value = { ...recollecting.value, [row.exchange]: false }
    }
    await api.post('/reports/generate', null, { params: { trade_date: report.value.date, collect: false } })
    await load()
    notice.value = `已尝试补齐 ${rows.length} 个数据项，并重新生成日报。`
  } catch (err) {
    error.value = '补数据中断了，请到任务记录里看原因。'
  } finally {
    bulkRecollecting.value = false
    const reset = { ...recollecting.value }
    for (const row of rows) reset[row.exchange] = false
    recollecting.value = reset
  }
}
async function backfillRecentHistory() {
  const tradeDate = report.value.date || viewingDate.value
  if (!tradeDate || historyBackfilling.value) return
  error.value = ''
  notice.value = ''
  historyBackfilling.value = true
  try {
    const { data } = await api.post('/history/backfill', null, { params: { end_date: tradeDate, days: 5, seats: false, enhancements: true, rebuild_latest: true } })
    await load()
    notice.value = `已补采近 ${data?.days || 5} 个交易日历史，并重建当前日报。`
  } catch (err) {
    error.value = '历史补采失败，请到运行记录或服务日志查看原因。'
  } finally {
    historyBackfilling.value = false
  }
}
function runRecollect(x, rebuild) {
  const params = new URLSearchParams({ exchange: x.exchange, rebuild: String(rebuild) })
  for (const kind of recollectKinds(x)) params.append('kinds', kind)
  return api.post(`/reports/${report.value.date}/recollect?${params.toString()}`)
}
function stopIntradayTimer() {
  if (intradayTimer) clearInterval(intradayTimer)
  intradayTimer = null
}
function startIntradayTimer() {
  stopIntradayTimer()
  if (intradayAutoRefresh.value && activeDashboardMode.value === 'intraday') {
    intradayTimer = setInterval(() => loadIntraday(false), 5 * 60 * 1000)
  }
}
onMounted(async () => { await Promise.all([loadHealth(), load(), loadIntraday(false)]); startIntradayTimer() })
onUnmounted(stopIntradayTimer)
watch(() => route.query.date, async () => { await Promise.all([load(), loadIntraday(false)]) })
watch(activeDashboardMode, mode => { if (mode === 'intraday' && !intraday.value.trade_date) loadIntraday(false); startIntradayTimer() })
watch(intradayAutoRefresh, startIntradayTimer)
</script>

<style scoped>
.today { max-width:1480px; margin:0 auto; }
.notice { margin:16px 0; padding:12px 14px; background:#f6f8ff; color:#526184; border:1px solid #e4e9ff; border-radius:12px; }
.notice.success { background:#f0fff5; color:#0f8a55; border-color:#bfeecf; }
.notice.error { background:#fff0f0; color:#bd3434; border-color:#ffd6d6; }
.daily-workbench { display:grid; grid-template-columns:1.15fr 1fr 1fr .9fr; gap:14px; margin:18px 0; }
.workbench-card { min-height:132px; border-radius:22px; padding:17px; color:#fff; box-shadow:0 14px 34px rgba(15,23,42,.12); display:flex; flex-direction:column; gap:8px; overflow:hidden; position:relative; }
.workbench-card::after { content:''; position:absolute; width:140px; height:140px; right:-46px; bottom:-58px; border-radius:999px; background:rgba(255,255,255,.16); }
.workbench-card.market { background:linear-gradient(135deg,#1d4ed8,#172554); }
.workbench-card.focus { background:linear-gradient(135deg,#e94560,#7f1d1d); }
.workbench-card.tomorrow { background:linear-gradient(135deg,#7c3aed,#312e81); }
.workbench-card.good { background:linear-gradient(135deg,#059669,#064e3b); }
.workbench-card.warn { background:linear-gradient(135deg,#d97706,#78350f); }
.workbench-card.bad { background:linear-gradient(135deg,#dc2626,#7f1d1d); }
.workbench-card.neutral { background:linear-gradient(135deg,#475569,#0f172a); }
.workbench-label { color:rgba(255,255,255,.76); font-size:13px; font-weight:900; }
.workbench-main { position:relative; z-index:1; font-size:21px; font-weight:950; line-height:1.25; }
.workbench-sub { position:relative; z-index:1; color:rgba(255,255,255,.86); line-height:1.55; font-size:13px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
.ask-daily-card { margin:0 0 18px; padding:16px; border-radius:22px; background:#fff; border:1px solid #e8edf5; box-shadow:0 10px 26px rgba(15,23,42,.06); }
.ask-head { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.ask-head b { display:block; color:#0f172a; font-size:17px; font-weight:950; }
.ask-head span { display:block; margin-top:4px; color:#64748b; font-size:13px; }
.ask-input-row { margin-top:12px; }
.ask-input-row input { width:100%; box-sizing:border-box; border:1px solid #dbe3ef; border-radius:14px; padding:12px 14px; font-size:14px; outline:none; }
.ask-input-row input:focus { border-color:#8ea2ff; box-shadow:0 0 0 4px rgba(63,94,251,.10); }
.ask-chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.ask-chips button { border:1px solid #dfe6ff; background:#f5f7ff; color:#3157d5; border-radius:999px; padding:7px 10px; font-size:12px; font-weight:900; cursor:pointer; }
.ask-answer { margin-top:13px; padding:13px; border-radius:16px; background:#f8fafc; border:1px solid #edf2f7; }
.ask-answer-title { color:#3157d5; font-size:13px; font-weight:950; }
.ask-answer p { margin:6px 0 8px; color:#0f172a; font-weight:900; line-height:1.55; }
.ask-answer ul { margin:0; padding-left:18px; color:#475569; line-height:1.65; }
.push-preview-card { margin:0 0 18px; padding:16px; border-radius:22px; background:linear-gradient(180deg,#ffffff,#f8fbff); border:1px solid #dfe6ff; box-shadow:0 10px 26px rgba(15,23,42,.06); }
.push-preview-head { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.push-preview-head b { display:block; color:#0f172a; font-size:17px; font-weight:950; }
.push-preview-head span { display:block; margin-top:4px; color:#64748b; font-size:13px; line-height:1.45; }
.push-preview-text { margin:14px 0 0; max-height:420px; overflow:auto; white-space:pre-wrap; word-break:break-word; border-radius:16px; background:#0f172a; color:#dbeafe; padding:14px; font-size:13px; line-height:1.7; }
.risk-strip { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:16px; }
.risk-chip { background:#fff7e6; border:1px solid #ffd591; color:#8a5200; padding:9px 12px; border-radius:999px; font-weight:700; }
.dashboard-toolbar { display:flex; justify-content:space-between; gap:14px; align-items:center; margin:18px 0 12px; padding:14px 16px; border:1px solid #e8edf5; border-radius:18px; background:rgba(255,255,255,.86); box-shadow:0 10px 26px rgba(15,23,42,.05); backdrop-filter:blur(10px); }
.dashboard-toolbar b { display:block; color:#0f172a; font-size:17px; }
.dashboard-toolbar span { display:block; margin-top:4px; color:#64748b; font-size:13px; line-height:1.45; }
.dashboard-actions { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; align-items:center; }
.mode-switch { display:flex; gap:4px; padding:4px; border-radius:999px; background:#eef2ff; border:1px solid #dfe6ff; }
.mode-switch button { border:0; border-radius:999px; padding:8px 14px; background:transparent; color:#64748b; font-weight:900; cursor:pointer; }
.mode-switch button.active { color:#fff; background:linear-gradient(135deg,#3f5efb,#6f8cff); box-shadow:0 8px 20px rgba(63,94,251,.24); }
.intraday-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; color:#64748b; font-size:12px; font-weight:800; }
.intraday-actions label { display:flex; align-items:center; gap:5px; cursor:pointer; white-space:nowrap; }
.intraday-actions .collect { color:#8a5200; background:#fff7e6; border-color:#ffd591; }
.intraday-disclaimer { margin:-2px 0 12px; padding:10px 13px; color:#64748b; background:#f8fafc; border:1px solid #e8edf5; border-radius:14px; font-size:13px; font-weight:800; }
.notice.version-warning { background:#fff7e6; color:#8a5200; border-color:#ffd591; }
.version-rebuild { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; }
.secondary.light { color:#3157d5; background:#f5f7ff; border-color:#dfe6ff; box-shadow:none; }
.module-picker { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; padding:12px; border-radius:16px; background:#f8fafc; border:1px dashed #cbd5e1; }
.module-picker label { display:flex; gap:6px; align-items:center; color:#475569; background:#fff; border:1px solid #e2e8f0; border-radius:999px; padding:7px 10px; font-size:13px; font-weight:800; cursor:pointer; }
.dashboard-masonry { column-count:2; column-gap:18px; }
.dashboard-card { display:inline-block; width:100%; margin:0 0 18px; break-inside:avoid; background:#fff; border:1px solid #e8edf5; border-radius:22px; padding:15px; box-shadow:0 10px 26px rgba(15,23,42,.06); transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease, opacity .18s ease; vertical-align:top; }
.dashboard-card:hover { transform:translateY(-1px); box-shadow:0 14px 32px rgba(15,23,42,.08); }
.dashboard-card.editing, .dashboard-masonry.editing .dashboard-card { cursor:grab; border-style:dashed; }
.dashboard-card.dragging { opacity:.45; transform:scale(.985); border-color:#8ea2ff; }
.dashboard-card-head { display:flex; justify-content:space-between; gap:10px; align-items:center; margin-bottom:10px; padding-bottom:8px; border-bottom:1px solid #f1f5f9; }
.dashboard-card-head b { color:#0f172a; font-size:15px; font-weight:900; }
.card-head-actions { display:flex; gap:6px; align-items:center; flex-shrink:0; }
.expand-card { border:0; background:#f1f5ff; color:#3157d5; border-radius:999px; padding:5px 9px; font-size:12px; font-weight:900; cursor:pointer; }
.drag-handle { color:#94a3b8; letter-spacing:-4px; margin-right:9px; cursor:grab; user-select:none; }
.hide-card { width:26px; height:26px; display:grid; place-items:center; border:0; border-radius:999px; background:#f1f5f9; color:#64748b; cursor:pointer; font-size:18px; line-height:1; }
.hide-card:hover { background:#ffe4e8; color:#d93655; }
.dashboard-inner-grid { grid-template-columns:1fr; gap:9px; }
.card-wide { column-span:all; }
.card-chart { min-height:310px; }
.dashboard-card .simple-table { max-height:360px; overflow:auto; }
.dashboard-card .positioning { margin-bottom:10px; padding:9px 11px; font-size:13px; line-height:1.55; }
.brief-card { margin:16px 0; background:#fff; border:1px solid #e8edf5; border-radius:20px; padding:18px; box-shadow:0 10px 24px rgba(15,23,42,.06); }
.brief-card.inline { margin:0; box-shadow:none; border-color:#eef2f7; }
.brief-title { font-size:18px; font-weight:900; color:#0f172a; margin-bottom:8px; }
.brief-card p { margin:0; color:#334155; line-height:1.75; }
.brief-bullets { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:14px; }
.brief-bullet { background:#f8fafc; border:1px solid #eef2f7; border-radius:14px; padding:12px; display:grid; gap:6px; }
.brief-bullet b { color:#1e293b; }
.brief-bullet span { color:#64748b; line-height:1.55; font-size:13px; }
.positioning { margin-bottom:14px; color:#475569; line-height:1.7; background:#f8fafc; border:1px solid #eef2f7; border-radius:14px; padding:12px 14px; }
.abnormal-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
.abnormal-card { border:1px solid #e8edf5; border-radius:16px; padding:12px; background:linear-gradient(180deg,#fff,#fbfdff); box-shadow:0 6px 16px rgba(15,23,42,.035); }
.abnormal-head { display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }
.abnormal-head b { display:block; color:#0f172a; font-size:16px; }
.abnormal-head span { display:block; margin-top:4px; color:#94a3b8; font-size:12px; }
.abnormal-head em { color:#64748b; background:#f1f5f9; border-radius:999px; padding:4px 8px; font-style:normal; font-size:12px; white-space:nowrap; }
.card-section-label { margin-top:10px; color:#94a3b8; font-size:12px; font-weight:950; letter-spacing:.04em; }
.abnormal-signal { margin-top:4px; color:#1e293b; font-weight:950; line-height:1.6; font-size:15px; }
.bias-positive { color:#d93655; } .bias-negative { color:#12966b; } .bias-mixed { color:#b45309; } .bias-neutral { color:#475569; }
.dimension-tags { display:flex; flex-wrap:wrap; gap:6px; margin-top:9px; }
.dimension-tags span { color:#526184; background:#f1f5f9; border:1px solid #e2e8f0; border-radius:999px; padding:4px 7px; font-size:12px; font-weight:800; }
.history-context { display:flex; flex-wrap:wrap; gap:7px; margin-top:9px; }
.history-context .card-section-label { flex-basis:100%; margin-top:0; }
.history-context span { background:#eef2ff; color:#3157d5; border:1px solid #dfe6ff; border-radius:999px; padding:5px 8px; font-size:12px; font-weight:900; }
.evidence-chain { display:grid; gap:7px; margin-top:10px; padding:9px; border-radius:13px; background:#f8fafc; border:1px solid #edf2f7; }
.evidence-chain.prominent { background:#f8fbff; border-color:#dfe8ff; padding:11px; }
.evidence-title { margin-top:0; color:#3157d5; }
.evidence-chain.compact { padding:8px; }
.evidence-row { display:grid; grid-template-columns:72px 1fr; gap:8px; align-items:start; font-size:12px; line-height:1.45; }
.evidence-row b { color:#3157d5; white-space:nowrap; }
.evidence-row span { color:#475569; }
.reason-list ul, .abnormal-card ul { margin:7px 0 0; padding-left:18px; color:#475569; line-height:1.55; font-size:13px; }
.viewpoint-chip { margin-top:10px; border-radius:12px; padding:9px; background:#f8fafc; border:1px solid #e2e8f0; font-size:13px; line-height:1.55; color:#475569; }
.related-news { display:grid; gap:6px; margin-top:10px; }
.related-news a { color:#3157d5; text-decoration:none; font-size:13px; line-height:1.45; }
.related-news a:hover { text-decoration:underline; }
.watch-next { margin-top:10px; color:#8a5200; background:#fff7e6; border:1px solid #ffe4ad; border-radius:12px; padding:9px; font-size:13px; line-height:1.55; }
.watch-next b { margin-right:4px; }
.news-list, .viewpoint-list { display:grid; gap:9px; }
.viewpoint-item { border:1px solid #e8edf5; border-radius:14px; padding:11px 12px; background:#fff; }
.viewpoint-item b { display:block; margin-bottom:5px; }
.viewpoint-item span { color:#64748b; line-height:1.55; }
.news-item { display:block; text-decoration:none; border:1px solid #e8edf5; border-radius:14px; padding:11px 12px; background:#fff; }
.news-item b { display:block; color:#0f172a; line-height:1.45; }
.news-item span { display:block; margin-top:5px; color:#94a3b8; font-size:12px; }
.news-item:hover { border-color:#b8c4ff; box-shadow:0 8px 18px rgba(63,94,251,.08); }
.watch-focus-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
.watch-focus-card { border:1px solid #e8edf5; border-radius:16px; padding:13px; background:linear-gradient(180deg,#fff,#fbfdff); box-shadow:0 6px 16px rgba(15,23,42,.035); }
.watch-focus-head { display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }
.watch-focus-head b { color:#0f172a; font-size:16px; }
.watch-focus-head span { color:#64748b; background:#f1f5f9; border-radius:999px; padding:4px 8px; font-size:12px; font-weight:900; }
.watch-focus-price { margin-top:12px; color:#0f172a; font-size:24px; font-weight:950; }
.watch-focus-meta { display:flex; justify-content:space-between; gap:10px; align-items:center; margin-top:6px; }
.watch-focus-meta em { font-style:normal; font-weight:950; }
.watch-focus-meta span, .watch-focus-sub { color:#94a3b8; font-size:12px; }
.watch-focus-sub { margin-top:8px; }
.watch-digest-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
.watch-digest-card { border:1px solid #e8edf5; border-radius:16px; padding:12px; background:#fff; box-shadow:0 6px 16px rgba(15,23,42,.035); }
.watch-digest-head { display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }
.watch-digest-head b { display:block; color:#0f172a; font-size:16px; }
.watch-digest-head span { display:block; margin-top:4px; color:#94a3b8; font-size:12px; }
.watch-digest-head em { color:#0f172a; background:#f1f5f9; border-radius:999px; padding:4px 8px; font-style:normal; font-weight:900; white-space:nowrap; }
.watch-digest-signal { margin-top:10px; font-weight:900; line-height:1.55; }
.watch-digest-card ul { margin:8px 0 0; padding-left:18px; color:#475569; line-height:1.55; font-size:13px; }
.watch-list { display:grid; gap:10px; }
.watch-item { border:1px solid #e8edf5; border-radius:14px; padding:12px; background:#fff; }
.watch-item.high { border-color:#ffd591; background:#fffaf0; }
.tomorrow-list { gap:12px; }
.tomorrow-item { display:grid; gap:8px; }
.tomorrow-top { display:flex; justify-content:space-between; gap:8px; align-items:center; }
.tomorrow-top em { font-style:normal; color:#3157d5; background:#eef2ff; border-radius:999px; padding:4px 8px; font-size:12px; font-weight:950; }
.tomorrow-top strong { color:#b45309; font-size:12px; }
.tomorrow-evidence { margin:0; padding-left:18px; color:#64748b; line-height:1.5; font-size:12px; }
.tomorrow-impact { color:#8a5200; background:#fff7e6; border:1px solid #ffe4ad; border-radius:10px; padding:8px; font-size:12px; line-height:1.45; }
.watch-item b { display:block; color:#0f172a; margin-bottom:5px; }
.watch-item span { color:#64748b; line-height:1.6; }
.layout-grid, .chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }
.layout-grid.three { grid-template-columns:1fr 1fr 1fr; }
.signal-stack { display:grid; gap:12px; }
.signal-item { display:flex; justify-content:space-between; gap:12px; padding:12px 0; border-bottom:1px solid #f1f5f9; }
.signal-item:last-child { border-bottom:none; }
.signal-name { color:#64748b; }
.tone-up { color:#d93655; } .tone-down { color:#12966b; } .tone-flat { color:#64748b; } .tone-warn { color:#b7791f; }
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
.quality-actions { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:12px; color:#64748b; background:#f8fafc; border:1px solid #eef2f7; border-radius:14px; padding:10px 12px; font-size:13px; }
.quality-table { width:100%; overflow:auto; }
.quality-table table { width:100%; border-collapse:separate; border-spacing:0; font-size:13px; min-width:780px; }
.quality-table th { position:sticky; top:0; z-index:1; background:#f8fafc; padding:11px 12px; text-align:left; font-weight:900; color:#475569; border-bottom:1px solid #e2e8f0; white-space:nowrap; }
.quality-table td { padding:11px 12px; border-bottom:1px solid #f1f5f9; color:#1f2937; white-space:nowrap; }
.quality-note { color:#64748b; white-space:normal; min-width:220px; }
.mini-action { background:#f1f5ff; color:#3157d5; border:1px solid #dbe3ff; border-radius:10px; padding:7px 11px; font-weight:800; cursor:pointer; }
.mini-action:disabled { opacity:.6; cursor:wait; }
.positive-text { color:#12966b !important; font-weight:800; }
.negative-text { color:#d93655 !important; font-weight:800; }
.warn-text { color:#b7791f !important; font-weight:800; }
.unrecoverable-text { color:#7c3aed !important; font-weight:900; }
.empty-cell { text-align:center; color:#94a3b8; padding:24px !important; }
.empty-state { padding:28px; text-align:center; color:#888; background:#fafafa; border-radius:14px; }
.empty-state.large { margin:18px 0; padding:48px; }
.empty-state.small { padding:18px; }
@media (max-width:1100px) { .daily-workbench { grid-template-columns:1fr 1fr; } .dashboard-masonry { column-count:2; } .layout-grid, .layout-grid.three, .chart-grid, .brief-bullets, .abnormal-grid, .watch-digest-grid, .watch-focus-grid { grid-template-columns:1fr 1fr; } }
@media (max-width:760px) { .daily-workbench { grid-template-columns:1fr; } .ask-head { flex-direction:column; align-items:stretch; } .dashboard-toolbar { flex-direction:column; align-items:stretch; } .dashboard-masonry { column-count:1; } .layout-grid, .layout-grid.three, .chart-grid, .brief-bullets, .abnormal-grid, .watch-digest-grid, .watch-focus-grid { grid-template-columns:1fr; } }
</style>
