import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { CheckCircle2, XCircle, Circle, BarChart3, List, Code2, ArrowLeft, Download, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import { api, type RunData, type BacktestMetrics } from "@/lib/api";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { EquityChart } from "@/components/charts/EquityChart";
import { MetricsCard } from "@/components/chat/MetricsCard";
import { Skeleton, SkeletonMetrics, SkeletonChart } from "@/components/common/Skeleton";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { MarkdownRenderer } from "@/components/common/MarkdownRenderer";

type Tab = "report" | "chart" | "trades" | "code";

function downloadCsv(filename: string, csvContent: string) {
  const blob = new Blob(["\uFEFF" + csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function escapeCsvField(value: unknown): string {
  const str = String(value ?? "");
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function buildTradesCsv(trades: Array<Record<string, string>>): string {
  if (trades.length === 0) return "";
  const keys = [...new Set(trades.flatMap(Object.keys))];
  const header = keys.map(escapeCsvField).join(",");
  const rows = trades.map(tr => keys.map(k => escapeCsvField(tr[k])).join(","));
  return [header, ...rows].join("\n");
}

function buildMetricsCsv(metrics: BacktestMetrics): string {
  const header = "metric,value";
  const rows = Object.entries(metrics).map(([k, v]) => `${escapeCsvField(k)},${escapeCsvField(v)}`);
  return [header, ...rows].join("\n");
}

export function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [run, setRun] = useState<RunData | null>(null);
  const [code, setCode] = useState<Record<string, string>>({});
  const [tab, setTab] = useState<Tab>("chart");
  const [loading, setLoading] = useState(true);

  const TABS: { id: Tab; label: string; icon: typeof BarChart3 }[] = [
    ...(run?.report_markdown ? [{ id: "report" as Tab, label: t.report, icon: FileText }] : []),
    { id: "chart", label: t.chart, icon: BarChart3 },
    { id: "trades", label: t.trades, icon: List },
    { id: "code", label: t.code, icon: Code2 },
  ];

  useEffect(() => {
    if (!runId) return;
    Promise.all([
      api.getRun(runId).catch(() => null),
      api.getRunCode(runId).catch(() => ({})),
    ]).then(([r, c]) => { setRun(r); setCode(c || {}); }).finally(() => setLoading(false));
  }, [runId]);

  useEffect(() => {
    if (!run) return;
    const hasChartData = Boolean(
      (run.price_series && Object.keys(run.price_series).length > 0) ||
      (run.equity_curve && run.equity_curve.length > 0)
    );
    const hasReport = Boolean(run.report_markdown?.trim());

    setTab((prev) => {
      if (prev === "report" && !hasReport) return "chart";
      if (prev === "chart" && hasReport && !hasChartData) return "report";
      return prev;
    });
  }, [run]);

  if (loading) {
    return (
      <div className="p-8 space-y-4">
        <Skeleton className="h-6 w-48" />
        <SkeletonMetrics />
        <SkeletonChart height={400} />
      </div>
    );
  }
  if (!run) return <div className="p-8 text-destructive">Run not found</div>;

  const ok = run.status === "success";
  const failed = run.status === "failed";

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-border p-4 space-y-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="p-1 rounded-button hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title="Go back"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          {ok ? <CheckCircle2 className="h-5 w-5 text-success" /> : failed ? <XCircle className="h-5 w-5 text-destructive" /> : <Circle className="h-5 w-5 text-muted-foreground" />}
          <h1 className="font-mono text-sm font-medium text-foreground">{runId}</h1>
          {run.elapsed_seconds && <span className="text-xs text-muted-foreground">{run.elapsed_seconds.toFixed(1)}s</span>}
        </div>
        {run.prompt && <p className="text-sm text-muted-foreground">{run.prompt}</p>}
        {run.metrics && <MetricsCard metrics={run.metrics as Record<string, number>} />}

        <div className="flex items-center gap-1">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-button text-sm transition-colors",
                tab === id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
              )}
            >
              <Icon className="h-3.5 w-3.5" /> {label}
            </button>
          ))}

          <div className="ml-auto flex gap-1">
            {run.trade_log && run.trade_log.length > 0 && (
              <button
                onClick={() => downloadCsv(`trades_${runId}.csv`, buildTradesCsv(run.trade_log!))}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-button text-xs text-muted-foreground hover:bg-muted transition-colors"
                title={t.downloadTradesCsv}
              >
                <Download className="h-3.5 w-3.5" /> {t.downloadTradesCsv}
              </button>
            )}
            {run.metrics && (
              <button
                onClick={() => downloadCsv(`metrics_${runId}.csv`, buildMetricsCsv(run.metrics!))}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-button text-xs text-muted-foreground hover:bg-muted transition-colors"
                title={t.downloadMetricsCsv}
              >
                <Download className="h-3.5 w-3.5" /> {t.downloadMetricsCsv}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <ErrorBoundary>
          {tab === "report" && <ReportTab run={run} />}
          {tab === "chart" && <ChartTab run={run} />}
          {tab === "trades" && <TradesTab run={run} />}
          {tab === "code" && <CodeTab code={code} />}
        </ErrorBoundary>
      </div>
    </div>
  );
}

function ReportTab({ run }: { run: RunData }) {
  const report = run.report_markdown?.trim();

  if (!report) {
    return <div className="p-8 text-muted-foreground text-sm">No report available for this run.</div>;
  }

  return (
    <div className="p-4">
      <div className="prose prose-sm dark:prose-invert max-w-none rounded-xl border border-border bg-card p-4 text-foreground leading-relaxed prose-table:border prose-table:border-border prose-th:bg-muted/50 prose-th:px-3 prose-th:py-1.5 prose-td:px-3 prose-td:py-1.5 prose-th:text-left prose-th:text-xs prose-th:font-medium prose-td:text-xs [&_pre]:overflow-auto [&_pre]:rounded-md [&_pre]:bg-muted [&_pre]:border [&_pre]:border-border [&_pre]:p-3 [&_code]:text-[11px] [&_pre:has(.echarts-block)]:bg-transparent [&_pre:has(.echarts-block)]:border-0 [&_pre:has(.echarts-block)]:p-0 [&_pre:has(.mermaid-block)]:bg-transparent [&_pre:has(.mermaid-block)]:border-0 [&_pre:has(.mermaid-block)]:p-0">
        <MarkdownRenderer>{report}</MarkdownRenderer>
      </div>
    </div>
  );
}

function ChartTab({ run }: { run: RunData }) {
  const { t } = useI18n();
  const entries = run.price_series ? Object.entries(run.price_series) : [];
  const hasEquity = run.equity_curve && run.equity_curve.length > 0;
  const hasReport = Boolean(run.report_markdown?.trim());

  if (entries.length === 0 && !hasEquity) {
    return (
      <div className="p-8 text-center text-muted-foreground space-y-2">
        <p className="text-sm">{hasReport ? "This run generated a narrative report instead of backtest charts." : t.noChartData}</p>
        <p className="text-xs">{hasReport ? "Open the Report tab to view the saved analysis." : t.noChartDataHint}</p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {entries.map(([sym, bars]) => (
        <div key={sym}>
          <h3 className="text-sm font-medium mb-1 text-foreground">{sym}</h3>
          <CandlestickChart data={bars} markers={run.trade_markers?.filter(m => m.code === sym)} indicators={run.indicator_series?.[sym]} height={500} />
        </div>
      ))}
      {hasEquity && (
        <div>
          <h3 className="text-sm font-medium mb-1 text-foreground">Equity & Drawdown</h3>
          <EquityChart data={run.equity_curve!} height={280} />
        </div>
      )}
    </div>
  );
}

function TradesTab({ run }: { run: RunData }) {
  const trades = run.trade_log || [];
  if (trades.length === 0) return <div className="p-8 text-muted-foreground text-sm">No trades recorded.</div>;
  return (
    <div className="p-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="py-2 pr-4">Time</th>
            <th className="py-2 pr-4">Code</th>
            <th className="py-2 pr-4">Side</th>
            <th className="py-2 pr-4">Price</th>
            <th className="py-2 pr-4">Qty</th>
            <th className="py-2">Reason</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((tr, i) => (
            <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-muted/20">
              <td className="py-2 pr-4 font-mono text-xs text-muted-foreground">{tr.time || tr.timestamp}</td>
              <td className="py-2 pr-4 text-foreground">{tr.code}</td>
              <td className={cn("py-2 pr-4 font-medium", tr.side === "BUY" ? "text-success" : "text-destructive")}>{tr.side}</td>
              <td className="py-2 pr-4 tabular-nums text-foreground">{tr.price}</td>
              <td className="py-2 pr-4 tabular-nums text-foreground">{tr.qty}</td>
              <td className="py-2 text-muted-foreground">{tr.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CodeTab({ code }: { code: Record<string, string> }) {
  const files = Object.entries(code);
  const [active, setActive] = useState(files[0]?.[0] || "");
  if (files.length === 0) return <div className="p-8 text-muted-foreground text-sm">No code files.</div>;
  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-1 p-2 border-b border-border">
        {files.map(([name]) => (
          <button key={name} onClick={() => setActive(name)} className={cn("px-3 py-1 rounded-button text-xs font-mono", active === name ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>{name}</button>
        ))}
      </div>
      <div className="flex-1 overflow-auto p-3 text-[11px] leading-relaxed bg-muted/30 [&_pre]:m-0 [&_pre]:bg-transparent [&_code]:text-[11px]">
        <MarkdownRenderer>{`\`\`\`python\n${code[active] || ""}\n\`\`\``}</MarkdownRenderer>
      </div>
    </div>
  );
}

