import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import OrderForm from "../components/OrderForm.vue";

describe("OrderForm", () => {
  it("emits a market order with the chosen values", async () => {
    const wrapper = mount(OrderForm, { props: { symbols: ["AAPL", "MSFT"] } });
    await wrapper.find('[data-testid="symbol"]').setValue("AAPL");
    await wrapper.find('[data-testid="qty"]').setValue(10);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("submit-order")).toBeTruthy();
    expect(wrapper.emitted("submit-order")![0][0]).toEqual({
      symbol: "AAPL",
      side: "BUY",
      qty: 10,
      order_type: "MARKET",
    });
  });

  it("blocks a zero quantity with an error message", async () => {
    const wrapper = mount(OrderForm, { props: { symbols: ["AAPL"] } });
    await wrapper.find('[data-testid="symbol"]').setValue("AAPL");
    await wrapper.find('[data-testid="qty"]').setValue(0);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("submit-order")).toBeFalsy();
    expect(wrapper.find('[data-testid="error"]').text()).toContain("positive whole number");
  });

  it("requires a limit price for limit orders", async () => {
    const wrapper = mount(OrderForm, { props: { symbols: ["AAPL"] } });
    await wrapper.find('[data-testid="symbol"]').setValue("AAPL");
    await wrapper.find('[data-testid="order-type"]').setValue("LIMIT");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("submit-order")).toBeFalsy();
    expect(wrapper.find('[data-testid="error"]').text()).toContain("limit price");
  });

  it("includes the limit price once it is set", async () => {
    const wrapper = mount(OrderForm, { props: { symbols: ["AAPL"] } });
    await wrapper.find('[data-testid="symbol"]').setValue("AAPL");
    await wrapper.find('[data-testid="order-type"]').setValue("LIMIT");
    await wrapper.find('[data-testid="limit-price"]').setValue(230.5);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("submit-order")![0][0]).toEqual({
      symbol: "AAPL",
      side: "BUY",
      qty: 1,
      order_type: "LIMIT",
      limit_price: 230.5,
    });
  });
});
