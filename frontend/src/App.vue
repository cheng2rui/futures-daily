<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">FD</div>
        <div>
          <div class="brand-title">Futures Daily</div>
          <div class="brand-sub">全市场期货日报</div>
        </div>
      </div>
      <nav class="nav-links">
        <router-link to="/">今日看板</router-link>
        <router-link to="/history">历史复盘</router-link>
        <router-link to="/seats">席位动向</router-link>
        <router-link to="/dataset">数据完整度</router-link>
        <router-link to="/diagnostics">数据诊断</router-link>
        <router-link to="/events">事件日历</router-link>
        <router-link to="/jobs">运行记录</router-link>
        <router-link to="/settings">设置</router-link>
      </nav>
      <div class="side-foot">
        <span class="status-dot"></span>
        <span>Local · Docker · v{{ appVersion }}</span>
      </div>
    </aside>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api from './api.js'

const appVersion = ref('0.5.26')
onMounted(async () => {
  try {
    const { data } = await api.get('/health')
    appVersion.value = data?.version || appVersion.value
  } catch {}
})
</script>

<style scoped>
.app-shell { display:flex; min-height:100vh; background:#eef2f7; }
.sidebar { width:236px; color:#e5edff; padding:22px 16px; display:flex; flex-direction:column; gap:22px; background:linear-gradient(180deg,#111827 0%,#18213a 52%,#0f172a 100%); box-shadow:12px 0 32px rgba(15,23,42,.18); position:sticky; top:0; height:100vh; }
.brand { display:flex; gap:12px; align-items:center; padding:6px 6px 18px; border-bottom:1px solid rgba(255,255,255,.08); }
.brand-mark { width:42px; height:42px; border-radius:14px; display:grid; place-items:center; font-weight:900; letter-spacing:-.04em; color:white; background:linear-gradient(135deg,#e94560,#3f5efb); box-shadow:0 14px 32px rgba(233,69,96,.28); }
.brand-title { font-weight:900; color:#fff; }
.brand-sub { margin-top:3px; color:#8ea2c8; font-size:12px; }
.nav-links { display:grid; gap:6px; }
.nav-links a { color:#aebddd; text-decoration:none; padding:12px 13px; border-radius:13px; font-weight:700; transition:all .18s ease; }
.nav-links a:hover { color:#fff; background:rgba(255,255,255,.08); transform:translateX(2px); }
.nav-links a.router-link-active { color:#fff; background:linear-gradient(135deg,rgba(233,69,96,.95),rgba(63,94,251,.78)); box-shadow:0 12px 28px rgba(63,94,251,.20); }
.side-foot { margin-top:auto; display:flex; align-items:center; gap:8px; color:#8ea2c8; font-size:12px; padding:12px 10px; border-radius:14px; background:rgba(255,255,255,.05); }
.status-dot { width:8px; height:8px; border-radius:999px; background:#16c79a; box-shadow:0 0 0 5px rgba(22,199,154,.12); }
.content { flex:1; padding:26px; overflow:auto; }
@media (max-width: 860px) {
  .app-shell { display:block; }
  .sidebar { width:auto; height:auto; position:relative; border-radius:0 0 24px 24px; }
  .nav-links { grid-template-columns:repeat(3,1fr); }
  .content { padding:16px; }
}
@media (max-width: 560px) { .nav-links { grid-template-columns:repeat(2,1fr); } }
</style>
