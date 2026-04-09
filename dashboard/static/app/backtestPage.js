import { initBacktestPage } from "./modules/backtest.js";

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initBacktestPage);
} else {
  initBacktestPage();
}
