import { useEffect, useRef, useState } from "react";
import { echarts } from "@/lib/echarts";

function cloneObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? { ...(value as Record<string, unknown>) }
    : {};
}

function withTitleLegendSpacing(option: Record<string, unknown>): Record<string, unknown> {
  const next = { ...option };
  const title = cloneObject(next.title);
  const legend = cloneObject(next.legend);
  const hasTitle = Object.keys(title).length > 0 && typeof title.text === "string" && title.text.trim().length > 0;
  const hasLegend = Object.keys(legend).length > 0;

  if (!hasTitle && !hasLegend) return next;

  if (hasTitle) {
    title.top = typeof title.top === "number" ? Math.max(title.top, 8) : 8;
    title.padding = Array.isArray(title.padding) ? title.padding : [8, 10, 18, 10];
    next.title = title;
  }

  if (hasLegend) {
    legend.top = typeof legend.top === "number"
      ? Math.max(legend.top, hasTitle ? 44 : 12)
      : hasTitle ? 44 : 12;
    legend.left = legend.left ?? "center";
    legend.itemGap = typeof legend.itemGap === "number" ? Math.max(legend.itemGap, 12) : 12;
    legend.padding = Array.isArray(legend.padding) ? legend.padding : [8, 12, 8, 12];
    next.legend = legend;
  }

  const grid = cloneObject(next.grid);
  if (Object.keys(grid).length > 0) {
    grid.top = typeof grid.top === "number"
      ? Math.max(grid.top, hasTitle && hasLegend ? 96 : hasTitle || hasLegend ? 72 : grid.top)
      : hasTitle && hasLegend ? 96 : hasTitle || hasLegend ? 72 : grid.top;
    next.grid = grid;
  }

  return next;
}

function sanitizeOption(input: Record<string, unknown>): Record<string, unknown> {
  const option = { ...input };
  if (typeof option.title === "string") {
    option.title = { text: option.title };
  }
  return withTitleLegendSpacing(option);
}

export function EChartsBlock({ config }: { config: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    let parsed: Record<string, unknown>;
    try {
      parsed = sanitizeOption(JSON.parse(config));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid ECharts JSON");
      return;
    }

    const chart = echarts.init(ref.current);
    try {
      chart.setOption(parsed, true);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to render chart");
      chart.dispose();
      return;
    }

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [config]);

  if (error) {
    return (
      <div className="my-4 overflow-hidden rounded-card border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }

  return <div ref={ref} className="my-4 h-[360px] w-full overflow-hidden rounded-card border border-border bg-card" />;
}
