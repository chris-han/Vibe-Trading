import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { ArrowRight, ArrowUpRight, BarChart3, Bot, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { api, type AuthMeData } from "@/lib/api";

const DESK_SIGNALS = [
  {
    label: "Coverage",
    value: "A-Share, HK/US, Crypto",
    detail: "One research brief can move across markets without changing workflow.",
  },
  {
    label: "Outputs",
    value: "Code, backtest, report",
    detail: "Each run produces artifacts you can inspect, compare, and export.",
  },
  {
    label: "Execution",
    value: "Single agent or swarm",
    detail: "Start narrow, then escalate to a coordinated team when the problem widens.",
  },
];

const DESK_FLOW = [
  {
    title: "Write the brief",
    detail: "Describe the market, the logic, and the evaluation window in plain language.",
  },
  {
    title: "Watch the agent build",
    detail: "The workspace streams reasoning, tool calls, generated code, and backtest progress live.",
  },
  {
    title: "Keep only what survives review",
    detail: "Inspect metrics, compare runs, and push promising ideas into deeper research threads.",
  },
];

export function Home() {
  const { t } = useI18n();
  const [auth, setAuth] = useState<AuthMeData | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getAuthMe().then((data) => {
      if (!cancelled) setAuth(data);
    }).catch(() => {
      if (!cancelled) setAuth({ authenticated: false });
    });
    return () => { cancelled = true; };
  }, []);

  const FEATURES = [
    { icon: Bot, title: t.feat1, desc: t.feat1d },
    { icon: BarChart3, title: t.feat2, desc: t.feat2d },
    { icon: Zap, title: t.feat3, desc: t.feat3d },
  ];

  return (
    <div className="min-h-full bg-background">
      <section className="relative overflow-hidden border-b border-border/70">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.22),transparent_28%),radial-gradient(circle_at_82%_18%,hsl(var(--muted-foreground)/0.10),transparent_24%)]" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-6 py-16 md:px-8 md:py-20 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)] xl:items-end">
          <div className="space-y-8">
            <div className="space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/80 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground shadow-sm">
                <Sparkles className="h-3.5 w-3.5" />
                Quant Research Desk
              </div>
              <div className="space-y-4">
                <h1 className="text-hero max-w-4xl text-foreground">{t.heroTitle}</h1>
                <p className="max-w-2xl text-subhead text-muted-foreground">{t.heroDesc}</p>
              </div>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              {auth?.authenticated ? (
                <Link
                  to="/agent"
                  className="inline-flex items-center justify-center gap-2 rounded-button bg-primary px-5 py-3 text-sm font-medium text-primary-foreground transition-transform hover:scale-105 hover:bg-primary/90 active:scale-95"
                >
                  {t.startResearch}
                  <ArrowRight className="h-4 w-4" />
                </Link>
              ) : (
                <a
                  href={api.feishuLoginUrl()}
                  className="inline-flex items-center justify-center gap-2 rounded-button bg-primary px-5 py-3 text-sm font-medium text-primary-foreground transition-transform hover:scale-105 hover:bg-primary/90 active:scale-95"
                >
                  Sign in with Feishu
                  <ArrowRight className="h-4 w-4" />
                </a>
              )}
              <Link
                to="/compare"
                className="inline-flex items-center justify-center gap-2 rounded-button border border-border bg-background/85 px-5 py-3 text-sm font-medium text-foreground transition-colors hover:bg-muted"
              >
                Compare Runs
                <ArrowUpRight className="h-4 w-4" />
              </Link>
            </div>

            {auth?.authenticated && auth.user && (
              <p className="text-sm text-muted-foreground">
                Workspace <span className="font-medium text-foreground">{auth.user.workspace_slug}</span> is ready for new research threads.
              </p>
            )}

            <div className="grid gap-3 md:grid-cols-3">
              {DESK_SIGNALS.map((signal) => (
                <div key={signal.label} className="rounded-card border border-border/80 bg-card/85 p-4 shadow-sm backdrop-blur-sm">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{signal.label}</div>
                  <div className="mt-2 text-base font-semibold text-foreground">{signal.value}</div>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{signal.detail}</p>
                </div>
              ))}
            </div>
          </div>

          <aside className="rounded-hero border border-border/80 bg-card/88 p-6 shadow-sm backdrop-blur-sm md:p-7">
            <div className="space-y-6">
              <div className="space-y-2">
                <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Research system</div>
                <h2 className="text-headline text-foreground">One prompt turns into a full trading research loop.</h2>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  The workspace is built for strategy generation, backtest execution, document review, and iterative refinement without context switching.
                </p>
              </div>

              <div className="rounded-section bg-primary p-5 text-primary-foreground">
                <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-primary-foreground/80">Featured brief</div>
                <p className="mt-3 text-lg font-semibold leading-tight">
                  Build a cross-market portfolio, run the backtest, and explain where the edge actually comes from.
                </p>
                <div className="mt-4 inline-flex items-center gap-2 rounded-button bg-primary-foreground/10 px-3 py-1.5 text-xs font-medium text-primary-foreground">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Output includes metrics, trades, and a reviewable report
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
                <div className="rounded-card border border-border bg-background/85 p-4">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Live desk</div>
                  <div className="mt-2 text-base font-semibold text-foreground">Streaming reasoning and tool traces</div>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    Follow code generation, data access, and backtest progress in real time while the run is happening.
                  </p>
                </div>
                <div className="rounded-card border border-border bg-background/85 p-4">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Review surface</div>
                  <div className="mt-2 text-base font-semibold text-foreground">Compare outcomes before you trust them</div>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    Keep multiple runs, inspect deltas, and promote only the ideas that hold up under comparison.
                  </p>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 py-16 md:px-8 md:py-20">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
          <article className="rounded-section border border-border/80 bg-card p-8 shadow-sm md:p-10">
            <div className="max-w-2xl space-y-4">
              <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Research flow</div>
              <h2 className="text-section text-foreground">Fewer dashboards. More decisions that survive scrutiny.</h2>
              <p className="text-base leading-relaxed text-muted-foreground">
                The product should feel like a disciplined desk, not a gallery of disconnected tools. Each stage is there to eliminate weak ideas quickly.
              </p>
            </div>

            <div className="mt-8 grid gap-4 md:grid-cols-3">
              {DESK_FLOW.map((step, index) => (
                <div key={step.title} className="rounded-card border border-border bg-background/80 p-4">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">0{index + 1}</div>
                  <h3 className="mt-3 text-lg font-semibold text-foreground">{step.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{step.detail}</p>
                </div>
              ))}
            </div>
          </article>

          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-1">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <article key={title} className="rounded-section border border-border/80 bg-card p-6 shadow-sm">
                <div className="flex h-11 w-11 items-center justify-center rounded-button bg-primary text-primary-foreground">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="mt-5 text-headline text-foreground">{title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{desc}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
