import { useEffect, useRef, useState } from "react";
import { VChart } from "@visactor/vchart";
import { getChartTheme } from "@/lib/chart-theme";
import { ensureRegistered } from "@/lib/vchart-register";
import { useDarkMode } from "@/hooks/useDarkMode";

interface Props {
  data: Array<{ time: string; equity: number | string }>;
  height?: number;
}

export function MiniEquityChart({ data, height = 80 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const { dark } = useDarkMode();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ref.current || data.length < 2) return;
    ensureRegistered();
    const t = getChartTheme();
    const values = data.map((d) => Number(d.equity));
    const positive = values[values.length - 1] >= values[0];
    const color = positive ? t.upColor : t.downColor;
    let chart: VChart | null = null;

    try {
      chart = new VChart(
        {
        type: "area",
        background: "transparent",
        padding: 0,
        data: [{ id: "equity", values: data.map((d) => ({ time: d.time, equity: Number(d.equity) })) }],
        xField: "time",
        yField: "equity",
        axes: [
          { orient: "bottom", visible: false },
          { orient: "left", visible: false, zero: false },
        ],
        line: { style: { stroke: color, lineWidth: 1.5 } },
        area: {
          style: {
            fill: {
              gradient: "linear",
              x0: 0,
              y0: 0,
              x1: 0,
              y1: 1,
              stops: [
                { offset: 0, color, opacity: 0.18 },
                { offset: 1, color, opacity: 0.02 },
              ],
            },
          },
        },
        point: { visible: false },
        crosshair: { xField: { visible: false }, yField: { visible: false } },
        tooltip: { visible: false },
        animation: false,
        },
        { dom: ref.current }
      );

      chart.renderSync();
      setError(null);
    } catch (e) {
      chart?.release();
      setError(e instanceof Error ? e.message : "Chart failed to render");
      return;
    }

    const ro = new ResizeObserver(() => {
      if (ref.current) chart.resize(ref.current.clientWidth, height);
    });
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.release();
    };
  }, [data, dark, height]);

  if (data.length < 2) return null;
  if (error) return null;
  return <div ref={ref} style={{ height }} className="rounded-lg overflow-hidden" />;
}
