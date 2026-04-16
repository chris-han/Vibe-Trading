import { useEffect, useRef, useState } from "react";
import { VChart } from "@visactor/vchart";
import { ensureRegistered } from "@/lib/vchart-register";

/**
 * Returns the first data row from the spec's (still-unwrapped) data object.
 * Used by normalizeSpec to inspect field values before wrapping.
 */
function peekFirstDataRow(
  data: unknown
): Record<string, unknown> | null {
  if (data && !Array.isArray(data) && typeof data === "object") {
    const values = (data as { values?: unknown }).values;
    if (Array.isArray(values) && values.length > 0) {
      return values[0] as Record<string, unknown>;
    }
  }
  return null;
}

/**
 * Converts flat path-array data to a VChart-compatible hierarchy tree.
 * Input:  [{path: ["A", "B"], value: 10}, {path: ["A", "C"], value: 5}, ...]
 * Output: {name: "root", children: [{name: "A", children: [{name: "B", value: 10}, ...]}]}
 */
function buildHierarchyFromPaths(
  values: Record<string, unknown>[],
  pathField: string,
  valueField: string
): Record<string, unknown> {
  const root: Record<string, unknown> = { name: "root", children: [] };
  const nodeMap = new Map<string, Record<string, unknown>>();

  values.forEach((item) => {
    const path = item[pathField] as string[];
    const value = item[valueField];
    if (!Array.isArray(path) || path.length === 0) return;

    let parent = root;
    let keyAccum = "";
    path.forEach((segment, i) => {
      keyAccum += "/" + segment;
      if (!nodeMap.has(keyAccum)) {
        const node: Record<string, unknown> = { name: segment };
        if (i === path.length - 1) {
          node[valueField] = value;
        } else {
          node.children = [];
        }
        nodeMap.set(keyAccum, node);
        (parent.children as Record<string, unknown>[]).push(node);
      }
      parent = nodeMap.get(keyAccum)!;
    });
  });

  return root;
}

/**
 * Converts flat parent-reference data to a VChart-compatible hierarchy tree.
 * Input:  [{name:"A", value:10, parent:null}, {name:"B", value:5, parent:"A"}, ...]
 * Output: {name:"A", value:10, children:[{name:"B", value:5, children:[]}]}
 *
 * Handles:
 *  - duplicate names: uses insertion-order index as the internal key
 *  - self-referential rows (parent === name): treated as root nodes
 *  - orphaned rows (parent key not found): treated as root nodes
 */
function buildHierarchyFromParent(
  values: Record<string, unknown>[],
  nameField: string,
  valueField: string,
  parentField: string
): Record<string, unknown> {
  // Use stable numeric indices so duplicate names never collide.
  const nodes: Record<string, unknown>[] = values.map((item) => ({
    name: item[nameField],
    [valueField]: item[valueField],
    children: [] as Record<string, unknown>[],
    _parentName: item[parentField],  // temp; deleted before returning
  }));

  // Build a name→first-index map for parent lookup (first occurrence wins).
  const nameToIdx = new Map<string, number>();
  values.forEach((item, i) => {
    const n = item[nameField] as string;
    if (!nameToIdx.has(n)) nameToIdx.set(n, i);
  });

  const roots: Record<string, unknown>[] = [];
  nodes.forEach((node, i) => {
    const parentName = node._parentName;
    delete node._parentName;
    if (
      parentName == null ||
      parentName === "" ||
      parentName === node.name ||           // self-referential
      !nameToIdx.has(parentName as string)  // orphan
    ) {
      roots.push(node);
    } else {
      const parentIdx = nameToIdx.get(parentName as string)!;
      if (parentIdx === i) {
        roots.push(node); // resolved to self
      } else {
        (nodes[parentIdx].children as Record<string, unknown>[]).push(node);
      }
    }
  });

  if (roots.length === 1) return roots[0];
  return { name: "root", children: roots };
}

function inferCommonSeriesType(dataId: string, index: number): string {
  const lowered = dataId.toLowerCase();
  if (lowered.includes('line')) return 'line';
  if (lowered.includes('area')) return 'area';
  if (lowered.includes('scatter')) return 'scatter';
  if (lowered.includes('pie')) return 'pie';
  if (lowered.includes('bar') || lowered.includes('column')) return 'bar';
  return index === 0 ? 'bar' : 'line';
}

function normalizeSpec(input: Record<string, unknown>): Record<string, unknown> {
  const spec: Record<string, unknown> = { ...input };
  const chartType = spec.type as string;

  // Peek at the first data row before any wrapping so type-conversion logic
  // can inspect actual field values (e.g. numeric vs. string x/y).
  const firstRow = peekFirstDataRow(spec.data);

  // ── TYPE CONVERSIONS ─────────────────────────────────────────────────────────
  // VChart's "correlation" chart type:
  //  • If x/y fields contain strings → the model is describing a correlation
  //    matrix.  Convert to heatmap (xField, yField, valueField).
  //  • If x/y fields contain numbers → the model is describing a scatter plot.
  //    Convert to scatter and clean up.
  if (chartType === "correlation") {
    const xVal = firstRow?.[spec.xField as string ?? "x"];
    if (typeof xVal === "string") {
      // String-keyed correlation matrix → heatmap
      spec.type = "heatmap";
      // Map common matrix intensity fields to heatmap.valueField so the
      // renderer knows which property to color (supports `correlation`,
      // `value`, `size`, or an explicit `colorField`).
      spec.valueField = spec.valueField ?? spec.sizeField ?? spec.colorField ?? "correlation";
      // heatmap doesn't use `sizeField`; remove it to avoid confusion.
      if (spec.sizeField) delete spec.sizeField;
    } else {
      // Numeric scatter-like correlation → scatter
      spec.type = "scatter";
      if (!spec.sizeField && typeof spec.seriesField === "string" &&
          ["size", "sizeField"].includes(spec.seriesField)) {
        spec.sizeField = spec.seriesField;
        delete spec.seriesField;
      }
      delete spec.axes; // scatter infers axes automatically
    }
  }

  // VChart's "sequence" is an event-stream chart requiring a complex series[]
  // array.  The model emits a simple timeline spec → convert to line.
  if (spec.type === "sequence") {
    spec.type = "line";
    if (spec.categoryField && !spec.xField) { spec.xField = spec.categoryField; delete spec.categoryField; }
    if (spec.valueField && !spec.yField) { spec.yField = spec.valueField; delete spec.valueField; }
  }

  // VChart's "histogram" expects numeric bin ranges (xField + x2Field).
  // The model emits categorical bar-like data → convert to bar.
  if (spec.type === "histogram") {
    spec.type = "bar";
    delete spec.axes; // bar picks band+linear by default; avoid type="linear" override
  }

  // ── DATA WRAPPING – type-specific ─────────────────────────────────────────
  const rawData = spec.data;
  const isUnwrapped =
    rawData && !Array.isArray(rawData) && typeof rawData === "object" &&
    Array.isArray((rawData as { values?: unknown }).values);

  if (isUnwrapped) {
    const values = (rawData as { values: unknown[] }).values;

    // Hierarchy charts (sunburst / circlePacking / treemap) – two data formats:
    //
    //  1. pathField: model emits [{path:["A","B"], value:n}, ...]
    //     → buildHierarchyFromPaths()
    //  2. parentField: model emits [{name:"B", value:n, parent:"A"}, ...]
    //     → buildHierarchyFromParent()
    if (["sunburst", "circlePacking", "treemap"].includes(spec.type as string) && spec.pathField) {
      const pathField = spec.pathField as string;
      const valueField = (spec.valueField as string) || "value";
      const tree = buildHierarchyFromPaths(
        values as Record<string, unknown>[],
        pathField,
        valueField
      );
      spec.data = [{ id: "source", values: [tree] }];
      spec.categoryField = spec.categoryField ?? "name";
      delete spec.pathField;
    }

    else if (["sunburst", "circlePacking", "treemap"].includes(spec.type as string) && spec.parentField) {
      const nameField = (spec.nameField as string) || "name";
      const valueField = (spec.valueField as string) || "value";
      const parentField = spec.parentField as string;
      const tree = buildHierarchyFromParent(
        values as Record<string, unknown>[],
        nameField,
        valueField,
        parentField
      );
      spec.data = [{ id: "source", values: [tree] }];
      spec.categoryField = "name"; // tree nodes use "name" key from buildHierarchyFromParent
      delete spec.parentField;
      delete spec.nameField; // VChart reads categoryField, not nameField
    }

    // Sankey: sankeyLayout.computeSourceTargetNodeLinks checks `if (data.nodes && ...)`
    // An empty array `[]` is truthy, causing every link to be skipped (nodes not pre-populated).
    // Omit the nodes property so VChart auto-creates nodes from the link source/target fields.
    else if (spec.type === "sankey") {
      spec.data = [{ id: "source", values: [{ links: values }] }];
    }

    // Generic case: wrap {values:[…]} as [{id:"source", values:[…]}]
    else {
      spec.data = [{ id: "source", values }];
    }
  }

  // scatter: if the model-emitted xField/yField don't exist as keys in the data
  // (e.g. yField:"value" when data row has {x, y}), fall back to the literal "x"/"y"
  // keys when they exist.  This catches a common model mistake.
  if (spec.type === "scatter" && firstRow) {
    if (spec.xField && !(spec.xField as string in firstRow) && "x" in firstRow) {
      spec.xField = "x";
    }
    if (spec.yField && !(spec.yField as string in firstRow) && "y" in firstRow) {
      spec.yField = "y";
    }
  }

  // Radar: uses categoryField/valueField, not xField/yField.
  if (spec.type === "radar") {
    if (spec.xField && !spec.categoryField) { spec.categoryField = spec.xField; delete spec.xField; }
    if (spec.yField && !spec.valueField) { spec.valueField = spec.yField; delete spec.yField; }
  }

  // wordCloud: uses nameField (not categoryField) for the word text.
  if (spec.type === "wordCloud") {
    if (spec.categoryField && !spec.nameField) { spec.nameField = spec.categoryField; delete spec.categoryField; }
    if (spec.seriesField && !spec.nameField) { spec.nameField = spec.seriesField; delete spec.seriesField; }
  }

  // linearProgress extends CartesianSeries: category→yField (band/left axis),
  // value→xField (linear/bottom axis) for horizontal bars.
  if (spec.type === "linearProgress") {
    if (spec.categoryField && !spec.yField) { spec.yField = spec.categoryField; delete spec.categoryField; }
    if (spec.valueField && !spec.xField) { spec.xField = spec.valueField; delete spec.valueField; }
  }

  // heatmap: uses valueField for heat intensity; model often emits seriesField.
  if (spec.type === "heatmap") {
    if (spec.seriesField && !spec.valueField) { spec.valueField = spec.seriesField; delete spec.seriesField; }
  }

  // sankey: model sometimes emits nodeField instead of sourceField.
  if (spec.type === "sankey") {
    if (spec.nodeField && !spec.sourceField) { spec.sourceField = spec.nodeField; delete spec.nodeField; }
  }

  // common: model emits a simplified combo-chart shorthand with one dataset per
  // series and yField as an array. Expand it into VChart's series[] format.
  if (spec.type === "common" && !Array.isArray(spec.series) && Array.isArray(spec.data)) {
    const datasets = spec.data as Record<string, unknown>[];
    const yFields = Array.isArray(spec.yField) ? spec.yField : [];
    if (datasets.length > 0 && typeof spec.xField === "string") {
      const series = datasets.map((dataset, index) => {
        const dataId = typeof dataset.id === "string" && dataset.id ? dataset.id : `series_${index + 1}`;
        const values = Array.isArray(dataset.values) ? dataset.values : [];
        const firstValue = values[0] as Record<string, unknown> | undefined;
        const inferredYField =
          (typeof yFields[index] === "string" && yFields[index]) ||
          Object.keys(firstValue ?? {}).find((key) => key !== spec.xField) ||
          "value";
        return {
          type: inferCommonSeriesType(dataId, index),
          dataId,
          xField: spec.xField,
          yField: inferredYField,
        };
      });
      spec.series = series;
      if (!Array.isArray(spec.axes) || spec.axes.length === 0) {
        spec.axes = [
          { orient: "bottom", type: "band" },
          { orient: "left", type: "linear" },
        ];
      }
      delete spec.yField;
      delete spec.seriesField;
    }
  }

  // ── SPECIAL POST-WRAP PATCHES ─────────────────────────────────────────────
  // circularProgress: requires categoryField for the radius band axis.
  // Inject a synthetic label field when the model omits it.
  if (spec.type === "circularProgress" && !spec.categoryField) {
    spec.categoryField = "_label";
    const d = spec.data as Record<string, unknown>[];
    if (Array.isArray(d) && d[0]) {
      const ds = d[0] as { values?: unknown[] };
      if (Array.isArray(ds.values)) {
        ds.values = ds.values.map((v: any) => ({ _label: "progress", ...v }));
      }
    }
  }

  // waterfall: spec.total.tagField tells VChart which data rows are totals.
  // The model marks them with isTotal:true in the data but omits spec.total.
  if (spec.type === "waterfall" && !spec.total) {
    const d = spec.data as Record<string, unknown>[];
    if (Array.isArray(d) && d[0]) {
      const ds = d[0] as { values?: unknown[] };
      if (Array.isArray(ds.values) && ds.values.some((v: any) => "isTotal" in v)) {
        spec.total = { type: "field", tagField: "isTotal" };
      }
    }
  }

  // ── PIE / DONUT ───────────────────────────────────────────────────────────
  if (spec.type === "pie" && spec.isDonut === true) {
    // VChart's pieTheme sets outerRadius:0.6 via _mergeThemeToSpec. If the
    // innerRadius also defaults to 0.6 the ring width is zero → invisible.
    if (spec.innerRadius == null) spec.innerRadius = 0.5;
    if (spec.outerRadius == null) spec.outerRadius = 0.8;
  }

  if (spec.type === "pie") {
    // Animation pipeline can leave arcs at near-zero opacity; force full opacity.
    const pie = (spec.pie ?? {}) as Record<string, unknown>;
    const style = ((pie.style as Record<string, unknown>) ?? {}) as Record<string, unknown>;
    style.fillOpacity = style.fillOpacity ?? 1;
    style.opacity = style.opacity ?? 1;
    pie.style = style;
    spec.pie = pie;
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
      animation: false,
      animationAppear: false,
      animationEnter: false,
      animationUpdate: false,
      animationExit: false,
      ...normalizeSpec(spec),
    };

    // VChart auto-detects prefers-color-scheme and may apply a dark theme
    // (light-colored slices) even when the card background is white, making
    // chart elements invisible. Explicitly mirror the page theme class.
    const isDark = document.documentElement.classList.contains("dark");
    const theme = isDark ? "dark" : "light";

    let chart: VChart | null = null;
    try {
      // animation: false in both spec AND options for maximum coverage
      chart = new VChart(mergedSpec as any, {
        dom: containerRef.current,
        theme,
        animation: false,
      });
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
      <div ref={containerRef} style={{ height: 420, width: "100%" }} />
    </div>
  );
}
