import { initApi } from "./modules/api.js";
import { initBaseState } from "./modules/baseState.js";
import { initChart } from "./modules/chart.js";
import { initComputed } from "./modules/computed.js";
import { initDrawing } from "./modules/drawing.js";
import { initFontScale } from "./modules/fontScale.js";
import { initSignals } from "./modules/signals.js";
import { initTrade } from "./modules/trade.js";
import { initWebSocket } from "./modules/ws.js";

export function mountDashboard() {
  const { createApp, ref, computed, onMounted, onUnmounted, nextTick } =
    window.Vue;

  createApp({
    setup() {
      let ctx = initBaseState({ ref, computed });

      ctx = initFontScale(ctx, { ref });
      ctx = initChart(ctx);
      ctx = initApi(ctx);
      ctx = initTrade(ctx, { ref });
      ctx = initSignals(ctx);
      ctx = initComputed(ctx, { computed });
      ctx = initWebSocket(ctx);
      ctx = initDrawing(ctx, { ref });

      let realAccountTimer = null;

      onMounted(async () => {
        await nextTick();
        ctx.initChart();
        ctx.setupChartDrawing();
        await ctx.fetchState();
        await ctx.fetchRealAccount();
        await ctx.fetchTrades();
        await ctx.fetchStats();
        await ctx.fetchCumPerf();
        await ctx.fetchKbars();
        await ctx.fetchIntel();
        await ctx.fetchActivity();
        ctx.connectWS();
        realAccountTimer = setInterval(ctx.fetchRealAccount, 3000);
      });

      onUnmounted(() => {
        if (realAccountTimer) clearInterval(realAccountTimer);
      });

      return {
        state: ctx.state,
        currentPrice: ctx.currentPrice,
        prevPrice: ctx.prevPrice,
        trades: ctx.trades,
        stats: ctx.stats,
        timeframe: ctx.timeframe,
        tickCount: ctx.tickCount,
        intel: ctx.intel,
        modes: ctx.modes,
        switchMode: ctx.switchMode,
        activityLog: ctx.activityLog,
        activityLogReversed: ctx.activityLogReversed,
        showIntel: ctx.showIntel,
        showActivity: ctx.showActivity,
        tradesExpanded: ctx.tradesExpanded,
        displayTrades: ctx.displayTrades,
        cumPerf: ctx.cumPerf,
        cumPnlCurve: ctx.cumPnlCurve,
        activeInstrument: ctx.activeInstrument,
        instrumentList: ctx.instrumentList,
        getInstData: ctx.getInstData,
        switchInstrument: ctx.switchInstrument,
        activeInstData: ctx.activeInstData,
        realAccount: ctx.realAccount,
        realPositions: ctx.realPositions,
        fetchRealAccount: ctx.fetchRealAccount,
        manualOpen: ctx.manualOpen,
        manualClose: ctx.manualClose,
        closeRealPosition: ctx.closeRealPosition,
        getInstPriceClass: ctx.getInstPriceClass,
        getInstPriceChange: ctx.getInstPriceChange,
        getEstLoss: ctx.getEstLoss,
        getEstProfit: ctx.getEstProfit,
        getEstSLMult: ctx.getEstSLMult,
        getEstTPMult: ctx.getEstTPMult,
        getEstRR: ctx.getEstRR,
        realPosLivePrice: ctx.realPosLivePrice,
        realPosLivePnl: ctx.realPosLivePnl,
        realPosPriceChange: ctx.realPosPriceChange,
        riskProfiles: ctx.riskProfiles,
        getSignalLight: ctx.getSignalLight,
        getTradeAdvice: ctx.getTradeAdvice,
        getRecommended: ctx.getRecommended,
        getInstruction: ctx.getInstruction,
        getDistancePoints: ctx.getDistancePoints,
        liveTotalPnl: ctx.liveTotalPnl,
        statusClass: ctx.statusClass,
        statusText: ctx.statusText,
        signalStrength: ctx.signalStrength,
        signalBarStyle: ctx.signalBarStyle,
        circuitDotClass: ctx.circuitDotClass,
        circuitText: ctx.circuitText,
        leftScoreColor: ctx.leftScoreColor,
        leftSignalText: ctx.leftSignalText,
        activityIcon: ctx.activityIcon,
        activityMsgClass: ctx.activityMsgClass,
        formatActivityTime: ctx.formatActivityTime,
        formatPrice: ctx.formatPrice,
        formatNumber: ctx.formatNumber,
        formatTime: ctx.formatTime,
        drawingMode: ctx.drawingMode,
        drawingColor: ctx.drawingColor,
        drawingWidth: ctx.drawingWidth,
        drawnLines: ctx.drawnLines,
        selectedDrawing: ctx.selectedDrawing,
        toggleDrawing: ctx.toggleDrawing,
        undoLastLine: ctx.undoLastLine,
        clearAllLines: ctx.clearAllLines,
        removeDrawingAt: ctx.removeDrawingAt,
        promptHlinePrice: ctx.promptHlinePrice,
        engineAction: ctx.engineAction,
        setRiskProfile: ctx.setRiskProfile,
        switchTimeframe: ctx.switchTimeframe,
        deleteTrade: ctx.deleteTrade,
        editTrade: ctx.editTrade,
        refreshIntel: ctx.refreshIntel,
        uiFontScale: ctx.uiFontScale,
        increaseFont: ctx.increaseFont,
        decreaseFont: ctx.decreaseFont,
        resetFontScale: ctx.resetFontScale,
        toggleAutoTrade: ctx.toggleAutoTrade,
        autoTradeClass: ctx.autoTradeClass,
        autoTradeText: ctx.autoTradeText,
      };
    },
  }).mount("#app");
}

