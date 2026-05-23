<template>
  <div class="settings">
    <h2 class="page-title">设置</h2>

    <SectionCard title="系统配置">
      <SimpleTable :columns="['项目', '值']" :data="settingsRows" />
    </SectionCard>

    <SectionCard title="通知推送" style="margin-top:16px">
      <form class="notify-form" @submit.prevent="saveTelegram">
        <h3>Telegram</h3>
        <label class="switch-row">
          <input v-model="telegramForm.enabled" type="checkbox" />
          <span>启用 Telegram 日报推送</span>
        </label>
        <div class="form-grid">
          <label>
            <span>机器人密钥</span>
            <input v-model="telegramForm.bot_token" :placeholder="telegramMasked ? '已配置，不想修改就保持不变' : '123456:ABC...'" autocomplete="off" />
          </label>
          <label>
            <span>接收人/群 ID</span>
            <input v-model="telegramForm.chat_id" placeholder="如 1744225772 或群组 ID" />
          </label>
        </div>
        <div class="form-actions">
          <button :disabled="savingTelegram">{{ savingTelegram ? '保存中...' : '保存 Telegram 配置' }}</button>
        </div>
      </form>

      <form class="notify-form notify-subform" @submit.prevent="saveWeChatBot">
        <h3>WeChatBot / 微信 Claw</h3>
        <label class="switch-row">
          <input v-model="wechatbotForm.enabled" type="checkbox" />
          <span>启用 WeChatBot 日报推送</span>
        </label>
        <div class="form-grid">
          <label>
            <span>转发地址（可空）</span>
            <input v-model="wechatbotForm.webhook_url" placeholder="http://.../send" autocomplete="off" />
          </label>
          <label>
            <span>密钥</span>
            <input v-model="wechatbotForm.token" :placeholder="wechatbotMasked ? '已配置，不想修改就保持不变' : 'ilink bot token'" autocomplete="off" />
          </label>
          <label>
            <span>服务地址</span>
            <input v-model="wechatbotForm.claw_base_url" placeholder="https://ilinkai.weixin.qq.com" />
          </label>
          <label>
            <span>接收人 ID</span>
            <input v-model="wechatbotForm.chat_id" placeholder="wxid / user_id / xxx@im.wechat" />
          </label>
        </div>
        <div class="form-actions">
          <button :disabled="savingWeChatBot">{{ savingWeChatBot ? '保存中...' : '保存 WeChatBot 配置' }}</button>
          <button type="button" class="ghost" :disabled="testingNotify" @click="testNotify">{{ testingNotify ? '测试中...' : '发一条测试消息' }}</button>
          <button type="button" class="ghost" :disabled="testingPush" @click="testPushLatest">{{ testingPush ? '推送中...' : '测试推送最新日报' }}</button>
          <span v-if="settingsMessage" class="form-message">{{ settingsMessage }}</span>
        </div>
        <div v-if="pushResults.length" class="push-results">
          <div class="push-results-title">最近一次通知测试结果</div>
          <div v-for="item in pushResults" :key="item.channel || item.reason" class="push-result" :class="pushResultTone(item)">
            <b>{{ channelLabel(item.channel) }}</b>
            <span>{{ pushResultStatus(item) }}</span>
            <small v-if="pushResultDetail(item)">{{ pushResultDetail(item) }}</small>
          </div>
        </div>
      </form>
    </SectionCard>

    <div class="grid-2">
      <SectionCard title="自选品种">
        <form class="inline-form" @submit.prevent="addSymbol">
          <input v-model="symbolForm.symbol" placeholder="品种/合约，如 RB 或 TA2609" />
          <input v-model="symbolForm.exchange" placeholder="交易所，可空" />
          <input v-model="symbolForm.name" placeholder="名称，可空" />
          <button>添加</button>
        </form>
        <form class="bulk-form" @submit.prevent="bulkImportSymbols">
          <textarea v-model="bulkSymbols" placeholder="批量导入，一行或空格分隔：TA2609 RU2609 PX2607 JD2606 CJ2609 A2607 NI RB PB"></textarea>
          <div class="form-actions">
            <button :disabled="bulkImporting">{{ bulkImporting ? '导入中...' : '批量导入自选' }}</button>
            <label class="mini-check"><input v-model="bulkReplace" type="checkbox" /> 替换现有自选</label>
            <span v-if="watchMessage" class="form-message">{{ watchMessage }}</span>
          </div>
        </form>
        <div class="list">
          <div v-for="x in symbols" :key="x.id" class="item">
            <div><b>{{ x.symbol }}</b> <span>{{ exchangeName(x.exchange) }}</span> <span>{{ x.name || '-' }}</span></div>
            <button class="danger" @click="deleteSymbol(x.id)">删除</button>
          </div>
          <div v-if="!symbols.length" class="empty">暂无自选品种</div>
        </div>
      </SectionCard>

      <SectionCard title="关注席位">
        <form class="inline-form" @submit.prevent="addSeat">
          <input v-model="seatForm.seat_name" placeholder="席位，如 中信期货" />
          <input v-model="seatForm.alias" placeholder="别名，可空" />
          <button>添加</button>
        </form>
        <div class="list">
          <div v-for="x in seats" :key="x.id" class="item">
            <div><b>{{ x.seat_name }}</b> <span>{{ x.alias || '-' }}</span></div>
            <button class="danger" @click="deleteSeat(x.id)">删除</button>
          </div>
          <div v-if="!seats.length" class="empty">暂无关注席位</div>
        </div>
      </SectionCard>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api.js'
import SectionCard from '../components/SectionCard.vue'
import SimpleTable from '../components/SimpleTable.vue'
import { exchangeName } from '../exchange.js'

const settings = ref({})
const symbols = ref([])
const seats = ref([])
const symbolForm = ref({ symbol: '', exchange: '', name: '' })
const bulkSymbols = ref('')
const bulkReplace = ref(false)
const bulkImporting = ref(false)
const watchMessage = ref('')
const seatForm = ref({ seat_name: '', alias: '' })
const telegramForm = ref({ enabled: false, bot_token: '', chat_id: '' })
const telegramMasked = ref(false)
const wechatbotForm = ref({ enabled: false, webhook_url: '', token: '', claw_base_url: 'https://ilinkai.weixin.qq.com', chat_id: '' })
const wechatbotMasked = ref(false)
const savingTelegram = ref(false)
const savingWeChatBot = ref(false)
const testingPush = ref(false)
const testingNotify = ref(false)
const settingsMessage = ref('')
const pushResults = ref([])

const settingsRows = computed(() => [
  ['端口', settings.value.server?.port ?? '-'],
  ['交易所', (settings.value.exchanges?.enabled || []).map(exchangeName).join('、')],
  ['定时任务', settings.value.scheduler?.daily_report_cron || '-'],
  ['通知 Telegram', settings.value.notify?.telegram?.enabled ? '启用' : '关闭'],
  ['通知 WeChatBot', settings.value.notify?.wechatbot?.enabled ? '启用' : '关闭'],
  ['智能助手', settings.value.assistant?.enabled ? '启用' : '预留/关闭'],
])

async function load() {
  settings.value = (await api.get('/settings')).data
  const tg = settings.value.notify?.telegram || {}
  telegramMasked.value = tg.bot_token === '***'
  telegramForm.value = { enabled: !!tg.enabled, bot_token: tg.bot_token || '', chat_id: tg.chat_id || '' }
  const wb = settings.value.notify?.wechatbot || {}
  wechatbotMasked.value = wb.token === '***'
  wechatbotForm.value = { enabled: !!wb.enabled, webhook_url: wb.webhook_url || '', token: wb.token || '', claw_base_url: wb.claw_base_url || 'https://ilinkai.weixin.qq.com', chat_id: wb.chat_id || wb.claw_target || '' }
  symbols.value = (await api.get('/watch/symbols')).data
  seats.value = (await api.get('/watch/seats')).data
}

async function addSymbol() {
  if (!symbolForm.value.symbol.trim()) return
  await api.post('/watch/symbols', symbolForm.value)
  symbolForm.value = { symbol: '', exchange: '', name: '' }
  watchMessage.value = '自选品种已添加'
  await load()
}

async function bulkImportSymbols() {
  if (!bulkSymbols.value.trim()) return
  bulkImporting.value = true
  watchMessage.value = ''
  try {
    const { data } = await api.post('/watch/symbols/bulk', { text: bulkSymbols.value, replace: bulkReplace.value })
    watchMessage.value = `已导入 ${data.count || 0} 个自选品种`
    bulkSymbols.value = ''
    await load()
  } catch (err) {
    watchMessage.value = '批量导入失败，请检查品种/合约格式'
  } finally {
    bulkImporting.value = false
  }
}

async function addSeat() {
  if (!seatForm.value.seat_name.trim()) return
  await api.post('/watch/seats', seatForm.value)
  seatForm.value = { seat_name: '', alias: '' }
  await load()
}

async function saveTelegram() {
  savingTelegram.value = true
  settingsMessage.value = ''
  try {
    const payload = { ...telegramForm.value }
    if (telegramMasked.value && payload.bot_token === '***') delete payload.bot_token
    const { data } = await api.patch('/settings/notify/telegram', payload)
    telegramMasked.value = data.bot_token === '***'
    telegramForm.value = { enabled: !!data.enabled, bot_token: data.bot_token || '', chat_id: data.chat_id || '' }
    settingsMessage.value = 'Telegram 配置已保存'
    await load()
  } catch (err) {
    settingsMessage.value = '保存失败，请检查配置文件权限'
  } finally {
    savingTelegram.value = false
  }
}

async function saveWeChatBot() {
  savingWeChatBot.value = true
  settingsMessage.value = ''
  try {
    const payload = { ...wechatbotForm.value, claw_target: wechatbotForm.value.chat_id }
    if (wechatbotMasked.value && payload.token === '***') delete payload.token
    const { data } = await api.patch('/settings/notify/wechatbot', payload)
    wechatbotMasked.value = data.token === '***'
    wechatbotForm.value = { enabled: !!data.enabled, webhook_url: data.webhook_url || '', token: data.token || '', claw_base_url: data.claw_base_url || 'https://ilinkai.weixin.qq.com', chat_id: data.chat_id || data.claw_target || '' }
    settingsMessage.value = 'WeChatBot 配置已保存'
    await load()
  } catch (err) {
    settingsMessage.value = '保存失败，请检查配置文件权限'
  } finally {
    savingWeChatBot.value = false
  }
}

async function testNotify() {
  testingNotify.value = true
  settingsMessage.value = ''
  pushResults.value = []
  try {
    const { data } = await api.post('/settings/notify/test')
    pushResults.value = data?.dispatch || []
    const failed = pushResults.value.filter(x => x.ok === false)
    const sent = pushResults.value.filter(x => x.ok === true)
    const skipped = pushResults.value.filter(x => x.skipped)
    settingsMessage.value = failed.length
      ? `通知测试部分失败：${failed.map(x => channelLabel(x.channel)).join('、')}`
      : sent.length
        ? `通知测试完成：成功 ${sent.length}，跳过 ${skipped.length}`
        : '测试已执行，但还没有启用任何通知方式'
  } catch (err) {
    settingsMessage.value = '通知测试失败，请检查通知配置或服务日志'
  } finally {
    testingNotify.value = false
  }
}

async function testPushLatest() {
  testingPush.value = true
  settingsMessage.value = ''
  pushResults.value = []
  try {
    const { data } = await api.post('/reports/latest/push')
    pushResults.value = data?.dispatch || []
    const failed = pushResults.value.filter(x => x.ok === false)
    const sent = pushResults.value.filter(x => x.ok === true)
    const skipped = pushResults.value.filter(x => x.skipped)
    settingsMessage.value = failed.length
      ? `测试推送部分失败：${failed.map(x => channelLabel(x.channel)).join('、')}`
      : sent.length
        ? `测试推送完成：成功 ${sent.length}，跳过 ${skipped.length}`
        : '测试推送已执行，但还没有启用任何通知方式'
  } catch (err) {
    settingsMessage.value = '测试推送失败，请先生成日报并检查通知配置'
  } finally {
    testingPush.value = false
  }
}

function channelLabel(channel) {
  return ({ telegram: 'Telegram', wecom: '企业微信', wechatbot: 'WeChatBot' })[channel] || channel || '-'
}

function pushResultStatus(item) {
  if (item.ok === true) return '成功'
  if (item.ok === false) return '失败'
  if (item.skipped) return '跳过'
  return '未知'
}

function pushResultTone(item) {
  if (item.ok === true) return 'ok'
  if (item.ok === false) return 'fail'
  if (item.skipped) return 'skip'
  return ''
}

function pushResultDetail(item) {
  if (item.reason) return item.reason
  if (item.error) return item.error
  if (item.status_code) return `HTTP ${item.status_code}`
  if (typeof item.body === 'string') return item.body.slice(0, 120)
  const response = item.response
  if (response?.errmsg) return response.errmsg
  if (response?.message) return response.message
  if (response?.error) return String(response.error)
  return ''
}

async function deleteSymbol(id) { await api.delete(`/watch/symbols/${id}`); await load() }
async function deleteSeat(id) { await api.delete(`/watch/seats/${id}`); await load() }

onMounted(load)
</script>

<style scoped>
.page-title { margin-bottom: 20px; color: #1a1a2e; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
.inline-form { display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 8px; margin-bottom: 14px; }
.bulk-form { display:grid; gap:10px; margin-bottom:14px; padding:12px; border:1px solid #e2e8f0; border-radius:12px; background:#f8fafc; }
.bulk-form textarea { min-height:82px; resize:vertical; border:1px solid #ddd; border-radius:8px; padding:9px 10px; font-family:inherit; }
.inline-form input, .notify-form input { border: 1px solid #ddd; border-radius: 8px; padding: 9px 10px; }
.inline-form button, .notify-form button, .bulk-form button { background: #e94560; border: 0; color: white; border-radius: 8px; padding: 9px 14px; cursor: pointer; font-weight: 800; }
.mini-check { display:flex; align-items:center; gap:6px; color:#64748b; font-weight:800; }
.notify-form { display:grid; gap:14px; }
.notify-form h3 { margin:0; color:#1a1a2e; }
.notify-subform { margin-top:18px; border-top:1px solid #e2e8f0; padding-top:18px; }
.switch-row { display:flex; align-items:center; gap:10px; font-weight:800; color:#1a1a2e; }
.switch-row input { width:18px; height:18px; }
.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.form-grid label { display:grid; gap:6px; color:#64748b; font-weight:700; }
.form-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.notify-form button.ghost { background:#f1f5f9; color:#334155; }
.notify-form button:disabled { opacity:.65; cursor:wait; }
.form-message { color:#64748b; font-weight:700; }
.push-results { display:grid; gap:8px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:12px; }
.push-results-title { font-weight:900; color:#1a1a2e; }
.push-result { display:grid; grid-template-columns:120px 56px 1fr; gap:10px; align-items:center; padding:8px 10px; border-radius:10px; background:white; color:#334155; }
.push-result.ok { border-left:4px solid #16a34a; }
.push-result.fail { border-left:4px solid #dc2626; }
.push-result.skip { border-left:4px solid #94a3b8; }
.push-result small { color:#64748b; word-break:break-all; }
.list { display: grid; gap: 8px; }
.item { display: flex; justify-content: space-between; align-items: center; background: #fafafa; border-radius: 8px; padding: 10px 12px; }
.item span { color: #777; margin-left: 8px; }
.danger { border: 0; background: #fff1f0; color: #cf1322; border-radius: 8px; padding: 6px 10px; cursor: pointer; }
.empty { color: #999; padding: 12px; text-align: center; }
@media (max-width: 1000px) { .grid-2, .inline-form, .form-grid { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .push-result { grid-template-columns:1fr; } .form-actions { flex-direction:column; } .form-actions button { width:100%; } }
</style>
