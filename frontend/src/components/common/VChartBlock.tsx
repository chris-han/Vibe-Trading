import { useEffect, useRef, useState } from "react";
import { VChart } from "@visactor/vchart";

/**
 * Renders a VChart chart from a JSON spec string inside a markdown code fence.
 *
 * Usage in markdown:
 * ```vchart
 * { "type": "bar", "data": [...], "xField": "x", "yField": "y" }
 * ```
 */
export function VChartBlock({ config }: { config: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    let spec: Record<string, unknown>;
    try {
      spec = JSON.parse(config.trim());
    } catch {
      setError("Invalid JSON in chart block");
      return;
    }

    // Inject a transparent background if not specified
    const mergedSpec: Record<string, unknown> = {
      background: "transparent",
      ...spec,
    };

    let chart: VChart | null = null;
    try {
      chart = new VChart(mergedSpec as any, { dom: containerRef.current });
      chart.renderSync();
      setError(null);
    } catch (e) {
      chart?.release();
      setError(e instanceof Error ? e.message : "VChart failed to render");
      return;
    }

    const ro = new ResizeObserver(() => {
      try { chart?.resize(containerRef.current!.clientWidth, containerRef.current!.clientHeight); } catch { /* ignore */ }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart?.release();
    };
  }, [config]);

  if (error) {
    return (
      <pre className="my-2 whitespace-pre-wrap text-sm leading-relaxed">{config}</pre>
    );
  }

  return (
    <div className="vchart-block my-4 rounded-card border border-border bg-card p-4">
      <div ref={containerRef} style={{ height: 320, width: "100%" }} />
    </div>
  );
}
