<template>
  <table>
    <thead>
      <tr>
        <th>Symbol</th>
        <th>Name</th>
        <th>Class</th>
        <th>Exchange</th>
        <th>Last</th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="inst in instruments"
        :key="inst.symbol"
        :class="{ selected: inst.symbol === selectedSymbol }"
        @click="$emit('select', inst.symbol)"
      >
        <td>{{ inst.symbol }}</td>
        <td>{{ inst.name }}</td>
        <td>{{ inst.asset_class }}</td>
        <td>{{ inst.exchange }}</td>
        <td>{{ formatMoney(inst.latest_quote?.last ?? inst.base_price) }}</td>
      </tr>
    </tbody>
  </table>
</template>

<script setup lang="ts">
import type { Instrument } from "../lib/api";
import { formatMoney } from "../lib/format";

defineProps<{
  instruments: Instrument[];
  selectedSymbol: string | null;
}>();

defineEmits<{
  (e: "select", symbol: string): void;
}>();
</script>

<style scoped>
table {
  border-collapse: collapse;
  width: 100%;
}
th,
td {
  border-bottom: 1px solid #ddd;
  padding: 6px 8px;
  text-align: left;
}
tr.selected {
  background: #eef4ff;
}
tbody tr {
  cursor: pointer;
}
</style>
