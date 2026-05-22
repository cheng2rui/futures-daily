<template>
  <div class="settings">
    <h2 class="page-title">设置</h2>

    <SectionCard title="系统配置">
      <SimpleTable :columns="['项目', '值']" :data="settingsRows" />
    </SectionCard>

    <div class="grid-2">
      <SectionCard title="自选品种">
        <form class="inline-form" @submit.prevent="addSymbol">
          <input v-model="symbolForm.symbol" placeholder="品种，如 RB" />
          <input v-model="symbolForm.exchange" placeholder="交易所，可空" />
          <input v-model="symbolForm.name" placeholder="名称，可空" />
          <button>添加</button>
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
const seatForm = ref({ seat_name: '', alias: '' })

const settingsRows = computed(() => [
  ['端口', settings.value.server?.port ?? '-'],
  ['交易所', (settings.value.exchanges?.enabled || []).map(exchangeName).join('、')],
  ['定时任务', settings.value.scheduler?.daily_report_cron || '-'],
  ['通知 Telegram', settings.value.notify?.telegram?.enabled ? '启用' : '关闭'],
  ['智能助手', settings.value.assistant?.enabled ? '启用' : '预留/关闭'],
])

async function load() {
  settings.value = (await api.get('/settings')).data
  symbols.value = (await api.get('/watch/symbols')).data
  seats.value = (await api.get('/watch/seats')).data
}

async function addSymbol() {
  if (!symbolForm.value.symbol.trim()) return
  await api.post('/watch/symbols', symbolForm.value)
  symbolForm.value = { symbol: '', exchange: '', name: '' }
  await load()
}

async function addSeat() {
  if (!seatForm.value.seat_name.trim()) return
  await api.post('/watch/seats', seatForm.value)
  seatForm.value = { seat_name: '', alias: '' }
  await load()
}

async function deleteSymbol(id) { await api.delete(`/watch/symbols/${id}`); await load() }
async function deleteSeat(id) { await api.delete(`/watch/seats/${id}`); await load() }

onMounted(load)
</script>

<style scoped>
.page-title { margin-bottom: 20px; color: #1a1a2e; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
.inline-form { display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 8px; margin-bottom: 14px; }
.inline-form input { border: 1px solid #ddd; border-radius: 8px; padding: 9px 10px; }
.inline-form button { background: #e94560; border: 0; color: white; border-radius: 8px; padding: 9px 14px; cursor: pointer; }
.list { display: grid; gap: 8px; }
.item { display: flex; justify-content: space-between; align-items: center; background: #fafafa; border-radius: 8px; padding: 10px 12px; }
.item span { color: #777; margin-left: 8px; }
.danger { border: 0; background: #fff1f0; color: #cf1322; border-radius: 8px; padding: 6px 10px; cursor: pointer; }
.empty { color: #999; padding: 12px; text-align: center; }
@media (max-width: 1000px) { .grid-2, .inline-form { grid-template-columns: 1fr; } }
</style>
