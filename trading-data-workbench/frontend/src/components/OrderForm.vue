<template>
  <form @submit.prevent="submit">
    <label>
      Symbol
      <select v-model="symbol" data-testid="symbol">
        <option value="" disabled>Select a symbol</option>
        <option v-for="s in symbols" :key="s" :value="s">{{ s }}</option>
      </select>
    </label>
    <label>
      Side
      <select v-model="side" data-testid="side">
        <option value="BUY">BUY</option>
        <option value="SELL">SELL</option>
      </select>
    </label>
    <label>
      Quantity
      <input v-model.number="qty" type="number" min="1" step="1" data-testid="qty" />
    </label>
    <label>
      Order type
      <select v-model="orderType" data-testid="order-type">
        <option value="MARKET">MARKET</option>
        <option value="LIMIT">LIMIT</option>
      </select>
    </label>
    <label v-if="orderType === 'LIMIT'">
      Limit price
      <input v-model.number="limitPrice" type="number" min="0" step="0.01" data-testid="limit-price" />
    </label>
    <p v-if="error" class="error" data-testid="error">{{ error }}</p>
    <button type="submit">Place order</button>
  </form>
</template>

<script setup lang="ts">
import { ref } from "vue";
import type { NewOrder } from "../lib/api";

const props = defineProps<{ symbols: string[] }>();
const emit = defineEmits<{
  (e: "submit-order", order: NewOrder): void;
}>();

const symbol = ref("");
const side = ref<"BUY" | "SELL">("BUY");
const qty = ref(1);
const orderType = ref<"MARKET" | "LIMIT">("MARKET");
const limitPrice = ref<number | null>(null);
const error = ref("");

function submit(): void {
  error.value = "";
  if (!symbol.value) {
    error.value = "Choose a symbol first.";
    return;
  }
  if (!Number.isInteger(qty.value) || qty.value <= 0) {
    error.value = "Quantity must be a positive whole number.";
    return;
  }
  if (orderType.value === "LIMIT" && (limitPrice.value === null || limitPrice.value <= 0)) {
    error.value = "Limit orders need a positive limit price.";
    return;
  }
  const order: NewOrder = {
    symbol: symbol.value,
    side: side.value,
    qty: qty.value,
    order_type: orderType.value,
  };
  if (orderType.value === "LIMIT" && limitPrice.value !== null) {
    order.limit_price = limitPrice.value;
  }
  emit("submit-order", order);
}

defineExpose({ symbol });
void props;
</script>

<style scoped>
form {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: end;
}
label {
  display: flex;
  flex-direction: column;
  font-size: 0.9em;
}
.error {
  color: #b00020;
  width: 100%;
}
</style>
