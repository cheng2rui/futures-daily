<template>
  <div class="diagnostics">
    <div class="page-head">
      <div>
        <h2 class="page-title">数据源诊断</h2>
        <p class="muted">{{ tradeDate || '暂无日期' }} ｜ 聚焦 DCE / INE：覆盖矩阵、弱源诊断、原始响应和 parser replay。</p>
      </div>
      <div class="head-actions">
        <input v-model="tradeDateInput" placeholder="YYYYMMDD" @keyup.enter="load" />
        <button class="primary" :disabled="loading" @click="load">{{ loading ? '刷新中...' : '刷新' }}</button>
      </div>
    </div>

    <div v-if="notice" class="notice success">{{ notice }}</div>
    <div v-if="error" class="notice error">{{ error }}</div>

    <SectionCard v-if="operationResult" title="最近一次操作结果" class="op-card">
      <div class="op-summary">{{ operationResult.summary || '暂无总结' }}</div>
      <div class="replay-stats">
        <span>核心覆盖 {{ operationResult.coverage_diff?.core_coverage_after ?? 0 }}% <em>({{ fmtDelta(operationResult.coverage_diff?.core_coverage_delta) }})</em></span>
        <span>综合覆盖 {{ operationResult.coverage_diff?.overall_coverage_after ?? 0 }}% <em>({{ fmtDelta(operationResult.coverage_diff?.overall_coverage_delta) }})</em></span>
        <span>改善 {{ operationResult.coverage_diff?.improved_cells ?? 0 }}</span>
        <span>回退 {{ operationResult.coverage_diff?.regressed_cells ?? 0 }}</span>
      </div>
      <div class="op-tail">{{ operationResult.note || operationResult.message || '-' }}</div>
      <div v-if="operationResult.coverage_diff?.changes?.length" class="change-list compact">
        <div v-for="change in operationResult.coverage_diff.changes.slice(0, 8)" :key="`op-${change.exchange}-${change.kind}`" class="change-row" :class="changeClass(change.direction)">
          <b>{{ exchangeName(change.exchange) }} · {{ kindLabel(change.kind) }}</b>
          <span>{{ statusLabel(change.before?.status) }} {{ change.before?.rows ?? 0 }} → {{ statusLabel(change.after?.status) }} {{ change.after?.rows ?? 0 }}</span>
          <em>{{ Number(change.row_delta || 0) > 0 ? '+' : '' }}{{ change.row_delta || 0 }}</em>
        </div>
      </div>
    </SectionCard>

    <div class="kpi-row">
      <KpiCard label="核心覆盖" :value="`${coverageSummary.core_coverage_pct ?? 0}%`" color="#3f5efb" />
      <KpiCard label="综合覆盖" :value="`${coverageSummary.overall_coverage_pct ?? 0}%`" color="#16c79a" />
      <KpiCard label="部分交易所" :value="coverageSummary.partial_exchanges || 0" color="#f5a623" />
      <KpiCard label="源健康均分" :value="sourceHealthSummary.average_score ?? 0" :color="sourceHealthColor" />
    </div>

    <SectionCard title="数据源健康">
      <div class="source-health-head">
        <b>{{ sourceHealthSummary.summary || '暂无来源健康数据' }}</b>
        <span>Top: {{ (sourceHealthSummary.top_sources || []).join(' / ') || '-' }}</span>
      </div>
      <div class="source-grid">
        <article v-for="src in sourceHealthRows" :key="src.source" class="source-card" :class="`source-${src.status}`">
          <div class="source-top">
            <b>{{ src.source }}</b>
            <em>{{ src.score }}</em>
          </div>
          <p>{{ src.summary }}</p>
          <div class="source-metrics">
            <span>成功率 {{ src.success_rate }}%</span>
            <span>运行 {{ src.runs_success }}/{{ src.runs_total }}</span>
            <span>归档 {{ src.archives_count }}</span>
            <span>缺口 {{ src.open_gaps }}</span>
          </div>
          <div v-if="src.error_summary?.top_code" class="source-cause">
            <b>{{ src.error_summary.top_label }}</b>
            <span>{{ src.latest_error_category?.suggestion || src.error_summary.summary }}</span>
          </div>
          <div v-if="src.latest_error" class="source-error">{{ src.latest_error }}</div>
        </article>
      </div>
    </SectionCard>

    <SectionCard title="自动补采计划" style="margin-top:16px">
      <div class="retry-head">
        <div>
          <b>{{ retryPlan.summary?.summary || '暂无补采建议' }}</b>
          <span>跳过 {{ retryPlan.summary?.skipped ?? 0 }} 项不可自动处理数据。</span>
        </div>
        <div class="retry-actions">
          <button class="secondary" :disabled="loadingPlan || !retryPlanSteps.length" @click="runFirstRetryStep">{{ loadingPlan ? '执行中...' : '执行第一步' }}</button>
          <button class="primary small" :disabled="loadingPlan || !retryPlanSteps.length" @click="runRetryPlan">{{ loadingPlan ? '执行中...' : '执行计划' }}</button>
        </div>
      </div>
      <div v-if="!retryPlanSteps.length" class="empty-state small success">当前没有建议自动补采的步骤。</div>
      <div v-else class="retry-list">
        <article v-for="step in retryPlanSteps" :key="`${step.order}-${step.type}-${step.exchange}-${step.kind}`" class="retry-step">
          <div class="retry-top">
            <b>#{{ step.order }} {{ step.type }} · {{ exchangeName(step.exchange) }} · {{ kindLabel(step.kind) }}</b>
            <em>优先级 {{ step.priority }}</em>
          </div>
          <p>{{ step.reason }}</p>
          <div class="retry-meta">
            <span>源：{{ step.source }} / {{ step.source_status }}</span>
            <span>决策：{{ step.decision_label || step.decision || '自动重试' }}</span>
            <span v-if="step.error_category?.label">归因：{{ step.error_category.label }}</span>
            <span>预期：{{ step.expected_effect }}</span>
            <span>风险：{{ step.risk }}</span>
          </div>
          <div v-if="step.browser_probe" class="browser-probe">
            <b>{{ step.browser_probe.label }}</b>
            <span>{{ step.browser_probe.reason }}</span>
            <em>{{ step.browser_probe.next_step }}</em>
          </div>
          <div class="retry-step-actions">
            <button class="mini-action" :disabled="loadingPlan" @click="runRetryStep(step)">执行这一步</button>
            <button v-if="step.browser_probe" class="mini-action probe" :disabled="loadingPlan" @click="runBrowserProbe(step)">Browser Probe</button>
          </div>
        </article>
      </div>
      <details v-if="retryPlanSkipped.length" class="skip-details">
        <summary>查看跳过项 {{ retryPlanSkipped.length }} 个</summary>
        <div class="skip-list">
          <span v-for="item in retryPlanSkipped" :key="`${item.exchange}-${item.kind}`">{{ exchangeName(item.exchange) }} · {{ kindLabel(item.kind) }}：{{ item.decision_label || item.reason_code }}｜{{ item.error_category?.label || '未归因' }}｜{{ item.reason }}</span>
        </div>
      </details>
    </SectionCard>

    <SectionCard title="自动补采历史" style="margin-top:16px">
      <div class="history-head">
        <div>
          <b>{{ retryHistory.summary?.summary || '暂无自动补采执行历史。' }}</b>
          <span>记录 Retry Runner 每次做了什么、改善了多少、还剩哪些缺口。</span>
        </div>
        <button class="secondary" :disabled="loadingHistory" @click="loadRetryHistory">{{ loadingHistory ? '刷新中...' : '刷新历史' }}</button>
      </div>
      <div v-if="!retryRuns.length" class="empty-state small">暂无执行历史。执行一次计划后会出现在这里。</div>
      <div v-else class="run-history">
        <article v-for="run in retryRuns" :key="run.id" class="run-card" :class="`run-${run.status}`">
          <div class="run-top">
            <div>
              <b>#{{ run.id }} · {{ statusLabel(run.status) }}</b>
              <span>{{ fmtTime(run.started_at) }} · {{ run.trade_date }}</span>
            </div>
            <em>改善 {{ run.improved_cells }} / 回退 {{ run.regressed_cells }}</em>
          </div>
          <p>{{ run.change_summary || run.message || run.after_summary || '-' }}</p>
          <div class="run-metrics">
            <span>执行 {{ run.steps_total }} 步</span>
            <span>失败 {{ run.steps_failed }} 步</span>
            <span>变化格子 {{ run.coverage_diff?.changed_cells || 0 }}</span>
            <span>剩余计划 {{ run.remaining_steps }}</span>
            <span>跳过 {{ run.remaining_skipped }}</span>
          </div>
          <div v-if="run.cell_changes?.length" class="change-list compact">
            <div v-for="change in run.cell_changes.slice(0, 6)" :key="`${run.id}-${change.exchange}-${change.kind}`" class="change-row" :class="changeClass(change.direction)">
              <b>{{ exchangeName(change.exchange) }} · {{ kindLabel(change.kind) }}</b>
              <span>{{ statusLabel(change.before?.status) }} {{ change.before?.rows ?? 0 }} → {{ statusLabel(change.after?.status) }} {{ change.after?.rows ?? 0 }}</span>
              <em>{{ Number(change.row_delta || 0) > 0 ? '+' : '' }}{{ change.row_delta || 0 }}</em>
            </div>
          </div>
          <details>
            <summary>查看步骤</summary>
            <div class="run-steps">
              <div v-for="step in run.executed" :key="`${run.id}-${step.type}-${step.exchange}-${step.kind}-${step.priority}`" class="run-step" :class="step.status === 'failed' ? 'bad' : 'ok'">
                <b>{{ step.type }} · {{ exchangeName(step.exchange) }} · {{ kindLabel(step.kind) }}</b>
                <span>{{ step.summary || step.error || '-' }}</span>
                <div v-if="step.changes?.length" class="change-list">
                  <div v-for="change in step.changes.slice(0, 4)" :key="`${run.id}-${step.type}-${change.exchange}-${change.kind}`" class="change-row" :class="changeClass(change.direction)">
                    <b>{{ exchangeName(change.exchange) }} · {{ kindLabel(change.kind) }}</b>
                    <span>{{ statusLabel(change.before?.status) }} {{ change.before?.rows ?? 0 }} → {{ statusLabel(change.after?.status) }} {{ change.after?.rows ?? 0 }}</span>
                    <em>{{ Number(change.row_delta || 0) > 0 ? '+' : '' }}{{ change.row_delta || 0 }}</em>
                  </div>
                </div>
              </div>
            </div>
          </details>
        </article>
      </div>
    </SectionCard>

    <SectionCard title="覆盖矩阵" style="margin-top:16px">
      <div class="matrix-table">
        <table>
          <thead><tr><th>交易所</th><th v-for="kind in coverageKinds" :key="kind.key">{{ kind.label }}</th><th>结论</th></tr></thead>
          <tbody>
            <tr v-for="row in coverageRows" :key="row.exchange">
              <td>{{ exchangeName(row.exchange) }}</td>
              <td v-for="kind in coverageKinds" :key="`${row.exchange}-${kind.key}`">
                <span class="status-pill" :class="`status-${cell(row, kind.key).status}`" :title="cell(row, kind.key).message">
                  {{ cellLabel(cell(row, kind.key)) }}
                </span>
              </td>
              <td class="note-cell">{{ row.summary || '-' }}</td>
            </tr>
            <tr v-if="!coverageRows.length"><td class="empty-cell" colspan="9">暂无覆盖矩阵</td></tr>
          </tbody>
        </table>
      </div>
    </SectionCard>

    <div class="exchange-grid">
      <SectionCard v-for="item in diagnostics" :key="item.exchange" :title="`${exchangeName(item.exchange)} 诊断`">
        <div class="diag-summary" :class="`diag-${item.status}`">{{ item.summary || statusLabel(item.status) }}</div>
        <div v-if="item.error_summary?.top_code" class="diag-cause">
          <b>{{ item.error_summary.summary }}</b>
        </div>
        <div v-if="!item.issues?.length" class="empty-state small success">暂无明显问题。</div>
        <div v-else class="issue-list">
          <article v-for="issue in item.issues" :key="`${item.exchange}-${issue.kind}-${issue.status}`" class="issue-card" :class="`issue-${issue.severity}`">
            <div class="issue-head">
              <b>{{ kindLabel(issue.kind) }}</b>
              <span :class="`status-text-${issue.status}`">{{ statusLabel(issue.status) }}</span>
            </div>
            <p>{{ issue.message }}</p>
            <div v-if="issue.error_category" class="issue-cause">
              <b>{{ issue.error_category.label }}</b>
              <span>{{ issue.error_category.reason }}</span>
              <em>{{ issue.error_category.suggestion }}</em>
            </div>
            <div class="issue-meta">
              <span>run: {{ issue.latest_run ? `${issue.latest_run.status} / saved ${issue.latest_run.saved}` : '-' }}</span>
              <span>gap: {{ issue.latest_gap ? `${issue.latest_gap.status} / ${issue.latest_gap.message}` : '-' }}</span>
              <span>raw: {{ issue.latest_archive ? `#${issue.latest_archive.id} / ${fmtBytes(issue.latest_archive.size_bytes)}` : '-' }}</span>
            </div>
          </article>
        </div>
        <div class="action-list">
          <button
            v-for="action in item.actions || []"
            :key="`${item.exchange}-${action.type}-${action.kind || action.note}`"
            class="mini-action"
            :disabled="runningAction === `${item.exchange}-${action.kind}` || action.type !== 'recollect'"
            :title="action.note || action.endpoint || ''"
            @click="runRecollect(item.exchange, action.kind)"
          >
            {{ action.type === 'recollect' ? `补采${kindLabel(action.kind)}` : action.type }}
          </button>
        </div>
      </SectionCard>
    </div>

    <SectionCard title="Raw Archive / Parser Replay" style="margin-top:16px">
      <div class="archive-toolbar">
        <select v-model="archiveExchange" @change="loadArchives">
          <option value="">全部交易所</option>
          <option value="DCE">DCE</option>
          <option value="INE">INE</option>
        </select>
        <select v-model="archiveKind" @change="loadArchives">
          <option value="">全部类型</option>
          <option value="daily">日行情</option>
          <option value="seat_rank">席位</option>
          <option value="seat_rank_browser_probe">席位 Browser Probe</option>
          <option value="basis">基差</option>
          <option value="warehouse_receipt">仓单</option>
        </select>
        <button class="secondary" :disabled="loadingArchives" @click="loadArchives">刷新原始响应</button>
      </div>
      <div class="archive-table">
        <table>
          <thead><tr><th>ID</th><th>交易所</th><th>类型</th><th>来源</th><th>行数</th><th>大小</th><th>错误</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="row in archives" :key="row.id">
              <td>#{{ row.id }}</td>
              <td>{{ exchangeName(row.exchange) }}</td>
              <td>{{ kindLabel(row.kind) }}</td>
              <td>{{ row.source }}</td>
              <td>{{ row.rows }}</td>
              <td>{{ fmtBytes(row.size_bytes) }}</td>
              <td class="note-cell">{{ row.error || '-' }}</td>
              <td>
                <button class="mini-action" :disabled="replaying === row.id" @click="replay(row)">{{ replaying === row.id ? '处理中...' : 'Replay' }}</button>
                <button v-if="row.kind?.endsWith('_browser_probe')" class="mini-action probe" :disabled="replaying === row.id" @click="loadPromotionPreview(row)">Preview</button>
              </td>
            </tr>
            <tr v-if="!archives.length"><td class="empty-cell" colspan="8">暂无 raw archive</td></tr>
          </tbody>
        </table>
      </div>
      <div v-if="replayResult" class="replay-result">
        <div class="replay-head">
          <b>Replay #{{ replayResult.file?.id }} · {{ statusLabel(replayResult.status) }}</b>
          <span>{{ replayResult.message }}</span>
        </div>
        <div class="replay-stats">
          <span>输入 {{ replayResult.input_rows ?? 0 }}</span>
          <span>解析 {{ replayResult.parsed_rows ?? 0 }}</span>
          <span>成功率 {{ replayResult.success_rate ?? 0 }}%</span>
          <span>跳过 {{ replayResult.skipped_rows ?? 0 }}</span>
          <span>错误 {{ replayResult.error_count ?? 0 }}</span>
        </div>
        <div v-if="replayResult.parser_dry_run" class="parser-dry-run">
        <div class="parser-head">
          <b>DCE Parser Dry-run · {{ statusLabel(replayResult.parser_dry_run.status) }}</b>
          <span>{{ replayResult.parser_dry_run.message }}</span>
        </div>
        <div class="replay-stats">
          <span>尝试表格 {{ replayResult.parser_dry_run.tables_attempted ?? replayResult.parser_dry_run.input_rows ?? 0 }}</span>
          <span>解析行 {{ replayResult.parser_dry_run.parsed_rows ?? 0 }}</span>
          <span>错误 {{ replayResult.parser_dry_run.error_count ?? 0 }}</span>
        </div>
        <div v-if="firstParserResult" class="parser-grid">
          <div>
            <b>列映射</b>
            <pre>{{ JSON.stringify(firstParserResult.mapping || {}, null, 2) }}</pre>
          </div>
          <div>
            <b>样例行</b>
            <pre>{{ JSON.stringify(firstParserResult.sample || [], null, 2) }}</pre>
          </div>
        </div>
        <div v-if="replayResult.promotion_guard" class="promotion-guard" :class="replayResult.promotion_guard.allowed ? 'pass' : 'blocked'">
          <div class="parser-head">
            <b>Promotion Guard · {{ replayResult.promotion_guard.allowed ? 'PASS' : 'BLOCKED' }}</b>
            <span>{{ replayResult.promotion_guard.summary }}</span>
          </div>
          <div class="replay-stats">
            <span>输入 {{ replayResult.promotion_guard.metrics?.input_rows ?? 0 }}</span>
            <span>解析 {{ replayResult.promotion_guard.metrics?.parsed_rows ?? 0 }}</span>
            <span>成功率 {{ replayResult.promotion_guard.metrics?.success_rate ?? 0 }}%</span>
            <span>错误率 {{ replayResult.promotion_guard.metrics?.error_rate ?? 0 }}%</span>
          </div>
          <div v-if="replayResult.promotion_guard.reasons?.length" class="guard-reasons">
            <span v-for="reason in replayResult.promotion_guard.reasons" :key="reason.code">{{ reason.message }}</span>
          </div>
          <div class="op-tail">{{ replayResult.promotion_guard.next_action }}</div>
        </div>
        <details v-if="firstParserResult?.errors?.length" class="parser-errors">
          <summary>查看 parser dry-run 错误 {{ firstParserResult.errors.length }} 条</summary>
          <pre>{{ JSON.stringify(firstParserResult.errors, null, 2) }}</pre>
        </details>
      </div>
      <pre>{{ JSON.stringify({ stats: replayResult.stats, sample: replayResult.sample, errors: replayResult.errors }, null, 2) }}</pre>
      </div>
      <div v-if="promotionPreview" class="promotion-preview" :class="promotionPreview.status">
        <div class="parser-head">
          <b>Promotion Preview · {{ promotionPreview.status }}</b>
          <span>{{ promotionPreview.message }}</span>
        </div>
        <div class="replay-stats">
          <span>预览行 {{ promotionPreview.preview_count ?? 0 }}</span>
          <span>会写库 {{ promotionPreview.would_write ? 'YES' : 'NO' }}</span>
          <span>Guard {{ promotionPreview.promotion_guard?.allowed ? 'PASS' : 'BLOCKED' }}</span>
        </div>
        <div v-if="promotionPreview.status === 'ready'" class="promotion-actions">
          <button class="danger" :disabled="replaying === promotionPreview.file?.id" @click="applyPromotion(promotionPreview.file)">确认入库</button>
          <span>需要 Guard PASS；入库按精确行去重，不会清空已有席位数据。</span>
        </div>
        <div v-if="promotionPreview.inserted !== undefined" class="guard-reasons">
          <span>已插入 {{ promotionPreview.inserted || 0 }} 行，跳过重复 {{ promotionPreview.skipped || 0 }} 行</span>
        </div>
        <div v-if="promotionPreview.promotion_guard?.reasons?.length" class="guard-reasons">
          <span v-for="reason in promotionPreview.promotion_guard.reasons" :key="reason.code">{{ reason.message }}</span>
        </div>
        <div v-if="promotionPreviewRows.length" class="preview-table">
          <table>
            <thead>
              <tr>
                <th>record_id</th><th>rank</th><th>席位</th><th>成交</th><th>成交变化</th><th>多头持仓</th><th>多头变化</th><th>空头持仓</th><th>空头变化</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in promotionPreviewRows" :key="row.record_id">
                <td class="mono" :title="row.record_id">{{ shortId(row.record_id) }}</td>
                <td>{{ row.rank ?? '-' }}</td>
                <td>{{ row.vol_party_name || row.long_party_name || row.short_party_name || '-' }}</td>
                <td>{{ fmtNum(row.vol) }}</td>
                <td>{{ fmtSigned(row.vol_chg) }}</td>
                <td>{{ fmtNum(row.long_open_interest) }}</td>
                <td>{{ fmtSigned(row.long_open_interest_chg) }}</td>
                <td>{{ fmtNum(row.short_open_interest) }}</td>
                <td>{{ fmtSigned(row.short_open_interest_chg) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <details>
          <summary>查看 promotion preview 原始 JSON</summary>
          <pre>{{ JSON.stringify({ guard: promotionPreview.promotion_guard, rows: promotionPreview.preview_rows }, null, 2) }}</pre>
        </details>
      </div>
    </SectionCard>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api.js'
import KpiCard from '../components/KpiCard.vue'
import SectionCard from '../components/SectionCard.vue'
import { exchangeName } from '../exchange.js'
import { kindLabel, statusLabel } from '../labels.js'
import { normalizeApiError } from '../utils/errors.js'
import { confirmDanger } from '../utils/confirm.js'

const loading = ref(false)
const loadingArchives = ref(false)
const tradeDate = ref('')
const tradeDateInput = ref('')
const coverage = ref({ rows: [], kinds: [], summary: {} })
const sourceHealth = ref({ sources: [], summary: {} })
const retryPlan = ref({ steps: [], skipped: [], summary: {} })
const retryHistory = ref({ runs: [], summary: {} })
const diagnosticData = ref({ exchanges: [] })
const archives = ref([])
const archiveExchange = ref('')
const archiveKind = ref('')
const replayResult = ref(null)
const promotionPreview = ref(null)
const replaying = ref(null)
const runningAction = ref('')
const loadingPlan = ref(false)
const loadingHistory = ref(false)
const operationResult = ref(null)
const notice = ref('')
const error = ref('')

const coverageRows = computed(() => coverage.value.rows || [])
const coverageKinds = computed(() => coverage.value.kinds || [])
const coverageSummary = computed(() => coverage.value.summary || {})
const sourceHealthRows = computed(() => sourceHealth.value.sources || [])
const sourceHealthSummary = computed(() => sourceHealth.value.summary || {})
const sourceHealthColor = computed(() => sourceHealthSummary.value.status === 'good' ? '#16c79a' : sourceHealthSummary.value.status === 'warn' ? '#f5a623' : '#e94560')
const retryPlanSteps = computed(() => retryPlan.value.steps || [])
const retryPlanSkipped = computed(() => retryPlan.value.skipped || [])
const retryRuns = computed(() => retryHistory.value.runs || [])
const diagnostics = computed(() => diagnosticData.value.exchanges || [])
const firstParserResult = computed(() => {
  const dry = replayResult.value?.parser_dry_run
  if (!dry) return null
  if (Array.isArray(dry.results)) return dry.results[0] || null
  return dry
})
const promotionPreviewRows = computed(() => promotionPreview.value?.preview_rows || [])

function cell(row, kind) { return row?.cells?.[kind] || { status: 'missing', rows: 0, message: '未采集' } }
function cellLabel(c) {
  const labels = { ok: '✓', fallback: '备', partial: '!', missing: '—', failed: '×', not_supported: 'NA' }
  const base = labels[c.status] || '?'
  return ['ok', 'fallback', 'partial'].includes(c.status) && c.rows ? `${base} ${fmtNum(c.rows)}` : base
}
function fmtNum(v) { const n = Number(v || 0); if (!Number.isFinite(n) || n === 0) return v === 0 ? '0' : '-'; if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`; return String(Math.round(n)) }
function fmtSigned(v) { const n = Number(v || 0); if (!Number.isFinite(n) || n === 0) return v === 0 ? '0' : '-'; return n > 0 ? `+${fmtNum(n)}` : fmtNum(n) }
function shortId(v) { const s = String(v || ''); return s.length > 22 ? `${s.slice(0, 18)}…` : s }
function fmtBytes(v) { const n = Number(v || 0); if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`; if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`; return `${n} B` }
function fmtDelta(v) { const n = Number(v || 0); return n > 0 ? `+${n}%` : `${n}%` }
function fmtTime(v) { return v ? String(v).replace('T', ' ').slice(0, 19) : '-' }
function changeClass(direction) { return direction === 'improved' ? 'good' : direction === 'regressed' ? 'bad' : 'neutral' }

async function resolveLatestDate() {
  const { data } = await api.get('/dataset/varieties/latest')
  return data?.trade_date || ''
}

async function load() {
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    const date = tradeDateInput.value.trim() || tradeDate.value || await resolveLatestDate()
    if (!date) throw new Error('暂无可诊断日期')
    tradeDate.value = date
    tradeDateInput.value = date
    const [coverageResp, healthResp, planResp, diagResp] = await Promise.all([
      api.get(`/quality/coverage/${date}`),
      api.get(`/quality/source-health/${date}`),
      api.get(`/quality/retry-plan/${date}`),
      api.get(`/quality/diagnostics/${date}`),
    ])
    coverage.value = coverageResp.data || { rows: [], kinds: [], summary: {} }
    sourceHealth.value = healthResp.data || { sources: [], summary: {} }
    retryPlan.value = planResp.data || { steps: [], skipped: [], summary: {} }
    diagnosticData.value = diagResp.data || { exchanges: [] }
    await Promise.all([loadArchives(), loadRetryHistory()])
  } catch (e) {
    error.value = normalizeApiError(e, '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadRetryHistory() {
  if (!tradeDate.value) return
  loadingHistory.value = true
  try {
    const { data } = await api.get('/quality/retry-runs', { params: { trade_date: tradeDate.value, limit: 12 } })
    retryHistory.value = data || { runs: [], summary: {} }
  } finally {
    loadingHistory.value = false
  }
}

async function loadArchives() {
  if (!tradeDate.value) return
  loadingArchives.value = true
  try {
    const params = { trade_date: tradeDate.value, limit: 50 }
    if (archiveExchange.value) params.exchange = archiveExchange.value
    if (archiveKind.value) params.kind = archiveKind.value
    const { data } = await api.get('/dataset/raw-archives', { params })
    archives.value = data || []
  } finally {
    loadingArchives.value = false
  }
}

async function replay(row) {
  replaying.value = row.id
  replayResult.value = null
  promotionPreview.value = null
  try {
    const { data } = await api.post(`/dataset/raw-archives/${row.id}/replay`)
    replayResult.value = data
    operationResult.value = {
      summary: `Replay #${row.id}：解析 ${data.parsed_rows ?? 0}/${data.input_rows ?? 0} 行，成功率 ${data.success_rate ?? 0}%`,
      message: data.message,
      note: data.status === 'unsupported' ? '该类型暂未实现 parser replay。' : 'dry-run only，未修改数据库。',
      coverage_diff: null,
    }
  } catch (e) {
    error.value = normalizeApiError(e, 'Replay 失败')
  } finally {
    replaying.value = null
  }
}

async function loadPromotionPreview(row) {
  if (!row?.id) return
  replaying.value = row.id
  promotionPreview.value = null
  try {
    const { data } = await api.post(`/dataset/raw-archives/${row.id}/promotion-preview`)
    promotionPreview.value = data
    operationResult.value = {
      summary: data?.status === 'ready' ? `Promotion Preview #${row.id}：预览 ${data.preview_count || 0} 行` : `Promotion Preview #${row.id}：${data?.promotion_guard?.summary || '已阻断'}`,
      message: data?.message,
      note: data?.would_write ? '警告：该接口不应写库' : 'preview only，未修改数据库。',
      coverage_diff: {},
    }
  } catch (e) {
    error.value = normalizeApiError(e, 'Promotion Preview 失败')
  } finally {
    replaying.value = null
  }
}

async function applyPromotion(file) {
  if (!file?.id) return
  const token = `PROMOTE-${file.id}`
  if (!confirmDanger(`确认将 Raw Archive #${file.id} 的 Promotion Preview 写入 seat_rank_rows？\n\n确认令牌：${token}\n\n该操作会按精确席位行去重，不会清空已有席位数据。`)) return
  replaying.value = file.id
  try {
    const { data } = await api.post(`/dataset/raw-archives/${file.id}/promotion-apply`, null, { params: { confirm: token } })
    promotionPreview.value = data
    operationResult.value = {
      summary: `Promotion Apply #${file.id}：插入 ${data.inserted || 0} 行，跳过 ${data.skipped || 0} 行`,
      message: data.message,
      note: data.status === 'applied' ? '已受控写入 seat_rank_rows，并记录 crawler run / data gap。' : '没有新增写入。',
      coverage_diff: {},
    }
    await Promise.all([loadArchives(), load()])
  } catch (e) {
    error.value = normalizeApiError(e, 'Promotion Apply 失败')
  } finally {
    replaying.value = null
  }
}


async function runRecollect(exchange, kind) {
  return runRecollectInternal(exchange, kind)
}

async function runFirstRetryStep() {
  const step = retryPlanSteps.value[0]
  if (step) await runRetryStep(step)
}

async function runRetryPlan() {
  if (!tradeDate.value) return
  if (!confirmDanger(`确认执行 ${tradeDate.value} 的自动补采计划？最多执行 3 步，并会重建相关日报。`)) return
  loadingPlan.value = true
  error.value = ''
  notice.value = ''
  try {
    const { data } = await api.post(`/quality/retry-plan/${tradeDate.value}/run`, null, { params: { max_steps: 3, stop_on_failure: false, rebuild: true } })
    notice.value = data?.summary || '自动补采计划执行完成'
    const improved = (data?.executed || []).reduce((sum, item) => sum + Number(item.coverage_diff?.improved_cells || 0), 0)
    const failed = (data?.executed || []).filter(item => item.status === 'failed').length
    operationResult.value = {
      summary: data?.summary || `执行 ${(data?.executed || []).length} 步，改善 ${improved} 项`,
      message: `执行 ${(data?.executed || []).length} 步，失败 ${failed} 步`,
      note: `job #${data?.job_id || '-'} · ${data?.job_status || '-'}`,
      coverage_diff: aggregateRunnerDiff(data?.executed || []),
    }
    await load()
  } catch (e) {
    error.value = normalizeApiError(e, '执行计划失败')
  } finally {
    loadingPlan.value = false
  }
}

function aggregateRunnerDiff(items) {
  const last = [...items].reverse().find(item => item.coverage_diff)?.coverage_diff || {}
  const changes = aggregateCellChanges(items)
  return {
    ...last,
    improved_cells: items.reduce((sum, item) => sum + Number(item.coverage_diff?.improved_cells || 0), 0),
    regressed_cells: items.reduce((sum, item) => sum + Number(item.coverage_diff?.regressed_cells || 0), 0),
    changed_cells: changes.length,
    changes,
  }
}

function aggregateCellChanges(items) {
  const merged = new Map()
  for (const item of items || []) {
    for (const change of item.coverage_diff?.changes || []) {
      const key = `${change.exchange}-${change.kind}`
      const existing = merged.get(key)
      if (!existing) merged.set(key, { ...change, row_delta: Number(change.row_delta || 0) })
      else {
        existing.after = change.after || existing.after
        existing.direction = change.direction || existing.direction
        existing.row_delta = Number(existing.row_delta || 0) + Number(change.row_delta || 0)
      }
    }
  }
  return [...merged.values()].sort((a, b) => (a.direction === 'improved' ? 0 : a.direction === 'regressed' ? 1 : 2) - (b.direction === 'improved' ? 0 : b.direction === 'regressed' ? 1 : 2))
}

async function runRetryStep(step) {
  if (!step) return
  if (step.type === 'recollect') return runRecollectInternal(step.exchange, step.kind)
  if (step.type === 'collect_quhe') return runCollectQuhe(step)
}

async function runBrowserProbe(step) {
  if (!tradeDate.value || !step?.exchange || !step?.browser_probe) return
  if (!confirmDanger(`确认用 CloakBrowser 对 ${tradeDate.value} ${step.exchange} 做官方页低频探测？只写 raw archive，不会入库正式席位数据。`)) return
  loadingPlan.value = true
  runningAction.value = `${step.exchange}-${step.kind}-browser_probe`
  error.value = ''
  notice.value = ''
  try {
    const { data } = await api.post(`/dataset/browser-probe/${tradeDate.value}/${step.exchange}`, null, { params: { kind: step.kind } })
    notice.value = data?.ok ? `${step.exchange} Browser Probe 已归档` : `${step.exchange} Browser Probe 已记录失败归档`
    operationResult.value = {
      summary: data?.ok ? `Browser Probe #${data.archive_id}：${data.title || '已抓取'}` : `Browser Probe #${data?.archive_id || '-'}：${data?.error || '探测失败'}`,
      message: data?.source_file || '',
      note: '只写 raw archive；请在 Raw Archive 里 Replay 检查页面信号。',
      coverage_diff: {},
    }
    archiveExchange.value = step.exchange
    archiveKind.value = `${step.kind}_browser_probe`
    await loadArchives()
    if (data?.archive_id) {
      const row = archives.value.find(item => item.id === data.archive_id)
      if (row) await replay(row)
    }
  } catch (e) {
    error.value = normalizeApiError(e, 'Browser Probe 失败')
  } finally {
    runningAction.value = ''
    loadingPlan.value = false
  }
}

async function runRecollectInternal(exchange, kind) {
  if (!tradeDate.value || !exchange || !kind) return
  if (!confirmDanger(`确认补采 ${tradeDate.value} ${exchange} 的${kindLabel(kind)}数据，并重建日报？`)) return
  runningAction.value = `${exchange}-${kind}`
  loadingPlan.value = true
  error.value = ''
  notice.value = ''
  try {
    const { data } = await api.post(`/reports/${tradeDate.value}/recollect`, null, { params: { exchange, kinds: kind, rebuild: true } })
    notice.value = data?.summary || `${exchange} ${kindLabel(kind)}补采完成`
    operationResult.value = {
      summary: data?.coverage_diff?.summary || data?.summary || `${exchange} ${kindLabel(kind)}补采完成`,
      message: data?.summary,
      note: `job #${data?.job_id || '-'} · ${data?.job_status || '-'}`,
      coverage_diff: data?.coverage_diff || {},
    }
    await load()
  } catch (e) {
    error.value = normalizeApiError(e, '补采失败')
  } finally {
    runningAction.value = ''
    loadingPlan.value = false
  }
}

async function runCollectQuhe(step) {
  if (!tradeDate.value) return
  if (!confirmDanger(`确认刷新 ${tradeDate.value} 的曲合/官方增强数据？`)) return
  loadingPlan.value = true
  error.value = ''
  notice.value = ''
  try {
    const { data } = await api.post(`/dataset/collect-quhe/${tradeDate.value}`)
    notice.value = `${step?.source || '增强源'}刷新完成`
    operationResult.value = {
      summary: `增强源刷新完成：${data?.materialized?.count ?? 0} 个品种已物化`,
      message: step?.reason || '',
      note: '已刷新曲合/官方增强数据；请查看覆盖矩阵是否改善。',
      coverage_diff: {},
    }
    await load()
  } catch (e) {
    error.value = normalizeApiError(e, '增强源刷新失败')
  } finally {
    loadingPlan.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-head { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:18px; gap:12px; }
.page-title { color:#1a1a2e; }
.muted { color:#888; margin-top:4px; line-height:1.6; }
.head-actions { display:flex; gap:8px; align-items:center; }
.head-actions input, .archive-toolbar select { border:1px solid #ddd; border-radius:10px; padding:10px 12px; background:#fff; }
.primary { background:#e94560; color:white; border:0; border-radius:10px; padding:10px 16px; font-weight:800; cursor:pointer; }
.primary.small { padding:8px 12px; }
.secondary, .mini-action { background:#f1f5ff; color:#3157d5; border:1px solid #dbe3ff; border-radius:10px; padding:8px 12px; font-weight:800; cursor:pointer; }
.primary:disabled, .secondary:disabled, .mini-action:disabled { opacity:.55; cursor:wait; }
.notice { margin-bottom:16px; padding:11px 14px; border-radius:10px; }
.notice.success { background:#effaf5; color:#15845f; border:1px solid #d6f3e5; }
.notice.error { background:#fff1f2; color:#be123c; border:1px solid #fecdd3; }
.op-card { margin-bottom:16px; }
.op-summary { color:#0f172a; font-weight:900; line-height:1.5; margin-bottom:10px; }
.op-tail { margin-top:10px; color:#64748b; font-size:13px; }
.replay-stats em { font-style:normal; color:#64748b; }
.kpi-row { display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin-bottom:16px; }
.source-health-head { display:flex; justify-content:space-between; gap:12px; align-items:center; color:#334155; margin-bottom:12px; }
.source-health-head span { color:#64748b; font-size:13px; }
.source-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.source-card { border:1px solid #e8edf5; border-radius:14px; padding:13px; background:#fff; display:grid; gap:9px; }
.source-good { border-color:#bbf7d0; background:#f7fffb; }
.source-warn { border-color:#fed7aa; background:#fffaf0; }
.source-bad { border-color:#fecdd3; background:#fff8f9; }
.source-top { display:flex; justify-content:space-between; gap:8px; align-items:center; }
.source-top b { color:#0f172a; }
.source-top em { font-style:normal; font-weight:950; color:#3157d5; background:#eef2ff; border:1px solid #dbe3ff; border-radius:999px; padding:4px 8px; }
.source-card p { margin:0; color:#475569; line-height:1.45; font-size:13px; }
.source-metrics { display:flex; flex-wrap:wrap; gap:6px; }
.source-metrics span { background:#f8fafc; color:#64748b; border:1px solid #e2e8f0; border-radius:999px; padding:4px 7px; font-size:12px; font-weight:850; }
.source-cause, .diag-cause, .issue-cause { display:grid; gap:3px; background:#fff7ed; border:1px solid #fed7aa; border-radius:10px; padding:7px 9px; font-size:12px; line-height:1.45; color:#9a3412; }
.source-cause b, .diag-cause b, .issue-cause b { color:#7c2d12; }
.issue-cause em { font-style:normal; color:#64748b; }
.source-error { color:#be123c; background:#fff1f2; border:1px solid #fecdd3; border-radius:10px; padding:7px 9px; font-size:12px; line-height:1.4; }
.matrix-table, .archive-table { width:100%; overflow:auto; }
table { width:100%; min-width:860px; border-collapse:separate; border-spacing:0; font-size:13px; }
th { background:#f8fafc; color:#475569; text-align:left; padding:11px 12px; border-bottom:1px solid #e2e8f0; white-space:nowrap; }
td { padding:11px 12px; border-bottom:1px solid #f1f5f9; white-space:nowrap; }
.note-cell { white-space:normal; color:#64748b; min-width:220px; }
.status-pill { display:inline-flex; min-width:46px; justify-content:center; border-radius:999px; padding:4px 8px; font-weight:950; border:1px solid #e2e8f0; background:#f8fafc; color:#64748b; }
.status-ok { background:#ecfdf5; border-color:#bbf7d0; color:#047857; }
.status-fallback { background:#eef2ff; border-color:#dbe3ff; color:#3157d5; }
.status-partial { background:#fff7ed; border-color:#fed7aa; color:#b45309; }
.status-missing { background:#f8fafc; border-color:#e2e8f0; color:#94a3b8; }
.status-failed { background:#fff1f2; border-color:#fecdd3; color:#be123c; }
.status-not_supported { background:#f1f5f9; border-color:#e2e8f0; color:#94a3b8; }
.exchange-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }
.diag-summary { padding:10px 12px; border-radius:12px; background:#f8fafc; color:#475569; margin-bottom:12px; font-weight:800; }
.diag-failed { background:#fff1f2; color:#be123c; } .diag-partial { background:#fff7ed; color:#b45309; } .diag-ok { background:#ecfdf5; color:#047857; }
.issue-list { display:grid; gap:10px; }
.issue-card { border:1px solid #e8edf5; border-radius:14px; padding:12px; background:#fff; }
.issue-error { border-color:#fecdd3; background:#fff8f9; } .issue-warning { border-color:#fed7aa; background:#fffaf0; }
.issue-head { display:flex; justify-content:space-between; gap:8px; font-weight:900; }
.issue-card p { color:#475569; line-height:1.5; margin:8px 0; }
.issue-meta { display:grid; gap:5px; color:#64748b; font-size:12px; }
.action-list, .archive-toolbar, .replay-stats { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
.retry-head { display:flex; justify-content:space-between; gap:12px; align-items:center; color:#334155; margin-bottom:12px; }
.retry-actions { display:flex; gap:8px; flex-wrap:wrap; }
.retry-head b { display:block; color:#0f172a; }
.retry-head span { display:block; margin-top:4px; color:#64748b; font-size:13px; }
.retry-list { display:grid; gap:10px; }
.retry-step { border:1px solid #e8edf5; border-radius:14px; padding:13px; background:#fff; display:grid; gap:9px; }
.retry-top { display:flex; justify-content:space-between; gap:8px; align-items:center; }
.retry-top b { color:#0f172a; }
.retry-top em { font-style:normal; color:#b45309; background:#fff7ed; border:1px solid #fed7aa; border-radius:999px; padding:4px 8px; font-size:12px; font-weight:950; }
.retry-step p { margin:0; color:#475569; line-height:1.5; }
.retry-meta { display:grid; gap:5px; color:#64748b; font-size:12px; }
.retry-step-actions { display:flex; gap:8px; flex-wrap:wrap; }
.mini-action.probe { background:#fff7ed; color:#b45309; border-color:#fed7aa; }
.browser-probe { display:grid; gap:4px; padding:9px 10px; border-radius:11px; border:1px solid #fed7aa; background:#fffaf0; color:#9a3412; font-size:12px; line-height:1.45; }
.browser-probe b { color:#7c2d12; }
.browser-probe em { color:#64748b; font-style:normal; }
.history-head { display:flex; justify-content:space-between; gap:12px; align-items:center; color:#334155; margin-bottom:12px; }
.history-head b { display:block; color:#0f172a; }
.history-head span { display:block; margin-top:4px; color:#64748b; font-size:13px; }
.run-history { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }
.run-card { border:1px solid #e8edf5; border-radius:14px; padding:13px; background:#fff; display:grid; gap:9px; }
.run-success { border-left:5px solid #16a34a; } .run-partial { border-left:5px solid #f59e0b; } .run-failed { border-left:5px solid #dc2626; } .run-running { border-left:5px solid #3f5efb; }
.run-top { display:flex; justify-content:space-between; gap:8px; align-items:flex-start; }
.run-top b { display:block; color:#0f172a; }
.run-top span { display:block; margin-top:3px; color:#94a3b8; font-size:12px; }
.run-top em { font-style:normal; color:#3157d5; background:#eef2ff; border:1px solid #dbe3ff; border-radius:999px; padding:4px 8px; font-size:12px; font-weight:950; white-space:nowrap; }
.run-card p { margin:0; color:#475569; line-height:1.45; }
.run-metrics { display:flex; flex-wrap:wrap; gap:6px; }
.run-metrics span { background:#f8fafc; color:#64748b; border:1px solid #e2e8f0; border-radius:999px; padding:4px 7px; font-size:12px; font-weight:850; }
.run-card details summary { cursor:pointer; color:#334155; font-weight:900; }
.run-steps { display:grid; gap:7px; margin-top:8px; }
.run-step { display:grid; gap:6px; padding:8px 10px; border-radius:10px; background:#fbfdff; border:1px solid #eef2f7; }
.run-step.ok { border-left:4px solid #16a34a; } .run-step.bad { border-left:4px solid #dc2626; }
.run-step span { color:#64748b; font-size:12px; line-height:1.45; word-break:break-word; }
.change-list { display:grid; gap:6px; margin-top:4px; }
.change-list.compact { margin-top:2px; }
.change-row { display:grid; grid-template-columns:minmax(120px, 1fr) minmax(150px, 1.5fr) auto; gap:8px; align-items:center; padding:7px 9px; border-radius:10px; border:1px solid #e2e8f0; background:#f8fafc; font-size:12px; }
.change-row b { color:#0f172a; }
.change-row span { color:#64748b; }
.change-row em { font-style:normal; font-weight:950; color:#334155; }
.change-row.good { border-left:4px solid #16a34a; background:#f0fdf4; }
.change-row.bad { border-left:4px solid #dc2626; background:#fff7f7; }
.change-row.neutral { border-left:4px solid #94a3b8; }
.skip-details { margin-top:12px; color:#64748b; }
.skip-details summary { cursor:pointer; font-weight:900; color:#334155; }
.skip-list { display:grid; gap:6px; margin-top:8px; font-size:12px; }
.empty-state { padding:24px; text-align:center; color:#888; background:#fafafa; border-radius:10px; }
.empty-state.small { padding:18px; } .empty-state.success { color:#15845f; background:#effaf5; border:1px solid #d6f3e5; }
.empty-cell { text-align:center; color:#94a3b8; padding:24px !important; }
.replay-result { margin-top:14px; border:1px solid #e8edf5; border-radius:14px; padding:14px; background:#fbfdff; }
.replay-head, .parser-head { display:flex; justify-content:space-between; gap:12px; color:#334155; }
.parser-dry-run { margin-top:12px; padding:12px; border-radius:14px; border:1px solid #dbeafe; background:#f8fbff; display:grid; gap:10px; }
.promotion-preview { margin-top:12px; padding:12px; border-radius:14px; border:1px solid #e2e8f0; background:#fbfdff; display:grid; gap:10px; }
.promotion-preview.ready { border-color:#bbf7d0; background:#f0fdf4; }
.promotion-preview.blocked { border-color:#fed7aa; background:#fff7ed; }
.preview-table { overflow:auto; border:1px solid #e2e8f0; border-radius:12px; background:#fff; }
.preview-table table { min-width:980px; }
.preview-table .mono { font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; color:#3157d5; font-size:12px; }
.promotion-preview details summary { cursor:pointer; color:#334155; font-weight:900; }
.promotion-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; color:#64748b; font-size:12px; font-weight:800; }
.promotion-actions .danger { border:0; border-radius:10px; padding:8px 12px; background:#e94560; color:#fff; font-weight:900; cursor:pointer; }
.promotion-actions .danger:disabled { opacity:.55; cursor:not-allowed; }
.promotion-guard { padding:11px; border-radius:12px; display:grid; gap:8px; }
.promotion-guard.pass { border:1px solid #bbf7d0; background:#f0fdf4; }
.promotion-guard.blocked { border:1px solid #fed7aa; background:#fff7ed; }
.guard-reasons { display:grid; gap:5px; color:#9a3412; font-size:12px; }
.guard-reasons span { background:#ffedd5; border:1px solid #fed7aa; border-radius:8px; padding:6px 8px; }
.parser-head b { color:#1d4ed8; }
.parser-head span { color:#64748b; font-size:13px; }
.parser-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.parser-grid b { color:#334155; }
.parser-errors summary { cursor:pointer; color:#b45309; font-weight:900; }
.replay-stats span { background:#eef2ff; color:#3157d5; border:1px solid #dbe3ff; border-radius:999px; padding:5px 9px; font-weight:900; font-size:12px; }
pre { margin-top:12px; max-height:360px; overflow:auto; background:#0f172a; color:#dbeafe; border-radius:12px; padding:12px; font-size:12px; }
@media (max-width: 980px) { .kpi-row, .exchange-grid, .source-grid, .run-history, .change-row, .parser-grid { grid-template-columns:1fr; } .page-head, .head-actions, .source-health-head, .retry-head, .history-head { flex-direction:column; align-items:stretch; } }
</style>
