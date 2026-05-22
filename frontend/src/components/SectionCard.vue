<template>
  <div class="section-card">
    <div v-if="title" class="section-title">
      <span>{{ title }}</span>
    </div>
    <div class="section-body">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({ title: String })
</script>

<style scoped>
.section-card { background:rgba(255,255,255,.92); border:1px solid #e8edf5; border-radius:20px; box-shadow:0 12px 30px rgba(15,23,42,.07); overflow:hidden; backdrop-filter: blur(8px); }
.section-title { padding:16px 18px; font-size:15px; font-weight:900; color:#0f172a; border-bottom:1px solid #edf2f7; display:flex; justify-content:space-between; align-items:center; }
.section-title span { display:flex; align-items:center; gap:8px; }
.section-title span::before { content:''; width:8px; height:18px; border-radius:999px; background:linear-gradient(180deg,#e94560,#3f5efb); }
.section-body { padding:18px; }
</style>
