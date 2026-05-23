<template>
  <div class="hero">
    <div>
      <div class="eyebrow">Futures Daily · {{ displayDate }}</div>
      <h1>{{ report.overview?.stage || (viewingDate ? '历史期货日报' : '今日期货日报') }}</h1>
      <p>{{ report.overview?.summary || '暂无日报数据。点击右上角生成日报，系统会获取行情、席位和资讯，整理出今天的市场概览。' }}</p>
    </div>
    <div class="actions">
      <router-link v-if="viewingDate" to="/" class="secondary">查看最新</router-link>
      <button class="secondary" :disabled="!pushText || loading" @click="$emit('copy-push-digest')">{{ copyButtonText }}</button>
      <button class="secondary" :disabled="!report.date || pushing" @click="$emit('push-report')">{{ pushButtonText }}</button>
      <button class="primary" :disabled="loading" @click="$emit('generate')">{{ generateButtonText }}</button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  report: { type: Object, required: true },
  displayDate: { type: String, required: true },
  viewingDate: { type: String, default: '' },
  pushText: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  pushing: { type: Boolean, default: false },
  copyButtonText: { type: String, required: true },
  pushButtonText: { type: String, required: true },
  generateButtonText: { type: String, required: true },
})

defineEmits(['copy-push-digest', 'push-report', 'generate'])
</script>

<style scoped>
.hero { display:flex; justify-content:space-between; gap:24px; align-items:flex-start; padding:26px; border-radius:24px; color:#fff; background:radial-gradient(circle at top left,#3f5efb 0,#1a1a2e 42%,#111827 100%); box-shadow:0 18px 48px rgba(17,24,39,.18); }
.eyebrow { color:#a8c7ff; font-size:13px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
.hero h1 { margin:8px 0 10px; font-size:32px; line-height:1.2; }
.hero p { max-width:860px; margin:0; color:#dbeafe; line-height:1.8; }
.actions { display:flex; gap:10px; align-items:center; flex-shrink:0; flex-wrap:wrap; justify-content:flex-end; }
.primary { background:#e94560; color:white; border:0; border-radius:12px; padding:11px 18px; font-weight:800; cursor:pointer; box-shadow:0 10px 28px rgba(233,69,96,.32); }
.secondary { background:rgba(255,255,255,.12); color:#fff; border:1px solid rgba(255,255,255,.28); border-radius:12px; padding:10px 16px; font-weight:800; text-decoration:none; cursor:pointer; }
.primary:disabled, .secondary:disabled { opacity:.6; cursor:wait; }
@media (max-width:760px) { .hero { flex-direction:column; align-items:stretch; } .hero h1 { font-size:26px; } }
</style>
