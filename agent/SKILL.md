---
name: vibe-trading
description: Professional finance research toolkit — backtesting, factor analysis, options pricing, 64 finance skills, and 29 multi-agent swarm teams across 3 markets (A-shares, crypto, HK/US equities).
dependencies:
  python: ">=3.11"
  pip:
    - vibe-trading-ai
env:
  - name: TUSHARE_TOKEN
    description: "Tushare API token for China A-share data (optional — HK/US/crypto work without any key)"
    required: false
  - name: OPENAI_API_KEY
    description: "OpenAI-compatible API key — only needed for run_swarm (multi-agent teams). All other 15 tools work without it."
    required: false
  - name: LANGCHAIN_MODEL_NAME
    description: "LLM model name for run_swarm (e.g. deepseek/deepseek-v3.2). Only needed if using run_swarm."
    required: false
mcp:
  command: vibe-trading-mcp
  args: []
---

# Vibe-Trading

Professional finance research toolkit with AI-powered backtesting, multi-agent teams, and 64 specialized skills.

## Setup

```bash
pip install vibe-trading-ai
```

> **Repo-local development:** inside this repository, prefer the agent virtualenv explicitly:
>
> ```bash
> cd agent
> ./.venv/bin/python -m pip install -r requirements.txt
> ./.venv/bin/python cli.py
> ```
>
> Use `python -m pip`, not `pip`, so agent runs do not hit stale wrapper scripts.

> **Package name vs commands:** The PyPI package is `vibe-trading-ai`. Once installed, you get:
>
> | Command | Purpose |
> |---------|---------|
> | `vibe-trading` | Interactive CLI / TUI |
> | `vibe-trading serve` | Launch FastAPI web server |
> | `vibe-trading-mcp` | Start MCP server (for Claude Desktop, OpenClaw, Cursor, etc.) |

Add to your agent's MCP config:

```json
{
  "mcpServers": {
    "vibe-trading": {
      "command": "vibe-trading-mcp"
    }
  }
}
```

### API Key Requirements

**15 of 16 MCP tools work with zero API keys.** After `pip install`, backtesting, market data, factor analysis, options pricing, chart patterns, and all 64 skills are ready to use for HK/US equities and crypto.

| Feature | Key needed | When |
|---------|-----------|------|
| HK/US equities & crypto | None | Always free (yfinance + OKX) |
| China A-share data | `TUSHARE_TOKEN` | Only if you query A-share symbols |
| Multi-agent swarm (`run_swarm`) | `OPENAI_API_KEY` + `LANGCHAIN_MODEL_NAME` | Swarm spawns internal LLM workers |

## What You Can Do

### Backtesting
Create and run quantitative strategies across 3 markets:
- **HK/US equities** via yfinance (free, no API key)
- **Cryptocurrency** via OKX (free, no API key)
- **China A-shares** via Tushare (requires TUSHARE_TOKEN)

Example workflow:
1. Use `list_skills()` to discover strategy patterns
2. Use `load_skill("strategy-generate")` for the strategy creation guide
3. Call `setup_backtest_run(config_json=..., signal_engine_py=...)` — creates a timestamped run directory, writes `config.json` and `code/signal_engine.py`, and returns the `run_dir` path. **Always use this instead of writing files manually.**
4. Use `backtest(run_dir=...)` to run and get metrics (Sharpe, return, drawdown, etc.)

> **`setup_backtest_run` config_json required fields:** `source` ("auto"|"tushare"|"yfinance"|"okx"), `codes`, `start_date`, `end_date`, `initial_cash`.
> Symbol routing with `source="auto"`: `000001.SZ` / `000001.SH` → tushare; `AAPL.US` / `TSLA.US` → yfinance; `BTC-USDT` / `ETH-USDT` → okx.
> Optional: `optimizer` ("risk_parity"|"equal_weight"), `optimizer_params`, `commission`, `slippage`.
> In `signal_engine.py`, annotate with `pd.DataFrame` / `pd.Series` and `import pandas as pd`; do not import `DataFrame` or `Series` from `typing`.
> If `config.optimizer` is set, let the built-in optimizer handle sizing rather than re-implementing risk parity or equal-weight logic inside `SignalEngine`.

### Multi-Agent Swarm Teams
29 pre-built agent teams for complex research:
- **Investment Committee**: bull/bear debate → risk review → PM decision
- **Global Equities Desk**: A-share + HK/US + crypto → global strategist
- **Crypto Trading Desk**: funding/basis + liquidation + flow → risk manager
- **Earnings Research Desk**: fundamentals + revisions + options → earnings strategist
- **Macro/Rates/FX Desk**: rates + FX + commodities → macro PM
- **Quant Strategy Desk**: screening → factor research → backtest → risk audit
- **Risk Committee**: drawdown, tail risk, regime analysis
- And 22 more specialized teams

Use `list_swarm_presets()` to see all teams, then `run_swarm()` to execute.

### Finance Skills (64)
Comprehensive knowledge base covering:
- Technical analysis (candlestick, Elliott wave, Ichimoku, SMC)
- Quantitative methods (factor research, ML strategy, pair trading)
- Risk management (VaR/CVaR, stress testing, hedging)
- Options (Black-Scholes, Greeks, multi-leg strategies)
- HK/US equities (SEC filings, earnings revisions, ETF flows, ADR/H-share arbitrage)
- Crypto trading desk (funding rates, liquidation heatmaps, stablecoin flows, token unlocks, DeFi yields)
- Macro analysis, credit research, sector rotation, and more

Use `load_skill(name)` to access full methodology docs with code templates.

## Available MCP Tools (16)

| Tool | Description | API Key |
|------|-------------|---------|
| `list_skills` | List all 64 finance skills | None |
| `load_skill` | Load full skill documentation | None |
| `backtest` | Run vectorized backtest engine | None* |
| `factor_analysis` | IC/IR analysis + layered backtest | None* |
| `analyze_options` | Black-Scholes price + Greeks | None |
| `pattern_recognition` | Detect chart patterns (H&S, double top, etc.) | None |
| `get_market_data` | Fetch OHLCV data across 3 markets (auto-detect source) | None* |
| `read_url` | Fetch web page as Markdown | None |
| `read_document` | Extract text from PDF (with OCR) | None |
| `write_file` | Write files (config, strategy code) | None |
| `read_file` | Read file contents | None |
| `list_swarm_presets` | List multi-agent team presets | None |
| `run_swarm` | Execute a multi-agent research team | LLM key |
| `get_swarm_status` | Poll swarm run status without blocking | None |
| `get_run_result` | Get final report and task summaries | None |
| `list_runs` | List recent swarm runs with metadata | None |

<sub>*A-share symbols require `TUSHARE_TOKEN`. HK/US/crypto are free.</sub>

## Quick Start

```bash
pip install vibe-trading-ai
```

That's it — no API keys needed for HK/US/crypto markets. Start using `backtest`, `get_market_data`, `analyze_options`, and all 64 skills immediately.

## Examples

**Backtest a MACD strategy on Apple:**
> Backtest AAPL with MACD crossover strategy (fast=12, slow=26, signal=9) for 2024

**Run an investment committee review:**
> Use run_swarm with investment_committee preset to evaluate NVDA. Variables: target=NVDA.US, market=US

**Factor analysis on CSI 300:**
> Run factor_analysis on CSI 300 stocks using pe_ttm factor from 2023 to 2024

**Options analysis:**
> Use analyze_options: spot=100, strike=105, 90 days, vol=25%, rate=3%
