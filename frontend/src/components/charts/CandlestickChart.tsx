import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown } from "lucide-react";
import type { PriceBar, TradeMarker, IndicatorPoint } from "@/lib/api";
import { calcMA, calcBOLL, calcMACD, calcRSI, calcKDJ, calcEMA } from "@/lib/indicators";
import { getChartTheme } from "@/lib/chart-theme";
import { abbreviateNum } from "@/lib/formatters";
import { VChart } from "@visactor/vchart";
import { ensureRegistered } from "@/lib/vchart-register";
import { useDarkMode } from "@/hooks/useDarkMode";

ensureRegistered();

type Sub = "vol" | "macd" | "rsi" | "kdj";
type Range = "1M" | "3M" | "6M" | "1Y" | "ALL";
type Overlay = "ma5" | "ma10" | "ma20" | "ma60" | "ema12" | "ema26" | "boll";

const OVERLAY_OPTIONS: { id: Overlay; label: string; group: string }[] = [
  { id: "ma5", label: "MA5", group: "MA" },
  { id: "ma10", label: "MA10", group: "MA" },
  { id: "ma20", label: "MA20", group: "MA" },
  { id: "ma60", label: "MA60", group: "MA" },
  { id: "ema12", label: "EMA12", group: "MA" },
  { id: "ema26", label: "EMA26", group: "MA" },
  { id: "boll", label: "BOLL", group: "Channel" },
];

const RANGE_BARS: Record<Range, number> = { "1M": 22, "3M": 63, "6M": 126, "1Y": 252, ALL: Infinity };
const OVERLAY_COLORS = ["#f59e0b", "#8b5cf6", "#3b82f6", "#ec4899", "#10b981", "#f97316", "#6366f1"];

interface Props {
  data: PriceBar[];
  markers?: TradeMarker[];
  indicators?: Record<string, IndicatorPoint[]>;
  height?: number;
}

export function CandlestickChart({ data, markers, indicators, height = 500 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<VChart | null>(null);
  const [sub, setSub] = useState<Sub>("vol");
  const [range, setRange] = useState<Range>("ALL");
  const [overlays, setOverlays] = useState<Set<Overlay>>(new Set(["ma5", "ma20"]));
  const [showMenu, setShowMenu] = useState(false);
  const { dark } = useDarkMode();

  const toggleOverlay = useCallback((id: Overlay) => {
    setOverlays((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const baseData = useMemo(() => {
    const closes = data.map((d) => d.close);
    const highs = data.map((d) => d.high);
    const lows = data.map((d) => d.low);
    return { closes, highs, lows };
  }, [data]);

  const indicatorCache = useMemo(
    () => ({
      ma5: calcMA(baseData.closes, 5),
      ma10: calcMA(baseData.closes, 10),
      ma20: calcMA(baseData.closes, 20),
      ma60: calcMA(baseData.closes, 60),
      ema12: calcEMA(baseData.closes, 12),
      ema26: calcEMA(baseData.closes, 26),
      boll: calcBOLL(baseData.closes, 20, 2),
      macd: calcMACD(baseData.closes),
      rsi: calcRSI(baseData.closes),
      kdj: calcKDJ(baseData.highs, baseData.lows, baseData.closes),
    }),
    [baseData]
  );

  const extraIndicators = useMemo(() => {
    if (!indicators) return [];
    return Object.entries(indicators).map(([name, points]) => {
      const lookup = new Map(points.map((p) => [p.time, p.value]));
      return { name: name.toUpperCase(), values: data.map((d) => lookup.get(d.time) ?? null) };
    });
  }, [indicators, data]);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;
    const t = getChartTheme();

    const candleValues = data.map((d) => ({
      time: d.time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
      volume: d.volume,
      rising: d.close >= d.open,
    }));

    const maxBars = RANGE_BARS[range];
    const scrollStart = maxBars >= data.length ? 0 : Math.max(0, 1 - maxBars / data.length);

    // ── Overlay series ────────────────────────────────────────────────────────
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const overlaySeries: any[] = [];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const dataSources: any[] = [{ id: "candleData", values: candleValues }];
    const overlayMap: Record<string, { name: string; data: (number | null)[] }> = {
      ma5: { name: "MA5", data: indicatorCache.ma5 },
      ma10: { name: "MA10", data: indicatorCache.ma10 },
      ma20: { name: "MA20", data: indicatorCache.ma20 },
      ma60: { name: "MA60", data: indicatorCache.ma60 },
      ema12: { name: "EMA12", data: indicatorCache.ema12 },
      ema26: { name: "EMA26", data: indicatorCache.ema26 },
    };
    let colorIdx = 0;

    for (const [key, { data: lineData }] of Object.entries(overlayMap)) {
      if (overlays.has(key as Overlay)) {
        const dataId = `ol-${key}`;
        dataSources.push({ id: dataId, values: data.map((d, i) => ({ time: d.time, value: lineData[i] })) });
        overlaySeries.push({
          type: "line", id: `s-${key}`, regionId: "mainRegion", dataId,
          xField: "time", yField: "value",
          point: { visible: false },
          line: { style: { stroke: OVERLAY_COLORS[colorIdx], lineWidth: 1 } },
        });
        colorIdx++;
      }
    }

    if (overlays.has("boll")) {
      const boll = indicatorCache.boll;
      const bollDataId = "ol-boll";
      dataSources.push({
        id: bollDataId,
        values: data.map((d, i) => ({ time: d.time, upper: boll.upper[i], mid: boll.mid[i], lower: boll.lower[i] })),
      });
      for (const [fieldKey, dash] of [["upper", true], ["mid", false], ["lower", true]] as [string, boolean][]) {
        overlaySeries.push({
          type: "line", id: `s-boll-${fieldKey}`, regionId: "mainRegion", dataId: bollDataId,
          xField: "time", yField: fieldKey,
          point: { visible: false },
          line: { style: { stroke: t.bollColor, lineWidth: dash ? 0.8 : 1, lineDash: dash ? [4, 4] : undefined } },
        });
      }
    }

    for (let i = 0; i < extraIndicators.length; i++) {
      const ind = extraIndicators[i];
      const dataId = `ol-extra-${i}`;
      dataSources.push({ id: dataId, values: data.map((d, j) => ({ time: d.time, value: ind.values[j] })) });
      overlaySeries.push({
        type: "line", id: `s-extra-${i}`, regionId: "mainRegion", dataId,
        xField: "time", yField: "value",
        point: { visible: false },
        line: { style: { stroke: OVERLAY_COLORS[(colorIdx + i) % OVERLAY_COLORS.length], lineWidth: 1, lineDash: [4, 4] } },
      });
    }

    // ── Sub-panel series ──────────────────────────────────────────────────────
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const subSeries: any[] = [];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let subAxisExtra: any = {};

    if (sub === "vol") {
      dataSources.push({ id: "subData", values: data.map((d) => ({ time: d.time, value: d.volume, rising: d.close >= d.open })) });
      subSeries.push({
        type: "bar", id: "subVol", regionId: "subRegion", dataId: "subData",
        xField: "time", yField: "value",
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        bar: { style: { fill: (datum: any) => datum.rising ? t.upColor + "aa" : t.downColor + "aa" } },
      });
    } else if (sub === "macd") {
      const m = indicatorCache.macd;
      dataSources.push({ id: "subData", values: data.map((d, i) => ({ time: d.time, dif: m.dif[i], signal: m.signal[i], hist: m.histogram[i] ?? 0 })) });
      subSeries.push(
        { type: "line", id: "macdDif", regionId: "subRegion", dataId: "subData", xField: "time", yField: "dif", point: { visible: false }, line: { style: { stroke: t.infoColor, lineWidth: 1 } } },
        { type: "line", id: "macdSig", regionId: "subRegion", dataId: "subData", xField: "time", yField: "signal", point: { visible: false }, line: { style: { stroke: t.warningColor, lineWidth: 1 } } },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { type: "bar", id: "macdHist", regionId: "subRegion", dataId: "subData", xField: "time", yField: "hist", bar: { style: { fill: (datum: any) => (datum.hist ?? 0) >= 0 ? t.upColor : t.downColor } } },
      );
    } else if (sub === "rsi") {
      dataSources.push({ id: "subData", values: data.map((d, i) => ({ time: d.time, value: indicatorCache.rsi[i] })) });
      subSeries.push({ type: "line", id: "rsiLine", regionId: "subRegion", dataId: "subData", xField: "time", yField: "value", point: { visible: false }, line: { style: { stroke: t.infoColor, lineWidth: 1.5 } } });
      subAxisExtra = { min: 0, max: 100 };
    } else {
      const kdj = indicatorCache.kdj;
      dataSources.push({ id: "subData", values: data.map((d, i) => ({ time: d.time, k: kdj.k[i], d: kdj.d[i], j: kdj.j[i] })) });
      subSeries.push(
        { type: "line", id: "kdjK", regionId: "subRegion", dataId: "subData", xField: "time", yField: "k", point: { visible: false }, line: { style: { stroke: t.infoColor, lineWidth: 1 } } },
        { type: "line", id: "kdjD", regionId: "subRegion", dataId: "subData", xField: "time", yField: "d", point: { visible: false }, line: { style: { stroke: t.warningColor, lineWidth: 1 } } },
        { type: "line", id: "kdjJ", regionId: "subRegion", dataId: "subData", xField: "time", yField: "j", point: { visible: false }, line: { style: { stroke: "#a855f7", lineWidth: 1 } } },
      );
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const spec: any = {
      type: "common",
      background: "transparent",
      layout: {
        type: "grid", col: 1, row: 2,
        elements: [
          { modelId: "mainRegion", col: 0, row: 0 },
          { modelId: "subRegion", col: 0, row: 1 },
        ],
      },
      region: [{ id: "mainRegion", height: "65%" }, { id: "subRegion", height: "25%" }],
      data: dataSources,
      series: [
        {
          type: "candlestick", id: "kSeries", regionId: "mainRegion", dataId: "candleData",
          xField: "time", openField: "open", highField: "high", lowField: "low", closeField: "close",
          rising: { style: { fill: t.upColor, stroke: t.upColor } },
          falling: { style: { fill: t.downColor, stroke: t.downColor } },
        },
        ...overlaySeries,
        ...subSeries,
      ],
      axes: [
        { orient: "bottom", regionId: "mainRegion", label: { style: { fill: t.textColor, fontSize: 10 } }, domainLine: { style: { stroke: t.axisColor } } },
        { orient: "left", regionId: "mainRegion", label: { style: { fill: t.textColor, fontSize: 10 }, formatMethod: (v: number) => abbreviateNum(v) }, grid: { style: { stroke: t.gridColor } } },
        { orient: "bottom", regionId: "subRegion", label: { visible: false }, domainLine: { style: { stroke: t.axisColor } } },
        { orient: "left", regionId: "subRegion", label: { style: { fill: t.textColor, fontSize: 10 } }, grid: { style: { stroke: t.gridColor } }, ...subAxisExtra },
      ],
      scrollBar: [{ orient: "bottom", regionId: ["mainRegion", "subRegion"], start: scrollStart, end: 1 }],
      tooltip: { mark: { visible: false }, dimension: { visible: true } },
      animation: false,
    };

    if (chartRef.current) {
      chartRef.current.release();
      chartRef.current = null;
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const chart = new VChart(spec as any, { dom: containerRef.current });
    chart.renderSync();
    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chartRef.current?.resize(containerRef.current.clientWidth, height);
    });
    ro.observe(containerRef.current);
    return () => {
      ro.disconnect();
      chartRef.current?.release();
      chartRef.current = null;
    };
  }, [data, markers, baseData, indicatorCache, extraIndicators, sub, range, overlays, dark, height]);

  if (data.length === 0) {
    return <div className="text-muted-foreground text-sm p-4">No price data</div>;
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <div className="flex gap-0.5">
          {(["1M", "3M", "6M", "1Y", "ALL"] as const).map((r) => (
            <button key={r} onClick={() => setRange(r)} className={cn("px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors", range === r ? "bg-primary/15 text-primary font-medium" : "text-muted-foreground/50 hover:text-muted-foreground")}>{r}</button>
          ))}
        </div>
        <div className="w-px h-3 bg-border/40" />
        <div className="relative">
          <button onClick={() => setShowMenu(!showMenu)} className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors">
            Indicators ({overlays.size}) <ChevronDown className="h-3 w-3" />
          </button>
          {showMenu && (
            <div className="absolute top-full left-0 mt-1 z-50 bg-card border rounded-lg shadow-lg p-2 min-w-[160px]" onMouseLeave={() => setShowMenu(false)}>
              {["MA", "Channel"].map((group) => (
                <div key={group}>
                  <p className="text-[9px] text-muted-foreground/50 uppercase tracking-wider px-1 pt-1">{group}</p>
                  {OVERLAY_OPTIONS.filter((o) => o.group === group).map((o) => (
                    <label key={o.id} className="flex items-center gap-2 px-1 py-0.5 rounded hover:bg-muted/30 cursor-pointer">
                      <input type="checkbox" checked={overlays.has(o.id)} onChange={() => toggleOverlay(o.id)} className="h-3 w-3 rounded accent-primary" />
                      <span className="text-xs">{o.label}</span>
                    </label>
                  ))}
                </div>
              ))}
              <div className="border-t mt-1 pt-1">
                <button onClick={() => { setOverlays(new Set()); setShowMenu(false); }} className="text-[10px] text-muted-foreground hover:text-foreground px-1 py-0.5 w-full text-left rounded hover:bg-muted/30">Bare K (clear all)</button>
              </div>
            </div>
          )}
        </div>
        <div className="w-px h-3 bg-border/40" />
        <div className="flex gap-0.5">
          {(["vol", "macd", "rsi", "kdj"] as const).map((id) => (
            <button key={id} onClick={() => setSub(id)} className={cn("px-1.5 py-0.5 rounded text-[10px] font-mono uppercase transition-colors", sub === id ? "bg-primary/15 text-primary font-medium" : "text-muted-foreground/50 hover:text-muted-foreground")}>{id}</button>
          ))}
        </div>
      </div>
      <div ref={containerRef} style={{ height }} />
    </div>
  );
}
