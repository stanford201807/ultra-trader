export function initBaseState(vue) {
  const { ref, computed } = vue;

  const state = ref({
    engine_state: "stopped",
    trading_mode: "simulation",
    risk_profile: "balanced",
    contract: "",
    price: 0,
    position: {},
    daily_pnl: 0,
    daily_trades: 0,
    auto_trade: false,
    strategy: {},
    risk: {},
    snapshot: {},
  });

  const currentPrice = ref(0);
  const prevPrice = ref(0);
  const trades = ref([]);
  const stats = ref({});
  const timeframe = ref(1);
  const tickCount = ref(0);
  const intel = ref({});
  const activityLog = ref([]);

  const showIntel = ref(false);
  const showActivity = ref(false);

  const tradesExpanded = ref(false);
  const cumPerf = ref({});

  const drawingMode = ref(null); // null | 'trendline' | 'hline'
  const drawingColor = ref("#FACC15");
  const drawingWidth = ref(2);
  const drawnLines = ref([]);
  const drawingState = { startPoint: null, tempLine: null };

  const activeInstrument = ref("");
  const instrumentList = computed(() => state.value.instruments || []);

  const realAccount = ref({
    equity: 0,
    balance: 0,
    margin_used: 0,
    margin_available: 0,
    unrealized_pnl: 0,
  });
  const realPositions = ref([]);

  async function fetchRealAccount() {
    try {
      const r = await fetch("/api/real-account");
      const data = await r.json();
      if (data.account) realAccount.value = data.account;
      if (data.positions) realPositions.value = data.positions;
    } catch {
      // ignore
    }
  }

  function getInstData(inst) {
    return (
      state.value.instruments_data?.[inst] || {
        price: 0,
        position: { side: "flat" },
        snapshot: {},
        strategy: {},
      }
    );
  }

  const modes = [
    {
      key: "simulation",
      icon: "🔬",
      label: "模擬",
      activeStyle:
        "background: rgba(107,114,128,0.2); color: #9CA3AF; border-color: #6B7280;",
    },
    {
      key: "paper",
      icon: "👁",
      label: "觀盤",
      activeStyle:
        "background: rgba(59,130,246,0.2); color: #60A5FA; border-color: #3B82F6;",
    },
    {
      key: "live",
      icon: "💰",
      label: "實單",
      activeStyle:
        "background: rgba(239,68,68,0.25); color: #F87171; border-color: #EF4444;",
    },
  ];

  const riskProfiles = [
    { key: "conservative", icon: "🛡", label: "保守" },
    { key: "balanced", icon: "⚖", label: "平衡" },
    { key: "aggressive", icon: "🔥", label: "積極" },
    { key: "crisis", icon: "⚔", label: "危機" },
  ];

  return {
    state,
    currentPrice,
    prevPrice,
    trades,
    stats,
    timeframe,
    tickCount,
    intel,
    activityLog,
    showIntel,
    showActivity,
    tradesExpanded,
    cumPerf,
    drawingMode,
    drawingColor,
    drawingWidth,
    drawnLines,
    drawingState,
    activeInstrument,
    instrumentList,
    realAccount,
    realPositions,
    fetchRealAccount,
    getInstData,
    modes,
    riskProfiles,
    // placeholders (其他模組會覆寫/補齊)
    redrawAllDrawings: () => {},
  };
}
