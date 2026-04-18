import { useEffect, useState } from "react";
import { Bot, TrendingUp, Bitcoin, Globe, Sparkles, Users } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface Example {
  title: string;
  desc: string;
  prompt: string;
}

interface Category {
  label: string;
  icon: React.ReactNode;
  color: string;
  examples: Example[];
}

const CATEGORIES: Category[] = [
  {
    label: "Multi-Market Backtest",
    icon: <TrendingUp className="h-4 w-4" />,
    color: "text-red-400 border-red-500/30 hover:border-red-500/60 hover:bg-red-500/5",
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
    color: "text-amber-400 border-amber-500/30 hover:border-amber-500/60 hover:bg-amber-500/5",
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
    color: "text-violet-400 border-violet-500/30 hover:border-violet-500/60 hover:bg-violet-500/5",
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
    color: "text-blue-400 border-blue-500/30 hover:border-blue-500/60 hover:bg-blue-500/5",
    examples: [
      {
        title: "Analyze an Earnings Report PDF",
        desc: "Upload a PDF and ask questions about the financials",
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

const CAPABILITY_CHIPS = [
  "56 Finance Skills",
  "25 Swarm Presets",
  "19 Agent Tools",
  "3 Markets: A-Share · Crypto · HK/US",
  "Minute to Daily Timeframes",
  "4 Portfolio Optimizers",
  "15+ Risk Metrics",
  "Options & Derivatives",
  "PDF & Web Research",
  "Factor Analysis & ML",
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

  return (
    <div className="flex min-h-full flex-col items-center justify-start gap-4 py-4 text-center md:gap-5 md:py-5">
      {/* Header */}
      <div className="space-y-2">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-button bg-primary shadow-sm">
          <img src="/logo-wireframe.svg" alt="semantier logo" className="block h-14 w-14 object-contain object-center" />
        </div>
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground md:text-2xl">semantier</h2>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto leading-relaxed">
            vibe trading with your professional financial agent team
          </p>
          <p className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-muted-foreground">
            {t.describeStrategy}
          </p>
        </div>
      </div>

      {/* Capability chips */}
      <div className="flex max-w-3xl flex-wrap justify-center gap-1.5">
        {CAPABILITY_CHIPS.map((chip) => (
          <span
            key={chip}
            className="rounded-full border border-border bg-muted/50 px-2.5 py-0.5 text-[11px] text-muted-foreground"
          >
            {chip}
          </span>
        ))}
      </div>

      {/* Example categories grid */}
      <div className="w-full max-w-4xl space-y-2.5 text-left">
        <p className="text-xs text-muted-foreground px-1">{t.examples}</p>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {visibleCategories.map((cat) => (
            <div key={cat.label} className="space-y-1.5">
              <div className={`flex items-center gap-1.5 px-1 text-[11px] font-medium ${cat.color.split(" ").filter(c => c.startsWith("text-")).join(" ")}`}>
                {cat.icon}
                <span>{cat.label}</span>
              </div>
              <div className="space-y-1.5">
                {cat.examples.map((ex) => (
                  <button
                    key={ex.title}
                    onClick={() => onExampleSelect(ex.prompt)}
                    className={`block w-full rounded-button border bg-card px-3 py-1.5 text-left transition-colors hover:shadow-sm ${cat.color}`}
                  >
                    <span className="text-[13px] font-medium leading-snug text-foreground md:text-sm">
                      {ex.title}
                    </span>
                    <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground md:text-xs">
                      {ex.desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
        {isShortViewport && !showAllCategories && (
          <div className="flex justify-center pt-1">
            <button
              type="button"
              onClick={() => setShowAllCategories(true)}
              className="rounded-full border border-border bg-background px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              Show more examples
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

