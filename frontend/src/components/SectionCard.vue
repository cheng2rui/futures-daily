<template>
  <div class="section-card">
    <div v-if="title" class="section-title">{{ title }}</div>
    <div class="section-body">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({ title: String })
</script>

<style scoped>
.section-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  overflow: hidden;
}
.section-title {
  padding: 16px 20px;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
  border-bottom: 1px solid #f0f0f0;
}
.section-body {
  padding: 20px;
}
</style>
