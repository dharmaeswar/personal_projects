<template>
  <main>
    <h1>Trading Data Workbench</h1>
    <p>Synthetic equity, ETF, and fixed-income market data with a Python API and a Vue 3 dashboard.</p>
    <p v-if="error" class="error" data-testid="load-error">{{ error }}</p>

    <section>
      <h2>Instruments</h2>
      <InstrumentTable :instruments="instruments" :selected-symbol="selectedSymbol" @select="selectSymbol" />
    </section>

    <section v-if="selectedSymbol">
      <h2>Latest quotes — {{ selectedSymbol }}</h2>
      <p v-if="latestQuote">
        Last {{ formatMoney(latestQuote.last) }} · Bid {{ formatMoney(latestQuote.bid) }} ·
        Ask {{ formatMoney(latestQuote.ask) }} · Spread {{ spreadBps(latestQuote.bid, latestQuote.ask).toFixed(1) }} bps ·
        Volume {{ latestQuote.volume }}
      </p>
    </section>

    <section>
      <h2>Place order</h2>
      <OrderForm :symbols="symbols" @submit-order="placeOrder" />
      <p v-if="orderMessage" data-testid="order-message">{{ orderMessage }}</p>
    </section>

    <section>
      <h2>Positions</h2>
      <PositionsPanel :positions="positions" />
    </section>

    <section>
      <h2>Data quality</h2>
      <DataQualityPanel :report="qualityReport" />
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, type Instrument, type NewOrder, type Position, type QualityEntry, type Quote } from "./lib/api";
import { formatMoney, spreadBps } from "./lib/format";
import DataQualityPanel from "./components/DataQualityPanel.vue";
import InstrumentTable from "./components/InstrumentTable.vue";
import OrderForm from "./components/OrderForm.vue";
import PositionsPanel from "./components/PositionsPanel.vue";

const instruments = ref<Instrument[]>([]);
const selectedSymbol = ref<string | null>(null);
const quotes = ref<Quote[]>([]);
const positions = ref<Position[]>([]);
const qualityReport = ref<QualityEntry[]>([]);
const error = ref("");
const orderMessage = ref("");

const symbols = computed(() => instruments.value.map((i) => i.symbol));
const latestQuote = computed(() => (quotes.value.length > 0 ? quotes.value[quotes.value.length - 1] : null));

async function loadAll(): Promise<void> {
  const [inst, pos, quality] = await Promise.all([
    api.listInstruments(),
    api.listPositions(),
    api.getDataQuality(),
  ]);
  instruments.value = inst.instruments;
  positions.value = pos.positions;
  qualityReport.value = quality.report;
}

async function selectSymbol(symbol: string): Promise<void> {
  selectedSymbol.value = symbol;
  const result = await api.getQuotes(symbol, 60);
  quotes.value = result.quotes;
}

async function placeOrder(order: NewOrder): Promise<void> {
  orderMessage.value = "";
  try {
    const placed = await api.placeOrder(order, `web-${Date.now()}`);
    orderMessage.value =
      placed.status === "filled"
        ? `Order #${placed.id} filled: ${placed.side} ${placed.filled_qty} ${placed.symbol} @ ${formatMoney(placed.filled_price ?? 0)}.`
        : `Order #${placed.id} is open (limit not crossed).`;
    const pos = await api.listPositions();
    positions.value = pos.positions;
  } catch (err) {
    orderMessage.value = err instanceof Error ? `Order failed: ${err.message}` : "Order failed.";
  }
}

onMounted(async () => {
  try {
    await loadAll();
  } catch (err) {
    error.value = err instanceof Error ? `Could not load market data: ${err.message}` : "Could not load market data.";
  }
});
</script>

<style scoped>
main {
  font-family: system-ui, sans-serif;
  max-width: 900px;
  margin: 0 auto;
  padding: 16px;
}
section {
  margin-top: 24px;
}
.error {
  color: #b00020;
}
</style>
