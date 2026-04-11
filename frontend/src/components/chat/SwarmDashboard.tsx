import { useEffect, useState, useRef } from "react";
import { CheckCircle2, XCircle, Loader2, Clock, Timer, ChevronDown, ChevronRight, Wrench } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface SwarmAgent {
  id: string;
  status: "waiting" | "running" | "done" | "failed" | "retry";
  tool: string;
  iters: number;
  startedAt: number;
  elapsed: number;
  lastText: string;
  /** Full accumulated streaming reasoning text for this agent */
  reasoningText: string;
  summary: string;
}

export interface SwarmDashboardProps {
  preset: string;
  agents: Record<string, SwarmAgent>;
  agentOrder: string[];
  currentLayer: number;
  finished: boolean;
  finalStatus: string;
  startTime: number;
  completedSummaries: Array<{ agentId: string; summary: string }>;
  finalReport: string;
}

const AGENT_COLORS = [
  "text-primary", "text-foreground", "text-success",
  "text-warning", "text-info", "text-destructive",
  "text-foreground/70", "text-success/80",
];
const AGENT_BG = [
  "bg-primary/10", "bg-muted", "bg-success/10",
  "bg-warning/10", "bg-info/10", "bg-destructive/10",
  "bg-muted/50", "bg-primary/5",
];
const AGENT_BORDER = [
  "border-primary/30", "border-border", "border-success/30",
  "border-warning/30", "border-info/30", "border-destructive/30",
  "border-border/50", "border-primary/20",
];

function agentColor(idx: number) { return AGENT_COLORS[idx % AGENT_COLORS.length]; }
function agentBg(idx: number) { return AGENT_BG[idx % AGENT_BG.length]; }
function agentBorder(idx: number) { return AGENT_BORDER[idx % AGENT_BORDER.length]; }

function formatTime(seconds: number) {
  if (seconds <= 0) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function StatusIcon({ status }: { status: SwarmAgent["status"] }) {
  switch (status) {
    case "running": return <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />;
    case "done": return <CheckCircle2 className="h-3.5 w-3.5 text-success shrink-0" />;
    case "failed": return <XCircle className="h-3.5 w-3.5 text-destructive shrink-0" />;
    case "retry": return <Loader2 className="h-3.5 w-3.5 animate-spin text-warning shrink-0" />;
    default: return <Clock className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0" />;
  }
}

/** Single agent card with expandable streaming reasoning */
function AgentCard({
  agent,
  idx,
  now,
}: {
  agent: SwarmAgent;
  idx: number;
  now: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const reasoningRef = useRef<HTMLDivElement>(null);
  const isActive = agent.status === "running" || agent.status === "retry";
  const hasReasoning = agent.reasoningText.length > 0;

  // Auto-expand when agent starts running
  useEffect(() => {
    if (isActive) setExpanded(true);
  }, [isActive]);

  // Auto-close when done (delay so user can see final state)
  useEffect(() => {
    if (agent.status === "done" || agent.status === "failed") {
      const t = setTimeout(() => setExpanded(false), 2000);
      return () => clearTimeout(t);
    }
  }, [agent.status]);

  // Auto-scroll reasoning to bottom while streaming
  useEffect(() => {
    if (expanded && reasoningRef.current) {
      reasoningRef.current.scrollTop = reasoningRef.current.scrollHeight;
    }
  }, [agent.reasoningText, expanded]);

  const elapsed = isActive && agent.startedAt
    ? (now - agent.startedAt) / 1000
    : agent.elapsed / 1000;

  // Tool label: strip the trailing ✓/✗ for cleaner display
  const toolLabel = agent.tool.replace(/\s[✓✗]$/, "");
  const toolOk = agent.tool.endsWith("✓");
  const toolFail = agent.tool.endsWith("✗");

  return (
    <div className={`rounded-card border ${agentBorder(idx)} overflow-hidden`}>
      {/* Agent header row */}
      <button
        type="button"
        onClick={() => hasReasoning && setExpanded(v => !v)}
        className={`w-full px-4 py-2.5 flex items-center gap-3 text-sm transition-colors ${
          hasReasoning ? "cursor-pointer hover:bg-muted/40" : "cursor-default"
        } ${agentBg(idx)}`}
      >
        {/* Chevron toggle */}
        <span className="shrink-0 w-3.5">
          {hasReasoning
            ? (expanded
              ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
              : <ChevronRight className="h-3 w-3 text-muted-foreground" />)
            : null
          }
        </span>

        {/* Agent name */}
        <span className={`font-mono text-xs font-semibold w-36 shrink-0 truncate text-left ${agentColor(idx)}`}>
          {agent.id}
        </span>

        {/* Status icon */}
        <StatusIcon status={agent.status} />

        {/* Tool badge */}
        {toolLabel ? (
          <span className={`inline-flex items-center gap-1 text-xs font-mono px-1.5 py-0.5 rounded bg-muted/60 min-w-0 truncate max-w-[140px] ${
            toolFail ? "text-destructive" : toolOk ? "text-success/80" : "text-muted-foreground"
          }`}>
            <Wrench className="h-2.5 w-2.5 shrink-0" />
            <span className="truncate">{toolLabel}</span>
          </span>
        ) : (
          <span className="w-[140px]" />
        )}

        {/* Iter count */}
        {agent.iters > 0 && (
          <span className="text-xs text-muted-foreground/60 tabular-nums shrink-0">
            {agent.iters} iter{agent.iters !== 1 ? "s" : ""}
          </span>
        )}

        {/* Elapsed time */}
        <span className="ml-auto text-xs text-muted-foreground/60 tabular-nums shrink-0 flex items-center gap-1">
          <Timer className="h-3 w-3" />
          {formatTime(elapsed)}
        </span>
      </button>

      {/* Streaming reasoning area */}
      {expanded && hasReasoning && (
        <div
          ref={reasoningRef}
          className="max-h-48 overflow-y-auto px-4 py-3 border-t border-border/40 bg-background/50 font-mono text-[11px] leading-relaxed text-muted-foreground whitespace-pre-wrap break-words"
        >
          {agent.reasoningText}
          {isActive && (
            <span className="inline-block w-1.5 h-3 bg-primary/70 animate-pulse ml-0.5 align-middle" />
          )}
        </div>
      )}
    </div>
  );
}

export function SwarmDashboard(props: SwarmDashboardProps) {
  const { preset, agents, agentOrder, finished, finalStatus, startTime, completedSummaries, finalReport } = props;
  const [now, setNow] = useState(Date.now());
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    timerRef.current = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timerRef.current);
  }, []);

  const elapsedTotal = (now - startTime) / 1000;
  const doneCount = Object.values(agents).filter(a => a.status === "done" || a.status === "failed").length;
  const totalCount = Math.max(agentOrder.length, 1);
  const pct = Math.round((doneCount / totalCount) * 100);
  const runningAgents = Object.values(agents).filter(a => a.status === "running" || a.status === "retry");

  const borderColor = finished
    ? (finalStatus === "completed" ? "border-success/50" : "border-destructive/50")
    : "border-primary/30";
  const headerBg = finished
    ? (finalStatus === "completed" ? "bg-success/10" : "bg-destructive/5")
    : "bg-primary/10";

  return (
    <div className="space-y-2 w-full">
      {/* Dashboard header */}
      <div className={`rounded-card border ${borderColor} overflow-hidden`}>
        <div className={`px-4 py-2.5 ${headerBg} flex items-center justify-between`}>
          <div className="flex items-center gap-2 min-w-0">
            {!finished && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />}
            <span className="font-semibold text-sm text-foreground truncate">{preset}</span>
            {finished ? (
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${
                finalStatus === "completed"
                  ? "bg-success/20 text-success"
                  : "bg-destructive/10 text-destructive"
              }`}>
                {finalStatus.toUpperCase()}
              </span>
            ) : (
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary font-medium shrink-0">
                {runningAgents.length > 0
                  ? `${runningAgents.map(a => a.id).join(", ")} running`
                  : "RUNNING"}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground shrink-0">
            <Timer className="h-3 w-3" />
            {formatTime(elapsedTotal)}
          </div>
        </div>

        {/* Progress bar */}
        <div className="px-4 py-2 border-t border-border/30 flex items-center gap-3">
          <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                finished
                  ? (finalStatus === "completed" ? "bg-success" : "bg-destructive")
                  : "bg-primary"
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground tabular-nums w-14 text-right shrink-0">
            {doneCount}/{totalCount} agents
          </span>
        </div>
      </div>

      {/* Agent cards */}
      {agentOrder.length > 0 && (
        <div className="space-y-1.5">
          {agentOrder.map((agentId, idx) => {
            const agent = agents[agentId];
            if (!agent) return null;
            return <AgentCard key={agentId} agent={agent} idx={idx} now={now} />;
          })}
        </div>
      )}

      {/* Completed agent summaries (collapsed previews) */}
      {completedSummaries.length > 0 && !finished && (
        <div className="space-y-1.5">
          {completedSummaries.map(({ agentId, summary }, idx) => {
            const agentIdx = agentOrder.indexOf(agentId);
            const colorIdx = agentIdx >= 0 ? agentIdx : idx;
            const lines = summary.split("\n");
            const preview = lines.slice(0, 6).join("\n") + (lines.length > 6 ? "\n…" : "");
            return (
              <div key={agentId + idx} className={`rounded-card ${agentBg(colorIdx)} px-4 py-3 border ${agentBorder(colorIdx)}`}>
                <div className={`text-xs font-semibold mb-1.5 ${agentColor(colorIdx)}`}>
                  {agentId} · summary
                </div>
                <div className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
                  {preview}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Final report */}
      {finalReport && (
        <div className="rounded-card border border-success/30 bg-success/5 px-5 py-4">
          <div className="text-xs font-semibold text-success mb-3">Final Report</div>
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{finalReport}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}

