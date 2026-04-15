import { useEffect, useRef, useState } from "react";
import type { EquityPoint } from "@/lib/api";
import { getChartTheme } from "@/lib/chart-theme";
import { abbreviateNum } from "@/lib/formatters";
import { VChart } from "@visactor/vchart";
import { ensureRegistered } from "@/lib/vchart-register";
import { useDarkMode } from "@/hooks/useDarkMode";

interface Props {
  data: EquityPoint[];
  height?: number;
}

export function EquityChart({ data, height = 300 }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const { dark } = useDarkMode();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ref.current || data.length === 0) return;
    ensureRegistered();
    const t = getChartTheme();
    let chart: VChart | null = null;

    const equityValues = data.map((d) => ({ time: d.time, value: Number(d.equity) }));
    const drawdownValues = data.map((d) => ({ time: d.time, value: Number(d.drawdown) * 100 }));
    const minDD = Math.min(...drawdownValues.map((d) => d.value));

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    try {
      chart = new VChart(
        {
        type: "common",
        background: "transparent",
        layout: {
          type: "grid",
          col: 1,
          row: 2,
          colWidth: [
            { index: 0, size: (maxW: number) => maxW },
          ],
          rowHeight: [
            { index: 0, size: (maxH: number) => Math.floor(maxH * 0.68) },
            { index: 1, size: (maxH: number) => Math.floor(maxH * 0.22) },
          ],
          elements: [
            { modelId: "equityRegion", col: 0, row: 0 },
            { modelId: "ddRegion", col: 0, row: 1 },
          ],
        },
        region: [
          { id: "equityRegion" },
          { id: "ddRegion" },
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
            zero: false,
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
            zero: false,
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
        dataZoom: [
          {
            orient: "bottom",
            axisIndex: 0,
            start: 0,
            end: 1,
            brushSelect: false,
            roamZoom: { enable: true },
            roamDrag: { enable: true, reverse: true },
            roamScroll: { enable: true },
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

  if (data.length === 0) {
    return <div className="text-muted-foreground text-sm p-4">No equity data</div>;
  }
  if (error) {
    return <div className="text-muted-foreground text-sm p-4">Chart unavailable</div>;
  }
  return <div ref={ref} style={{ height }} />;
}
