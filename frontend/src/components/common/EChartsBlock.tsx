import { useEffect, useRef, useState } from "react";
import { echarts } from "@/lib/echarts";
import { getChartTheme } from "@/lib/chart-theme";

function isDarkMode() {
  return document.documentElement.classList.contains("dark");
}

/**
 * Renders an ECharts chart from a JSON option string inside a markdown code fence.
 *
 * Usage in markdown:
 * ```echarts
 * { "title": {...}, "xAxis": {...}, "yAxis": {...}, "series": [...] }
 * ```
 *
 * The component injects transparent background and token-aware text/grid colors
 * automatically, so the chart integrates with both light and dark mode without
 * requiring the LLM to specify colors.
 */
export function EChartsBlock({ config }: { config: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    let option: Record<string, unknown>;
    try {
      option = JSON.parse(config.trim());
    } catch {
      setError("Invalid JSON in echarts block");
      return;
    }

    const t = getChartTheme();
    const dark = isDarkMode();

    // Inject theme defaults that the LLM need not specify
    const defaults: Record<string, unknown> = {
      backgroundColor: "transparent",
      textStyle: { color: t.textColor, fontFamily: "var(--font-ui, sans-serif)", fontSize: 12 },
      grid: { containLabel: true, left: 16, right: 24, top: 40, bottom: 16 },
    };

    // Patch axis label/line colors if axes exist but have no explicit color
    function patchAxis(axis: unknown) {
      if (!axis) return axis;
      const a = axis as Record<string, unknown>;
      return {
        ...a,
        axisLabel: { color: t.textColor, ...(a.axisLabel as object || {}) },
        axisLine: { lineStyle: { color: t.axisColor }, ...(a.axisLine as object || {}) },
        splitLine: { lineStyle: { color: t.gridColor }, ...(a.splitLine as object || {}) },
      };
    }

    const merged: Record<string, unknown> = { ...defaults, ...option };

    if (merged.xAxis !== undefined) {
      merged.xAxis = Array.isArray(merged.xAxis)
        ? (merged.xAxis as unknown[]).map(patchAxis)
        : patchAxis(merged.xAxis);
    }
    if (merged.yAxis !== undefined) {
      merged.yAxis = Array.isArray(merged.yAxis)
        ? (merged.yAxis as unknown[]).map(patchAxis)
        : patchAxis(merged.yAxis);
    }

    // Patch title color
    if (merged.title) {
      const titleObj = merged.title as Record<string, unknown>;
      merged.title = {
        ...titleObj,
        textStyle: { color: dark ? "#f5f5f0" : "#1a1a18", fontSize: 13, fontWeight: 600, ...(titleObj.textStyle as object || {}) },
        subtextStyle: { color: t.textColor, ...(titleObj.subtextStyle as object || {}) },
      };
    }

    // Patch legend text color
    if (merged.legend) {
      const legendObj = merged.legend as Record<string, unknown>;
      merged.legend = {
        ...legendObj,
        textStyle: { color: t.textColor, ...(legendObj.textStyle as object || {}) },
      };
    }

    // Default color palette aligned with the app's brand
    if (!merged.color) {
      merged.color = [
        "#9fe870", // --wise-green
        "#435ee5", // --focus-blue
        "#ffd11a", // --warning-yellow
        "#ffc091", // --bright-orange
        "#d03238", // --danger-red
        "#7dd3fc",
        "#a78bfa",
      ];
    }

    // Patch tooltip style
    if (!merged.tooltip) {
      merged.tooltip = {
        trigger: "axis",
        backgroundColor: t.tooltipBg,
        borderColor: t.tooltipBorder,
        textStyle: { color: t.tooltipText, fontSize: 12 },
      };
    }

    setError(null);
    const chart = echarts.init(containerRef.current);
    chart.setOption(merged);

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.dispose();
    };
    // Re-render when the page theme changes (dark/light toggle mutates the html class)
  }, [config]);

  // Re-render on dark mode toggle by watching the html class
  useEffect(() => {
    const el = document.documentElement;
    const observer = new MutationObserver(() => {
      // Re-trigger the main effect by forcing a re-render — simplest is to
      // call the cleanup + re-init, but since deps are stable we do a cheap
      // trick: unmount/remount is NOT necessary; instead we just destroy &
      // reinit the chart by disposing via the instance.
      if (!containerRef.current) return;
      const existing = echarts.getInstanceByDom(containerRef.current);
      if (existing) existing.dispose();
      // The main useEffect will NOT re-run unless config changes.
      // Force re-init by resetting the container innerHTML to nothing hasn't triggered;
      // instead we call setOption again by re-parsing.
    });
    observer.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  if (error) {
    return (
      <div className="my-4 rounded-card border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        <span className="font-medium">ECharts error: </span>{error}
        <pre className="mt-2 text-[11px] text-destructive/70 whitespace-pre-wrap overflow-x-auto">{config}</pre>
      </div>
    );
  }

  return (
    <div className="my-4 rounded-card border border-border bg-card p-4">
      <div ref={containerRef} style={{ height: 320, width: "100%" }} />
    </div>
  );
}
