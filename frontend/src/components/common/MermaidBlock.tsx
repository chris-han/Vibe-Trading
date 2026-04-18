import { useEffect, useId, useRef, useState } from "react";
import mermaid from "mermaid";

let mermaidInitialized = false;
let renderCounter = 0;

const MERMAID_ERROR_SVG_RE = /(Syntax error in text|class="error-icon"|class="error-text")/i;

// Serialize mermaid.render() calls — mermaid uses global state and breaks under concurrency.
let renderQueue: Promise<void> = Promise.resolve();
function enqueueRender<T>(fn: () => Promise<T>): Promise<T> {
  let resolve: (v: T) => void;
  let reject: (e: unknown) => void;
  const p = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  renderQueue = renderQueue.then(() => fn().then(resolve!, reject!), () => fn().then(resolve!, reject!));
  return p;
}

const DIAGRAM_START_RE = /^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|pie|journey|timeline|mindmap|gitGraph|quadrantChart|xychart(?:-beta)?|sankey-beta|block-beta|architecture-beta|radar(?:-beta)?)\b/i;

function ensureMermaidInitialized() {
  if (mermaidInitialized) {
    return;
  }
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "loose",
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

function isMermaidErrorSvg(svg: string): boolean {
  return MERMAID_ERROR_SVG_RE.test(svg);
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
  // Mermaid node labels can break on nested quotes, HTML tags, emoji, or special chars.
  // Wrap bracket/paren/brace labels in double quotes and escape inner quotes.
  return source
    .replace(/\[([^\]\n]*)\]/g, (_match, inner: string) => {
      const clean = stripHtmlFromLabel(inner).replace(/"/g, "'");
      return `["${clean}"]`;
    })
    .replace(/\(([^\)\n]*)\)/g, (_match, inner: string) => {
      const clean = stripHtmlFromLabel(inner).replace(/"/g, "'");
      return `("${clean}")`;
    })
    .replace(/\{([^\}\n]*)\}/g, (_match, inner: string) => {
      const clean = stripHtmlFromLabel(inner).replace(/"/g, "'");
      return `{"${clean}"}`;
    });
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

/**
 * Fix Mermaid `timeline` diagrams:
 *  1. `section Name : extra` → `section Name`  (section lines must not contain `:`)
 *  2. Strip HTML tags (e.g. `<br/>`) from event text on Period : Event lines
 */
function sanitizeTimelineDiagram(source: string): string {
  if (!/^\s*timeline\b/i.test(source)) return source;
  return source
    .split("\n")
    .map((line) => {
      // Fix section lines: strip everything after the first colon
      if (/^\s*section\s/i.test(line)) {
        return line.replace(/(:.*$)/, "").trimEnd();
      }
      // Strip HTML tags from event values (text after `:` separator)
      if (/:\s*\S/.test(line)) {
        return line.replace(/:\s*(.+)/, (_m, val: string) => ": " + val.replace(/<[^>]+>/g, " ").trim());
      }
      return line;
    })
    .join("\n");
}

function buildRepairCandidates(raw: string): string[] {
  const base = stripFences(raw);
  const clipped = trimToDiagramBody(base);
  const isTimeline = /^\s*timeline\b/i.test(clipped);
  const sanitized = sanitizeQuotedLabels(clipped);
  const sanitizedUnescaped = sanitizeQuotedLabels(clipped.replace(/\\"/g, '"'));
  const merged = mergeTimelineContinuations(clipped);
  const mergedSanitized = sanitizeQuotedLabels(mergeTimelineContinuations(sanitizedUnescaped));
  const timelineSanitized = sanitizeTimelineDiagram(clipped);
  const timelineMergedSanitized = sanitizeTimelineDiagram(mergeTimelineContinuations(clipped));
  const headingStrippedSanitized = sanitizeQuotedLabels(
    clipped
      .split("\n")
      .filter((line) => !/^\s{0,3}#{1,6}\s+/.test(line))
      .join("\n"),
  );

  // Mermaid timeline parsing is brittle: malformed section headers like
  // `section 2022 : Defensive` can throw before later repair candidates run.
  // Try the normalized timeline forms first so we avoid poisoning the render.
  const candidates = isTimeline
    ? [
        timelineMergedSanitized,
        timelineSanitized,
        mergeTimelineContinuations(timelineSanitized),
        merged,
      ]
    : [
        clipped,
        sanitized,
        sanitizedUnescaped,
        timelineSanitized,
        timelineMergedSanitized,
        merged,
        mergedSanitized,
        headingStrippedSanitized,
      ];

  // If no recognized diagram-type keyword was found on the first line, prepend "graph TD"
  // to catch cases where the model wrote "top-down" or similar invalid openers.
  const firstLine = clipped.split("\n")[0]?.trim() ?? "";
  if (!DIAGRAM_START_RE.test(firstLine)) {
    const withPrefix = `graph TD\n${clipped}`;
    candidates.push(
      withPrefix,
      sanitizeQuotedLabels(withPrefix),
    );
  }

  return [...new Set(candidates.map((item) => item.trim()).filter(Boolean))];
}

export function MermaidBlock({ chart }: { chart: string }) {
  const id = useId().replace(/:/g, "-");
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Unique token per effect invocation — survives React StrictMode double-mount.
    const token = ++renderCounter;
    const source = chart.trim();

    if (!source) {
      setError("Empty Mermaid diagram");
      return;
    }

    ensureMermaidInitialized();

    const renderSafely = async () => {
      const candidates = buildRepairCandidates(source);
      let lastError: unknown = null;

      for (let index = 0; index < candidates.length; index += 1) {
        if (cancelled) return;
        const renderId = `mermaid-${id}-${token}-${index}`;
        try {
          const current = candidates[index];

          const { svg, bindFunctions } = await enqueueRender(() =>
            mermaid.render(renderId, current),
          );

          if (isMermaidErrorSvg(svg)) {
            throw new Error("Mermaid returned an error diagram instead of a rendered chart");
          }

          // Clean up the temp element mermaid may leave behind.
          document.getElementById(renderId)?.remove();
          document.getElementById(`d${renderId}`)?.remove();

          if (cancelled || !containerRef.current) {
            return;
          }

          containerRef.current.innerHTML = svg;
          bindFunctions?.(containerRef.current);
          setError(null);
          return;
        } catch (e) {
          // Clean up orphaned temp elements that mermaid leaves in <body> when it throws
          // on parse or render errors (removeTempElements() is not called on the throw path).
          document.getElementById(renderId)?.remove();
          document.getElementById(`d${renderId}`)?.remove();
          lastError = e;
        }
      }

      if (cancelled) {
        return;
      }

      setError(lastError instanceof Error ? lastError.message : "Unable to render Mermaid diagram");
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
    };

    void renderSafely();

    return () => { cancelled = true; };
  }, [chart, id]);

  if (error) {
    return (
      <pre className="my-2 whitespace-pre-wrap text-sm leading-relaxed">{chart}</pre>
    );
  }

  return (
    <div className="mermaid-block my-4 overflow-x-auto rounded-card border border-border bg-card p-4 text-foreground">
      <div ref={containerRef} className="flex justify-center [&_svg]:h-auto [&_svg]:max-w-full [&_svg]:bg-transparent" />
    </div>
  );
}
