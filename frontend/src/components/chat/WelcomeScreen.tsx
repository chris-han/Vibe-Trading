import { useEffect, useState } from "react";
import { ArrowRight, Bot, Globe, Sparkles, TrendingUp, Users } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface Example {
  title: string;
  desc: string;
  prompt: string;
}

interface Category {
  label: string;
  icon: React.ReactNode;
  examples: Example[];
}

const CATEGORIES: Category[] = [
  {
    label: "Multi-Market Backtest",
    icon: <TrendingUp className="h-4 w-4" />,
    examples: [
      {
        title: "Cross-Market Portfolio",
        desc: "A-shares + crypto + US equities with risk-parity optimizer",
        prompt: "Backtest a risk-parity portfolio of MSFT, BTC-USDT, and AAPL for full-year 2025, compare against equal-weight baseline",
      },
      {
        title: "BTC 5-Min MACD Strategy",
        desc: "Minute-level crypto backtest with real-time OKX data",
        prompt: "Backtest BTC-USDT 5-minute MACD strategy, fast=12 slow=26 signal=9, last 30 days",
      },
      {
        title: "US Tech Max Diversification",
        desc: "Portfolio optimizer across FAANG+ via yfinance",
        prompt: "Backtest AAPL, MSFT, GOOGL, AMZN, NVDA with max_diversification portfolio optimizer, full-year 2024",
      },
    ],
  },
  {
    label: "Research & Analysis",
    icon: <Sparkles className="h-4 w-4" />,
    examples: [
      {
        title: "Multi-Factor Alpha Model",
        desc: "IC-weighted factor synthesis across 300 stocks",
        prompt: "Build a multi-factor alpha model using momentum, reversal, volatility, and turnover on CSI 300 constituents with IC-weighted factor synthesis, backtest 2023-2024",
      },
      {
        title: "Options Greeks Analysis",
        desc: "Black-Scholes pricing with Delta/Gamma/Theta/Vega",
        prompt: "Calculate option Greeks using Black-Scholes: spot=100, strike=105, risk-free rate=3%, vol=25%, expiry=90 days, analyze Delta/Gamma/Theta/Vega",
      },
    ],
  },
  {
    label: "Swarm Teams",
    icon: <Users className="h-4 w-4" />,
    examples: [
      {
        title: "Investment Committee Review",
        desc: "Multi-agent debate: long vs short, risk review, PM decision",
        prompt: "[Swarm Team Mode] Use the investment_committee preset to evaluate whether to go long or short on NVDA given current market conditions. Variables: target=NVDA, market=US",
      },
      {
        title: "Quant Strategy Desk",
        desc: "Screening → factor research → backtest → risk audit pipeline",
        prompt: "[Swarm Team Mode] Use the quant_strategy_desk preset to find and backtest the best momentum strategy on CSI 300 constituents. Variables: market=A-shares, goal=momentum strategy on CSI 300 constituents",
      },
    ],
  },
  {
    label: "Document & Web Research",
    icon: <Globe className="h-4 w-4" />,
    examples: [
      {
        title: "Analyze an Earnings Report",
        desc: "Upload a document and ask questions about the financials",
        prompt: "Summarize the key financial metrics, risks, and outlook from the uploaded earnings report",
      },
      {
        title: "Web Research: Macro Outlook",
        desc: "Read live web sources for macro analysis",
        prompt: "Read the latest Fed meeting minutes and summarize the key takeaways for equity and crypto markets",
      },
    ],
  },
];

const CAPABILITY_CARDS = [
  { label: "Markets", value: "A-Share, HK/US, Crypto" },
  { label: "Modes", value: "Single agent and swarm presets" },
  { label: "Outputs", value: "Code, runs, metrics, reports" },
];

interface Props {
  onExampleSelect: (s: string) => void;
}

const SHORT_VIEWPORT_HEIGHT = 760;

export function WelcomeScreen({ onExampleSelect }: Props) {
  const { t } = useI18n();
  const [isShortViewport, setIsShortViewport] = useState(false);
  const [showAllCategories, setShowAllCategories] = useState(false);

  useEffect(() => {
    const syncViewportHeight = () => {
      const shortViewport = window.innerHeight < SHORT_VIEWPORT_HEIGHT;
      setIsShortViewport(shortViewport);
      if (!shortViewport) {
        setShowAllCategories(false);
      }
    };

    syncViewportHeight();
    window.addEventListener("resize", syncViewportHeight, { passive: true });
    return () => window.removeEventListener("resize", syncViewportHeight);
  }, []);

  const visibleCategories = isShortViewport && !showAllCategories ? CATEGORIES.slice(0, 2) : CATEGORIES;
  const [featuredCategory, ...secondaryCategories] = visibleCategories;
  const featuredPrimary = featuredCategory.examples[0];
  const featuredSecondary = featuredCategory.examples[1];

  return (
    <div className="flex min-h-full flex-col justify-center py-3 md:py-6">
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)] lg:items-stretch">
          <section className="rounded-hero border border-border/80 bg-card p-6 shadow-sm md:p-8">
            <div className="space-y-6">
              <div className="space-y-4">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-button bg-primary shadow-sm lg:mx-0">
                  <img src="/logo-wireframe.svg" alt="semantier logo" className="block h-14 w-14 object-contain object-center" />
                </div>
                <div className="inline-flex items-center gap-2 rounded-full border border-border bg-background/70 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  <Bot className="h-3.5 w-3.5" />
                  Research workspace
                </div>
                <div className="space-y-3">
                  <h2 className="text-section max-w-xl text-foreground">Start with a brief. Keep only the ideas that hold up.</h2>
                  <p className="max-w-xl text-subhead text-muted-foreground">vibe trading with your professional financial agent team</p>
                  <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">{t.describeStrategy}</p>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                {CAPABILITY_CARDS.map((card) => (
                  <div key={card.label} className="rounded-card border border-border bg-background/80 p-4">
                    <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{card.label}</div>
                    <div className="mt-2 text-sm font-semibold text-foreground">{card.value}</div>
                  </div>
                ))}
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                {[featuredPrimary, featuredSecondary].map((example, index) => (
                  <button
                    key={example.title}
                    type="button"
                    onClick={() => onExampleSelect(example.prompt)}
                    className={index === 0
                      ? "rounded-section bg-primary p-5 text-left text-primary-foreground transition-transform hover:scale-[1.01]"
                      : "rounded-section border border-border bg-background/80 p-5 text-left transition-colors hover:border-primary/50 hover:bg-muted/35"
                    }
                  >
                    <div className={index === 0 ? "text-[11px] font-medium uppercase tracking-[0.18em] text-primary-foreground/80" : "text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground"}>
                      {index === 0 ? "Featured prompt" : "Fast start"}
                    </div>
                    <div className={index === 0 ? "mt-3 text-lg font-semibold leading-tight" : "mt-3 text-base font-semibold leading-tight text-foreground"}>
                      {example.title}
                    </div>
                    <p className={index === 0 ? "mt-2 text-sm leading-relaxed text-primary-foreground/80" : "mt-2 text-sm leading-relaxed text-muted-foreground"}>
                      {example.desc}
                    </p>
                    <div className={index === 0 ? "mt-4 inline-flex items-center gap-2 rounded-button bg-primary-foreground/10 px-3 py-1.5 text-xs font-medium text-primary-foreground" : "mt-4 inline-flex items-center gap-2 rounded-button border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground"}>
                      Load prompt
                      <ArrowRight className="h-3.5 w-3.5" />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="rounded-hero border border-border/80 bg-card p-6 shadow-sm md:p-8">
            <div className="space-y-5">
              <div className="space-y-2">
                <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{t.examples}</div>
                <h3 className="text-headline text-foreground">Choose a lane, then let the workspace open the right tools.</h3>
              </div>

              <button
                type="button"
                onClick={() => onExampleSelect(featuredPrimary.prompt)}
                className="block w-full rounded-section border border-border bg-background/80 p-5 text-left transition-colors hover:border-primary/50 hover:bg-muted/35"
              >
                <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  {featuredCategory.icon}
                  {featuredCategory.label}
                </div>
                <div className="mt-4 text-lg font-semibold leading-tight text-foreground">{featuredPrimary.title}</div>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{featuredPrimary.desc}</p>
              </button>

              <div className="grid gap-3 sm:grid-cols-2">
                {secondaryCategories.map((category) => {
                  const example = category.examples[0];
                  return (
                    <button
                      key={category.label}
                      type="button"
                      onClick={() => onExampleSelect(example.prompt)}
                      className="block rounded-card border border-border bg-background/80 p-4 text-left transition-colors hover:border-primary/50 hover:bg-muted/35"
                    >
                      <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                        {category.icon}
                        {category.label}
                      </div>
                      <div className="mt-3 text-sm font-semibold leading-snug text-foreground">{example.title}</div>
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{example.desc}</p>
                    </button>
                  );
                })}
              </div>

              {isShortViewport && !showAllCategories && (
                <button
                  type="button"
                  onClick={() => setShowAllCategories(true)}
                  className="rounded-button border border-border bg-background px-3 py-2 text-sm text-foreground transition-colors hover:bg-muted"
                >
                  Show more examples
                </button>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

