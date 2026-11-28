<template>
  <ul>
    <li v-for="entry in report" :key="entry.symbol">
      <strong>{{ entry.symbol }}</strong>
      — {{ entry.rows_checked }} rows checked,
      <span v-if="entry.issues.length === 0" class="clean">no issues</span>
      <span v-else class="issues">{{ entry.issues.length }} issue(s)</span>
      <ul v-if="entry.issues.length > 0">
        <li v-for="(issue, i) in entry.issues" :key="i">{{ issue }}</li>
      </ul>
    </li>
  </ul>
</template>

<script setup lang="ts">
import type { QualityEntry } from "../lib/api";

defineProps<{ report: QualityEntry[] }>();
</script>

<style scoped>
.clean {
  color: #0a7d2c;
}
.issues {
  color: #b00020;
}
</style>
