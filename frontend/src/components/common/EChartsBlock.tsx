import { useEffect, useRef, useState } from "react";
import { echarts } from "@/lib/echarts";

function sanitizeOption(input: Record<string, unknown>): Record<string, unknown> {
  const option = { ...input };
  if (typeof option.title === "string") {
    option.title = { text: option.title };
  }
  return option;
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