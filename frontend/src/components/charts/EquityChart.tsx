import { useEffect, useRef } from "react";
import type { EquityPoint } from "@/lib/api";
import { getChartTheme } from "@/lib/chart-theme";
import { abbreviateNum } from "@/lib/formatters";
import { VChart } from "@visactor/vchart";
import { useDarkMode } from "@/hooks/useDarkMode";

interface Props {
  data: EquityPoint[];
  height?: number;
}

export function EquityChart({ data, height = 300 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const { dark } = useDarkMode();

  useEffect(() => {
    if (!ref.current || data.length === 0) return;
    const t = getChartTheme();

    const equityValues = data.map((d) => ({ time: d.time, value: Number(d.equity) }));
    const drawdownValues = data.map((d) => ({ time: d.time, value: Number(d.drawdown) * 100 }));
    const minDD = Math.min(...drawdownValues.map((d) => d.value));

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const chart = new VChart(
      {
        type: "common",
        background: "transparent",
        layout: {
          type: "grid",
          col: 1,
          row: 2,
          elements: [
            { modelId: "equityRegion", col: 0, row: 0 },
            { modelId: "ddRegion", col: 0, row: 1 },
          ],
        },
        region: [
          { id: "equityRegion", height: "68%" },
          { id: "ddRegion", height: "22%" },
        ],
        data: [
          { id: "equityData", values: equityValues },
          { id: "ddData", values: drawdownValues },
        ],
        series: [
          {
            type: "area",
            id: "equitySeries",
            regionId: "equityRegion",
            dataId: "equityData",
            xField: "time",
            yField: "value",
            point: { visible: false },
            line: { style: { stroke: t.infoColor, lineWidth: 2 } },
            area: {
              style: {
                fill: {
                  gradient: "linear",
                  x0: 0, y0: 0, x1: 0, y1: 1,
                  stops: [
                    { offset: 0, color: t.infoColor, opacity: 0.25 },
                    { offset: 1, color: t.infoColor, opacity: 0 },
                  ],
                },
              },
            },
          },
          {
            type: "area",
            id: "ddSeries",
            regionId: "ddRegion",
            dataId: "ddData",
            xField: "time",
            yField: "value",
            point: { visible: false },
            line: { style: { stroke: t.downColor, lineWidth: 1 } },
            area: { style: { fill: t.downColor, fillOpacity: 0.15 } },
          },
        ],
        axes: [
          {
            orient: "bottom",
            regionId: "equityRegion",
            label: { style: { fill: t.textColor, fontSize: 10 } },
            domainLine: { style: { stroke: t.axisColor } },
          },
          {
            orient: "left",
            regionId: "equityRegion",
            label: {
              style: { fill: t.textColor, fontSize: 10 },
              formatMethod: (v: number) => abbreviateNum(v),
            },
            grid: { style: { stroke: t.gridColor } },
          },
          {
            orient: "bottom",
            regionId: "ddRegion",
            label: { visible: false },
            domainLine: { style: { stroke: t.axisColor } },
          },
          {
            orient: "left",
            regionId: "ddRegion",
            label: {
              style: { fill: t.textColor, fontSize: 10 },
              formatMethod: (v: number) => `${v.toFixed(1)}%`,
            },
            grid: { style: { stroke: t.gridColor } },
          },
        ],
        markLine: [
          {
            regionId: "ddRegion",
            y: minDD,
            line: { style: { stroke: t.downColor, lineDash: [4, 4], lineWidth: 1 } },
            label: {
              text: `Max DD: ${minDD.toFixed(2)}%`,
              position: "insideEndTop",
              style: { fill: t.downColor, fontSize: 10 },
            },
          },
        ],
        scrollBar: [
          {
            orient: "bottom",
            regionId: ["equityRegion", "ddRegion"],
            start: 0,
            end: 1,
          },
        ],
        tooltip: {
          mark: { visible: false },
          dimension: { visible: true },
        },
        animation: false,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any,
      { dom: ref.current }
    );

    chart.renderSync();
    const ro = new ResizeObserver(() => {
      if (ref.current) chart.resize(ref.current.clientWidth, height);
    });
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.release();
    };
  }, [data, dark, height]);

  if (data.length === 0) {
    return <div className="text-muted-foreground text-sm p-4">No equity data</div>;
  }
  return <div ref={ref} style={{ height }} />;
}

