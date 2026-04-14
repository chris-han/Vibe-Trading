import { useEffect, useRef, useState } from "react";
import { GitCompare, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type RunListItem, type RunData, type EquityPoint } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { VChart } from "@visactor/vchart";
import { getChartTheme } from "@/lib/chart-theme";
import { useDarkMode } from "@/hooks/useDarkMode";

interface MetricDef {
  key: string;
  label: string;
  type: "pct" | "num" | "int" | "days";
  higherIsBetter: boolean;
}

function fmt(v: unknown, type: "pct" | "num" | "int" | "days" = "num"): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "\u2014";
  if (type === "pct") return (n * 100).toFixed(2) + "%";
  if (type === "int") return n.toFixed(0);
  if (type === "days") return n.toFixed(1);
  return n.toFixed(3);
}

function diffClass(a: unknown, b: unknown, higherIsBetter: boolean): string {
  const na = Number(a), nb = Number(b);
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return "";
  const better = higherIsBetter ? nb > na : nb < na;
  const worse = higherIsBetter ? nb < na : nb > na;
  return better ? "text-success" : worse ? "text-destructive" : "";
}

function diffStr(a: unknown, b: unknown, type: "pct" | "num" | "int" | "days"): string {
  const na = Number(a), nb = Number(b);
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return "\u2014";
  const d = nb - na;
  return (d > 0 ? "+" : "") + fmt(d, type);
}

function truncatePrompt(prompt: string | undefined, maxLen = 40): string {
  if (!prompt) return "";
  const trimmed = prompt.replace(/\n/g, " ").trim();
  return trimmed.length > maxLen ? trimmed.slice(0, maxLen) + "\u2026" : trimmed;
}

function runLabel(r: RunListItem): string {
  const summary = truncatePrompt(r.prompt);
  if (summary) return summary;
  return r.run_id;
}

const METRICS: MetricDef[] = [
  { key: "total_return",           label: "Total Return",         type: "pct", higherIsBetter: true },
  { key: "annualized_return",      label: "Annualized Return",    type: "pct", higherIsBetter: true },
  { key: "sharpe",                 label: "Sharpe Ratio",         type: "num", higherIsBetter: true },
  { key: "calmar_ratio",           label: "Calmar Ratio",         type: "num", higherIsBetter: true },
  { key: "sortino_ratio",          label: "Sortino Ratio",        type: "num", higherIsBetter: true },
  { key: "max_drawdown",           label: "Max Drawdown",         type: "pct", higherIsBetter: false },
  { key: "volatility",             label: "Volatility",           type: "pct", higherIsBetter: false },
  { key: "win_rate",               label: "Win Rate",             type: "pct", higherIsBetter: true },
  { key: "profit_factor",          label: "Profit Factor",        type: "num", higherIsBetter: true },
  { key: "avg_win",                label: "Avg Win",              type: "pct", higherIsBetter: true },
  { key: "avg_loss",               label: "Avg Loss",             type: "pct", higherIsBetter: false },
  { key: "trade_count",            label: "Trades",               type: "int", higherIsBetter: true },
  { key: "max_consecutive_losses", label: "Max Consec. Losses",   type: "int", higherIsBetter: false },
  { key: "exposure_time",          label: "Exposure Time",        type: "pct", higherIsBetter: true },
  { key: "avg_holding_period",     label: "Avg Holding Period",   type: "days", higherIsBetter: false },
];

// Also accept backend aliases
const METRIC_ALIASES: Record<string, string> = {
  annual_return: "annualized_return",
  calmar: "calmar_ratio",
  sortino: "sortino_ratio",
  profit_loss_ratio: "profit_factor",
  max_consec_loss: "max_consecutive_losses",
  max_consecutive_loss: "max_consecutive_losses",
  avg_hold_days: "avg_holding_period",
  avg_holding_days: "avg_holding_period",
};

function resolveMetric(metrics: Record<string, number> | null, key: string): number | undefined {
  if (!metrics) return undefined;
  if (metrics[key] !== undefined) return metrics[key];
  // Check if any alias maps to this key
  for (const [alias, canonical] of Object.entries(METRIC_ALIASES)) {
    if (canonical === key && metrics[alias] !== undefined) return metrics[alias];
  }
  return undefined;
}

interface EquityChartOverlayProps {
  leftCurve: EquityPoint[];
  rightCurve: EquityPoint[];
  leftLabel: string;
  rightLabel: string;
}

function EquityChartOverlay({ leftCurve, rightCurve, leftLabel, rightLabel }: EquityChartOverlayProps) {
  const ref = useRef<HTMLDivElement>(null);
  const { dark } = useDarkMode();

  useEffect(() => {
    if (!ref.current) return;
    if (leftCurve.length === 0 && rightCurve.length === 0) return;

    const t = getChartTheme();

    // Merge dates from both curves and sort
    const dateSet = new Set<string>();
    for (const p of leftCurve) dateSet.add(p.time);
    for (const p of rightCurve) dateSet.add(p.time);
    const dates = Array.from(dateSet).sort();

    // Build value arrays aligned to merged dates
    const leftMap = new Map(leftCurve.map((p) => [p.time, Number(p.equity)]));
    const rightMap = new Map(rightCurve.map((p) => [p.time, Number(p.equity)]));
    const leftValues = dates.map((d) => ({ time: d, value: leftMap.get(d) ?? null }));
    const rightValues = dates.map((d) => ({ time: d, value: rightMap.get(d) ?? null }));

    const colorA = getComputedStyle(document.documentElement).getPropertyValue("--chart-compare-a").trim() || "#3b82f6";
    const colorB = getComputedStyle(document.documentElement).getPropertyValue("--chart-compare-b").trim() || "#f59e0b";

    const spec = {
      type: "common",
      background: "transparent",
      padding: { top: 8, right: 8, bottom: 8, left: 8 },
      data: [
        { id: "leftData", values: leftValues },
        { id: "rightData", values: rightValues },
      ],
      series: [
        {
          type: "line",
          dataIndex: 0,
          xField: "time",
          yField: "value",
          name: leftLabel,
          line: { style: { stroke: colorA, lineWidth: 2 } },
          point: { visible: false },
        },
        {
          type: "line",
          dataIndex: 1,
          xField: "time",
          yField: "value",
          name: rightLabel,
          line: { style: { stroke: colorB, lineWidth: 2 } },
          point: { visible: false },
        },
      ],
      axes: [
        {
          orient: "bottom",
          type: "band",
          label: { style: { fill: t.textColor, fontSize: 10 } },
          domainLine: { style: { stroke: t.axisColor } },
          tick: { visible: false },
          sampling: true,
        },
        {
          orient: "left",
          type: "linear",
          label: { style: { fill: t.textColor, fontSize: 10 } },
          grid: { style: { stroke: t.gridColor } },
        },
      ],
      legends: [
        {
          visible: true,
          position: "top",
          orient: "horizontal",
          item: { label: { style: { fill: t.textColor, fontSize: 11 } } },
        },
      ],
      tooltip: {
        mark: { visible: true },
        dimension: { visible: true },
        style: {
          panel: { padding: 8, background: { fill: t.tooltipBg } },
          titleLabel: { fill: t.tooltipText },
          keyLabel: { fill: t.tooltipText },
          valueLabel: { fill: t.tooltipText },
        },
      },
      scrollBar: [
        {
          orient: "bottom",
          start: 0,
          end: 1,
          roamZoom: { enable: true },
        },
      ],
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const chart = new VChart(spec as any, { dom: ref.current });
    chart.renderSync();

    const ro = new ResizeObserver(() => {
      if (ref.current) chart.resize(ref.current.clientWidth, ref.current.clientHeight);
    });
    ro.observe(ref.current);
    return () => { ro.disconnect(); chart.release(); };
  }, [leftCurve, rightCurve, leftLabel, rightLabel, dark]);

  if (leftCurve.length === 0 && rightCurve.length === 0) return null;

  return <div ref={ref} style={{ height: 320 }} />;
}

export function Compare() {
  const { t } = useI18n();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [leftData, setLeftData] = useState<Record<string, number> | null>(null);
  const [rightData, setRightData] = useState<Record<string, number> | null>(null);
  const [leftCurve, setLeftCurve] = useState<EquityPoint[]>([]);
  const [rightCurve, setRightCurve] = useState<EquityPoint[]>([]);

  useEffect(() => {
    api.listRuns().then((items) => {
      setRuns(Array.isArray(items) ? items : []);
      if (items.length >= 2) { setLeftId(items[1].run_id); setRightId(items[0].run_id); }
      else if (items.length === 1) { setLeftId(items[0].run_id); }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (leftId) {
      api.getRun(leftId).then((d: RunData) => {
        setLeftData(d.metrics || null);
        setLeftCurve(d.equity_curve || []);
      }).catch(() => { setLeftData(null); setLeftCurve([]); });
    } else {
      setLeftData(null);
      setLeftCurve([]);
    }
  }, [leftId]);

  useEffect(() => {
    if (rightId) {
      api.getRun(rightId).then((d: RunData) => {
        setRightData(d.metrics || null);
        setRightCurve(d.equity_curve || []);
      }).catch(() => { setRightData(null); setRightCurve([]); });
    } else {
      setRightData(null);
      setRightCurve([]);
    }
  }, [rightId]);

  const leftRun = runs.find((r) => r.run_id === leftId);
  const rightRun = runs.find((r) => r.run_id === rightId);

  return (
    <div className="p-8 max-w-4xl space-y-6">
      <h1 className="text-xl font-bold flex items-center gap-2 text-foreground">
        <GitCompare className="h-5 w-5 text-primary" /> {t.strategyComparison}
      </h1>

      {/* Selectors */}
      <div className="flex gap-4 items-end">
        <div className="flex-1">
          <label className="text-xs text-muted-foreground block mb-1">{t.baseline}</label>
          <select value={leftId} onChange={(e) => setLeftId(e.target.value)} className="w-full px-3 py-2 rounded-button border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 text-foreground" title={leftRun?.prompt || leftId}>
            <option value="">{t.selectRun}</option>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{runLabel(r)} ({r.status})</option>)}
          </select>
        </div>
        <ArrowRight className="h-5 w-5 text-muted-foreground mb-2 shrink-0" />
        <div className="flex-1">
          <label className="text-xs text-muted-foreground block mb-1">{t.compareTo}</label>
          <select value={rightId} onChange={(e) => setRightId(e.target.value)} className="w-full px-3 py-2 rounded-button border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 text-foreground" title={rightRun?.prompt || rightId}>
            <option value="">{t.selectRun}</option>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{runLabel(r)} ({r.status})</option>)}
          </select>
        </div>
      </div>

      {/* Equity curve overlay */}
      {(leftCurve.length > 0 || rightCurve.length > 0) && (
        <div className="border border-border rounded-card p-4 bg-card">
          <h2 className="text-sm font-medium text-muted-foreground mb-2">{t.equityDrawdown}</h2>
          <EquityChartOverlay
            leftCurve={leftCurve}
            rightCurve={rightCurve}
            leftLabel={leftRun ? truncatePrompt(leftRun.prompt, 20) || t.baseline : t.baseline}
            rightLabel={rightRun ? truncatePrompt(rightRun.prompt, 20) || t.compareTo : t.compareTo}
          />
        </div>
      )}

      {/* Metrics table */}
      {(leftData || rightData) && (
        <div className="border border-border rounded-card overflow-hidden bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-4 py-2.5 text-muted-foreground font-medium">{t.metric}</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">{t.baseline}</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">{t.compareTo}</th>
                <th className="text-right px-4 py-2.5 text-muted-foreground font-medium">{t.delta}</th>
              </tr>
            </thead>
            <tbody>
              {METRICS.map(({ key, label, type, higherIsBetter }) => {
                const lv = resolveMetric(leftData, key);
                const rv = resolveMetric(rightData, key);
                return (
                  <tr key={key} className="border-b border-border/50 last:border-0 hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-medium text-foreground">{label}</td>
                    <td className="px-4 py-2.5 text-right font-mono tabular-nums text-muted-foreground">{fmt(lv, type)}</td>
                    <td className="px-4 py-2.5 text-right font-mono tabular-nums text-muted-foreground">{fmt(rv, type)}</td>
                    <td className={cn("px-4 py-2.5 text-right font-mono tabular-nums font-semibold", diffClass(lv, rv, higherIsBetter))}>{diffStr(lv, rv, type)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!leftData && !rightData && (
        <div className="text-center py-16 text-muted-foreground">
          <GitCompare className="h-12 w-12 mx-auto mb-3 opacity-20" />
          <p className="text-sm">{t.selectTwoRuns}</p>
        </div>
      )}
    </div>
  );
}
