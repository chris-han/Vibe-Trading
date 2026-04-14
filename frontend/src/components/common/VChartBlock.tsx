import { useEffect, useRef, useState } from "react";
import { VChart } from "@visactor/vchart";
import { ensureRegistered } from "@/lib/vchart-register";

function normalizeSpec(input: Record<string, unknown>): Record<string, unknown> {
  const spec: Record<string, unknown> = { ...input };

  const data = spec.data;
  if (data && !Array.isArray(data) && typeof data === "object") {
    const values = (data as { values?: unknown }).values;
    if (Array.isArray(values)) {
      spec.data = [{ id: "source", values }];
    }
  }

  if (spec.type === "pie" && spec.isDonut === true && spec.innerRadius == null) {
    spec.innerRadius = 0.6;
  }

  return spec;
}

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
    ensureRegistered();

    let spec: Record<string, unknown>;
    try {
      spec = JSON.parse(config.trim());
    } catch {
      setError("Invalid JSON in chart block");
      return;
    }

    // Normalize common agent-emitted shorthand and inject a default background.
    const mergedSpec: Record<string, unknown> = {
      background: "transparent",
      ...normalizeSpec(spec),
    };

    let chart: VChart | null = null;
    try {
      chart = new VChart(mergedSpec as any, { dom: containerRef.current });
      chart.renderSync();
      setError(null);
    } catch (e) {
      chart?.release();
      const msg = e instanceof Error ? e.message : "VChart failed to render";
      console.error("[VChartBlock] render error:", msg, "\nspec:", JSON.stringify(mergedSpec, null, 2));
      setError(msg);
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
      <div className="my-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
        <div className="mb-1 font-medium text-destructive">VChart error: {error}</div>
        <pre className="whitespace-pre-wrap text-xs text-muted-foreground leading-relaxed">{config}</pre>
      </div>
    );
  }

  return (
    <div className="vchart-block my-4 rounded-card border border-border bg-card p-4">
      <div ref={containerRef} style={{ height: 320, width: "100%" }} />
    </div>
  );
}
