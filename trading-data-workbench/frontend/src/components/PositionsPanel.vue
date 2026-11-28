<template>
  <div>
    <p v-if="positions.length === 0">No open positions yet. Place a buy order to open one.</p>
    <table v-else>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Qty</th>
          <th>Avg cost</th>
          <th>Last</th>
          <th>Market value</th>
          <th>Unrealised P&amp;L</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in positions" :key="p.symbol">
          <td>{{ p.symbol }}</td>
          <td>{{ p.qty }}</td>
          <td>{{ formatMoney(p.avg_cost) }}</td>
          <td>{{ formatMoney(p.last_price) }}</td>
          <td>{{ formatMoney(p.market_value) }}</td>
          <td :class="pnlClass(p.unrealized_pnl)">{{ formatSignedMoney(p.unrealized_pnl) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { Position } from "../lib/api";
import { formatMoney, formatSignedMoney, pnlClass } from "../lib/format";

defineProps<{ positions: Position[] }>();
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
.gain {
  color: #0a7d2c;
}
.loss {
  color: #b00020;
}
</style>
