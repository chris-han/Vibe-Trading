import { createContext, useContext, type ReactNode, useMemo, useState, useCallback } from "react";

const messagesEn = {
  home: "Home", agent: "Agent", runs: "Runs", settings: "Settings",
  startResearch: "Start Research", describeStrategy: "Describe a trading strategy to get started.",
  prompt: "e.g. Create a dual MA crossover strategy for 000001.SZ, backtest 2024",
  send: "Send", loading: "Loading...", noRuns: "No runs yet. Go to Agent to create one.",
  runHistory: "Run History", status: "Status", elapsed: "Elapsed",
  chart: "Chart", report: "Report", trades: "Trades", code: "Code", trace: "Trace",
  noData: "No data available", noTrades: "No trades recorded.", noCode: "No code files.",
  noTrace: "No trace data.", priceAndTrades: "Price & Trades", equityAndDrawdown: "Equity & Drawdown",
  examples: "Try an example:", bye: "Goodbye",
  heroTitle: "AI-Powered Quant Strategy Research",
  heroDesc: "Describe a trading strategy in natural language. The agent generates code, runs backtests, and optimizes — all in real time.",
  feat1: "AI Agent", feat1d: "Natural language strategy generation with ReAct reasoning",
  feat2: "Built-in Backtest", feat2d: "3 data sources: A-shares, US/HK, Crypto",
  feat3: "Real-time Streaming", feat3d: "Watch the agent think, call tools, and iterate",
  score: "Score", passed: "Passed", failed: "Failed", findings: "Findings", recommendations: "Recommendations",
  darkMode: "Dark", lightMode: "Light", language: "Language",
  sessions: "Sessions", newChat: "New Chat", deleteConfirm: "Delete?",
  noSessions: "No sessions yet",
  viewDetails: "View Details",
  fullReport: "Full Report →",
  strategyComparison: "Strategy Comparison",
  baseline: "Baseline", compareTo: "Compare", delta: "Delta", metric: "Metric",
  selectRun: "-- Select --",
  selectTwoRuns: "Select two runs to compare their metrics.",
  online: "Online", offline: "Offline",
  checking: "Checking…", checkConnection: "Check Connection",
  appearance: "Appearance",
  connection: "Connection",
  endpoints: "Endpoints",
  review: "Review",
  noReview: "No review data available.",
  colTime: "Time", colCode: "Code", colSide: "Side",
  colPrice: "Price", colQty: "Qty", colReason: "Reason",
  equityDrawdown: "Equity & Drawdown",
  noPriceData: "No price data", noEquityData: "No equity data",
  filterLogs: "Filter logs...",
  confirmDelete: "Confirm", cancelDelete: "Cancel",
  reconnectingN: "Connection lost, reconnecting (attempt {n})…",
  disconnected: "Connection lost",
  sessionCreated: "Session started",
  sendFailed: "Failed to send message, please retry.",
  reconnecting: "Connection lost, reconnecting…",
  connected: "Connection restored",
  toolLoadSkill: "Load strategy knowledge",
  toolWriteFile: "Generate code",
  toolEditFile: "Edit code",
  toolReadFile: "Read file",
  toolRunBacktest: "Run backtest",
  toolBash: "Run command",
  toolReadUrl: "Read webpage",
  toolReadDocument: "Read document",
  toolCompact: "Compact context",
  toolCreateTask: "Create task",
  toolUpdateTask: "Update task",
  toolSpawnSubagent: "Spawn sub-agent",
  toolProcessing: "Processing",
  toolRunning: "Running",
  thinkingRunning: "Running {tool}...",
  thinkingDone: "Done · {count} steps",
  metricTotalReturn: "Total Return",
  metricAnnualReturn: "Annual",
  metricSharpe: "Sharpe",
  metricMaxDrawdown: "Max DD",
  metricWinRate: "Win Rate",
  metricTradeCount: "Trades",
  metricFinalValue: "Final Value",
  metricCalmar: "Calmar",
  metricSortino: "Sortino",
  metricProfitLossRatio: "P/L Ratio",
  metricMaxConsecutiveLoss: "Max Consec. Loss",
  metricAvgHoldingDays: "Avg Hold Days",
  metricBenchmarkReturn: "Benchmark",
  metricExcessReturn: "Excess Return",
  metricIR: "IR",
  overlayMA: "Moving Avg",
  overlayChannel: "Channel",
  overlayIndicators: "Indicators",
  overlayClearAll: "Bare K (clear all)",
  rename: "Rename",
  goBack: "Go back",
  noChartData: "No chart data available",
  noChartDataHint: "The backtest engine may not have generated price data. Check the artifacts/ directory.",
  executionFailed: "Execution failed",
  executionTimeout: "Execution timed out, automatically stopped",
  cancelSent: "Cancel request sent",
  cancelFailed: "Cancel failed",
  exportChat: "Export chat",
  stopGeneration: "Stop generation",
  newMessages: "New messages",
  loadMoreHistory: "Load more history",
  loadingMoreHistory: "Loading more history...",
  stepN: "Step {n}",
  exportTitle: "# Chat Export",
  exportTime: "Export time",
  exportUser: "## User",
  exportAssistant: "## Assistant",
  exportError: "## Error",
  exportToolCall: "> Tool call",
  exportRunComplete: "> Backtest complete",
  downloadTradesCsv: "Download Trades CSV",
  downloadMetricsCsv: "Download Metrics CSV",
  example1: "Dual MA crossover on 000001.SZ (5/20 day), backtest 2024",
  example2: "Build a dual MA crossover strategy for 000001.SZ, backtest 2024",
  example3: "Bollinger band mean-reversion on 600519.SH, backtest last 3 years",
};

const messagesZh: Partial<Record<keyof typeof messagesEn, string>> = {
  home: "首页", agent: "代理", runs: "运行", settings: "设置",
  startResearch: "开始研究", describeStrategy: "用自然语言描述交易策略以开始。",
  send: "发送", loading: "加载中...", noRuns: "尚无运行。请到代理页面创建。",
  runHistory: "运行历史", chart: "图表", report: "报告", trades: "交易", code: "代码",
  heroTitle: "AI 驱动的量化策略研究",
  heroDesc: "用自然语言描述交易策略。代理会生成代码、运行回测并优化 —— 实时反馈。",
  darkMode: "暗色", lightMode: "亮色", language: "语言",
  sessions: "会话", newChat: "新会话", deleteConfirm: "删除？",
  fullReport: "完整报告 →",
  noSessions: "暂无会话",
  viewDetails: "查看详情",
  confirmDelete: "确认", cancelDelete: "取消",
  loadMoreHistory: "加载更多历史消息",
  loadingMoreHistory: "正在加载更多历史消息...",
};

type Messages = typeof messagesEn;

type Lang = "en" | "zh";

const I18nCtx = createContext<{ t: Messages; lang: Lang; setLang: (l: Lang) => void; detectAndSetLangFromContent: (text: string) => void }>({ t: messagesEn, lang: "en", setLang: () => {}, detectAndSetLangFromContent: () => {} });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    try {
      const stored = localStorage.getItem("app.lang");
      if (stored === "zh") return "zh";
    } catch {}
    return navigator.language?.startsWith("zh") ? "zh" : "en";
  });

  const setLangAndStore = useCallback((l: Lang) => {
    try { localStorage.setItem("app.lang", l); } catch {}
    setLang(l);
    // set html lang attribute for CSS selectors
    try {
      document.documentElement.lang = l === "zh" ? "zh" : "en";
      // Update CSS font variable so English uses Autaut Grotesk, Chinese uses Noto Sans SC
      if (l === "zh") {
        document.documentElement.style.setProperty("--font-ui", "'Noto Sans SC', 'Autaut Grotesk', -apple-system, system-ui, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif");
      } else {
        document.documentElement.style.setProperty("--font-ui", "'Autaut Grotesk', 'Noto Sans SC', -apple-system, system-ui, 'Segoe UI', Roboto, Arial, sans-serif");
      }
    } catch {}
  }, []);

  const detectAndSetLangFromContent = useCallback((text: string) => {
    const cjk = /[\u4E00-\u9FFF\u3400-\u4DBF\u3000-\u303F]/;
    if (cjk.test(text)) setLangAndStore("zh");
  }, [setLangAndStore]);

  const t = useMemo(() => {
    if (lang === "zh") return { ...(messagesEn as any), ...(messagesZh as any) } as Messages;
    return messagesEn as Messages;
  }, [lang]);

  // Ensure CSS font variable matches initial lang on mount
  try {
    if (lang === "zh") {
      document.documentElement.style.setProperty("--font-ui", "'Noto Sans SC', 'Autaut Grotesk', -apple-system, system-ui, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif");
    } else {
      document.documentElement.style.setProperty("--font-ui", "'Autaut Grotesk', 'Noto Sans SC', -apple-system, system-ui, 'Segoe UI', Roboto, Arial, sans-serif");
    }
  } catch {}

  return (
    <I18nCtx.Provider value={{ t, lang, setLang: setLangAndStore, detectAndSetLangFromContent }}>
      {children}
    </I18nCtx.Provider>
  );
}

export function useI18n() { return useContext(I18nCtx); }
