import { useEffect, useId, useRef, useState } from "react";
import mermaid from "mermaid";

let mermaidInitialized = false;

const DIAGRAM_START_RE = /^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|journey|timeline|mindmap|gitGraph|quadrantChart|xychart|sankey-beta|block-beta|architecture-beta|radar-beta)\b/i;

function ensureMermaidInitialized() {
  if (mermaidInitialized) {
    return;
  }
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: "neutral",
    themeVariables: {
      background: "transparent",
    },
    fontFamily: "ui-sans-serif, system-ui, sans-serif",
  });
  mermaidInitialized = true;
}

function stripFences(source: string): string {
  return source
    .replace(/^\s*```\s*mermaid\s*\n?/i, "")
    .replace(/\n?\s*```\s*$/i, "")
    .trim();
}

function trimToDiagramBody(source: string): string {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const start = lines.findIndex((line) => DIAGRAM_START_RE.test(line.trim()));
  if (start < 0) {
    return source;
  }
  const end = lines.findIndex((line, idx) => idx > start && line.trim().startsWith("```"));
  const body = end > start ? lines.slice(start, end) : lines.slice(start);
  return body.join("\n").trim();
}

function stripHtmlFromLabel(text: string): string {
  return text.replace(/<br\s*\/?>/gi, " ").replace(/<[^>]+>/g, "");
}

function sanitizeQuotedLabels(source: string): string {
  // Mermaid node labels can break on nested quotes or HTML tags in model-generated text.
  return source
    .replace(/\[([^\]\n]*)\]/g, (_match, inner: string) => `[${stripHtmlFromLabel(inner).replace(/"/g, "'")}]`)
    .replace(/\(([^\)\n]*)\)/g, (_match, inner: string) => `(${stripHtmlFromLabel(inner).replace(/"/g, "'")})`)
    .replace(/\{([^\}\n]*)\}/g, (_match, inner: string) => `{${stripHtmlFromLabel(inner).replace(/"/g, "'")}}`);
}

/** Merge standalone `: event` continuation lines onto the preceding period line for timeline diagrams */
function mergeTimelineContinuations(source: string): string {
  const lines = source.split("\n");
  const out: string[] = [];
  for (const line of lines) {
    if (/^\s+:\s/.test(line) && out.length > 0 && !/^\s*$/.test(out[out.length - 1])) {
      out[out.length - 1] = out[out.length - 1].trimEnd() + " " + line.trim();
    } else {
      out.push(line);
    }
  }
  return out.join("\n");
}

function buildRepairCandidates(raw: string): string[] {
  const base = stripFences(raw);
  const clipped = trimToDiagramBody(base);
  const sanitized = sanitizeQuotedLabels(clipped);
  const sanitizedUnescaped = sanitizeQuotedLabels(clipped.replace(/\\"/g, '"'));
  const merged = mergeTimelineContinuations(clipped);
  const mergedSanitized = sanitizeQuotedLabels(mergeTimelineContinuations(sanitizedUnescaped));
  const candidates = [
    clipped,
    sanitized,
    sanitizedUnescaped,
    merged,
    mergedSanitized,
    sanitizeQuotedLabels(
      clipped
        .split("\n")
        .filter((line) => !/^\s{0,3}#{1,6}\s+/.test(line))
        .join("\n"),
    ),
  ];

  return [...new Set(candidates.map((item) => item.trim()).filter(Boolean))];
}

export function MermaidBlock({ chart }: { chart: string }) {
  const elementId = useId().replace(/:/g, "-");
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const source = chart.trim();

    if (!source) {
      setError("Empty Mermaid diagram");
      return;
    }

    ensureMermaidInitialized();

    const renderSafely = async () => {
      const candidates = buildRepairCandidates(source);
      let lastError: unknown = null;

      for (let i = 0; i < candidates.length; i += 1) {
        try {
          const current = candidates[i];
          const { svg, bindFunctions } = await mermaid.render(`mermaid-${elementId}-${i}`, current);
          // Mermaid sometimes returns an error SVG instead of throwing — detect and reject it.
          if (
            svg.includes("Syntax error") ||
            svg.includes("error-text") ||
            svg.includes("error-icon") ||
            svg.includes("#bomb")
          ) {
            throw new Error("Mermaid returned error SVG");
          }
          if (cancelled || !containerRef.current) {
            return;
          }
          containerRef.current.innerHTML = svg;
          bindFunctions?.(containerRef.current);
          setError(null);
          return;
        } catch (e) {
          lastError = e;
        }
      }

      if (cancelled) {
        return;
      }
      const message = lastError instanceof Error ? lastError.message : "Unable to render Mermaid diagram";
      setError(message);
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
    };

    void renderSafely();

    return () => {
      cancelled = true;
    };
  }, [chart, elementId]);

  if (error) {
    return (
      <div className="my-4 overflow-hidden rounded-2xl border border-amber-300/40 bg-amber-50/60 text-amber-950 dark:border-amber-500/30 dark:bg-amber-950/20 dark:text-amber-100">
        <div className="border-b border-current/10 px-4 py-2 text-xs font-medium">Mermaid render failed</div>
        <pre className="m-0 overflow-x-auto p-4 text-[11px] leading-relaxed whitespace-pre-wrap">{chart}</pre>
      </div>
    );
  }

  return (
    <div className="my-4 overflow-x-auto rounded-card border border-border bg-card p-4 text-foreground">
      <div
        ref={containerRef}
        className="min-w-max [&_svg]:h-auto [&_svg]:max-w-none [&_svg]:bg-transparent"
      />
    </div>
  );
}