import { useState, useEffect, useMemo, memo } from "react";
import { ChevronDown, ChevronRight, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";
import type { AgentMessage } from "@/types/agent";

/* ---------- Tool display name keys (mapped to i18n) ---------- */
const TOOL_I18N_KEY: Record<string, string> = {
  load_skill: "toolLoadSkill",
  write_file: "toolWriteFile",
  edit_file: "toolEditFile",
  read_file: "toolReadFile",
  run_backtest: "toolRunBacktest",
  bash: "toolBash",
  read_url: "toolReadUrl",
  read_document: "toolReadDocument",
  compact: "toolCompact",
  create_task: "toolCreateTask",
  update_task: "toolUpdateTask",
  spawn_subagent: "toolSpawnSubagent",
};

interface Props {
  messages: AgentMessage[];
  isLatest?: boolean;
}

export const ThinkingTimeline = memo(function ThinkingTimeline({ messages, isLatest = false }: Props) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(isLatest);

  const toolLabel = (tool?: string): string => {
    if (!tool) return t.toolProcessing;
    const key = TOOL_I18N_KEY[tool];
    return key ? (t as Record<string, string>)[key] || tool : tool;
  };

  useEffect(() => {
    if (!isLatest) setExpanded(false);
  }, [isLatest]);

  const { steps, hasError, isRunning, totalMs, latestTool, latestThinking } = useMemo(() => {
    let totalMs = 0;
    let latestTool = "";
    let latestThinking = "";
    // Merge tool_call + tool_result pairs into "steps"
    const steps: Array<{ tool: string; label: string; status: "running" | "ok" | "error"; elapsed_ms?: number }> = [];

    for (const m of messages) {
      if (m.type === "thinking" && m.content) latestThinking = m.content;
      if (m.type === "tool_call") {
        steps.push({ tool: m.tool || "", label: toolLabel(m.tool), status: m.status === "running" ? "running" : "ok", elapsed_ms: undefined });
        if (m.status === "running") latestTool = m.tool || "";
      }
      if (m.type === "tool_result") {
        const existing = [...steps].reverse().find(s => s.tool === m.tool);
        if (existing) {
          existing.status = m.status === "ok" ? "ok" : "error";
          existing.elapsed_ms = m.elapsed_ms;
        }
        if (m.elapsed_ms) totalMs += m.elapsed_ms;
      }
    }

    return {
      steps,
      hasError: steps.some(s => s.status === "error"),
      isRunning: steps.some(s => s.status === "running"),
      totalMs,
      latestTool,
      latestThinking,
    };
  }, [messages]);

  const stepCount = steps.length;
  const summaryText = isRunning
    ? t.thinkingRunning.replace("{tool}", toolLabel(latestTool))
    : t.thinkingDone.replace("{count}", String(stepCount)) + (totalMs > 0 ? ` · ${(totalMs / 1000).toFixed(1)}s` : "");

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      {/* Summary bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-muted/50 transition-colors"
      >
        {expanded
          ? <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
          : <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />}
        {isRunning ? (
          <Loader2 className="h-3 w-3 text-primary animate-spin shrink-0" />
        ) : hasError ? (
          <XCircle className="h-3 w-3 text-destructive shrink-0" />
        ) : (
          <CheckCircle2 className="h-3 w-3 text-success shrink-0" />
        )}
        <span className={cn("text-foreground font-medium", isRunning && "text-primary")}>
          {summaryText}
        </span>
      </button>

      {/* Thinking preview when running but collapsed */}
      {!expanded && isRunning && latestThinking && (
        <div className="px-3 pb-2 -mt-1">
          <p className="text-[11px] text-muted-foreground line-clamp-1 pl-5 italic">
            {latestThinking.slice(-100)}
          </p>
        </div>
      )}

      {/* Expanded step list */}
      {expanded && steps.length > 0 && (
        <div className="border-t border-border px-3 py-2 space-y-1">
          {steps.map((step) => (
            <div key={`${step.tool}-${step.label}`} className="flex items-center gap-2 py-0.5 text-xs">
              {/* Status icon */}
              {step.status === "running" ? (
                <Loader2 className="h-3 w-3 text-primary animate-spin shrink-0" />
              ) : step.status === "error" ? (
                <XCircle className="h-3 w-3 text-destructive shrink-0" />
              ) : (
                <CheckCircle2 className="h-3 w-3 text-success shrink-0" />
              )}

              {/* Label */}
              <span className={cn(
                "flex-1",
                step.status === "running" ? "text-foreground font-medium" : "text-muted-foreground"
              )}>
                {step.label}
              </span>

              {/* Duration or status */}
              {step.status === "running" ? (
                <span className="text-[10px] text-primary font-medium">{t.toolRunning}</span>
              ) : step.elapsed_ms != null ? (
                <span className="text-[10px] text-muted-foreground tabular-nums">{(step.elapsed_ms / 1000).toFixed(1)}s</span>
              ) : null}
            </div>
          ))}
        </div>
      )}

      {/* Expanded: show thinking content if any (for Q&A without tools) */}
      {expanded && steps.length === 0 && latestThinking && (
        <div className="border-t border-border px-3 py-2">
          <p className="text-xs text-muted-foreground leading-relaxed line-clamp-4">
            {latestThinking}
          </p>
        </div>
      )}
    </div>
  );
});
