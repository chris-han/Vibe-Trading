---
name: bear-side-research
description: Systematic multi-dimensional bear-side stock research framework — technical, valuation, fundamental, and quantitative risk analysis for downside thesis building.
category: research
tags: [stocks, research, risk-analysis, valuation, technical-analysis]
---

# Bear-Side Stock Research Framework

## Purpose

Systematic multi-dimensional bear-side research methodology for identifying downside risks, valuation bubbles, and fundamental deterioration in individual stocks. Combines technical analysis, valuation assessment, fundamental trend analysis, and quantitative risk metrics into a comprehensive bear case.

## When to Use

- User requests bear-side research on a specific stock
- Need to identify downside risks before making investment decisions
- Conducting pre-trade risk assessment
- Building short thesis or hedging rationale
- Investment committee bear analyst role

## Six-Dimension Framework

| Dimension | Key Metrics | Bearish Signals |
|-----------|-------------|-----------------|
| **1. Technical** | RSI, Bollinger, EMA, ADX, Volume, Divergences | RSI >70, Price >95% BB Upper, EMA bearish crossover, Volume divergence, RSI/MACD divergences |
| **2. Valuation** | P/E, P/B, P/S, EV/EBITDA vs sector/historical | P/E premium >50% vs sector, P/B >3x historical, P/S >2x sector avg |
| **3. Fundamental** | Margin trends, Revenue growth, Balance sheet | Gross margin compression, Decelerating growth, Deteriorating cash flow |
| **4. Risk Metrics** | VaR, CVaR, Beta, Volatility, Drawdown | Beta >1.5, VaR(95%) >5%, Max DD >30%, Fat tails (kurtosis >4) |
| **5. Tail Risk** | GPD shape parameter, Monte Carlo worst cases | GPD ξ >0.5, Worst 5% scenario <-30% |
| **6. Catalysts** | Insider activity, Institutional flows, Competitive threats | Insider selling, Institutional reduction, Competitive share loss |

## Implementation Steps

### Step 1: Data Fetching (yfinance)

```python
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

ticker = yf.Ticker("SYMBOL")
end_date = datetime.now()
start_date = end_date - timedelta(days=730)  # 2 years for technical analysis

df = yf.download("SYMBOL", start=start_date.strftime("%Y-%m-%d"), 
                 end=end_date.strftime("%Y-%m-%d"), progress=False)

# Handle MultiIndex columns (yfinance quirk)
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.droplevel(1)

info = ticker.info  # Fundamental snapshot
financials = ticker.financials
quarterly_financials = ticker.quarterly_financials
balance_sheet = ticker.balance_sheet
cashflow = ticker.cashflow
```

### Step 2: Technical Analysis

```python
# RSI
delta = df['Close'].diff()
gain = (delta.where(delta > 0, 0)).ewm(span=14, adjust=False).mean()
loss = (-delta.where(delta < 0, 0)).ewm(span=14, adjust=False).mean()
df['RSI'] = 100 - (100 / (1 + gain/loss))

# Bollinger Bands
df['BB_Mid'] = df['Close'].rolling(20).mean()
df['BB_Std'] = df['Close'].rolling(20).std()
df['BB_Upper'] = df['BB_Mid'] + 2 * df['BB_Std']
df['BB_Lower'] = df['BB_Mid'] - 2 * df['BB_Std']

# EMA
df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()

# ADX
df['TR'] = np.maximum(df['High'] - df['Low'], 
                      np.maximum(abs(df['High'] - df['Close'].shift()), 
                                 abs(df['Low'] - df['Close'].shift())))
df['ATR'] = df['TR'].ewm(span=14, adjust=False).mean()
# ... (+DM/-DM → +DI/-DI → DX → ADX)

# Check divergences (price vs RSI/MACD/Volume)
```

**Bearish Signals to Flag:**
- RSI > 70 (overbought)
- Price > 95% of Bollinger Band range
- EMA12 < EMA26 (bearish crossover)
- ADX < 20 (weak trend, vulnerable)
- Volume declining on rallies (distribution)
- RSI/MACD making lower highs while price makes higher highs

### Step 3: Valuation Analysis

```python
pe_ttm = info.get('trailingPE')
pe_forward = info.get('forwardPE')
pb = info.get('priceToBook')
ps = info.get('priceToSalesTrailing12Months')
ev_ebitda = info.get('enterpriseToEbitda')
eps_ttm = info.get('trailingEps')

# Sector comparison (semiconductor avg: P/E ~22x, P/B ~5x)
sector_pe_avg = 22.0
fair_value = eps_ttm * sector_pe_avg
downside = (fair_value / current_price) - 1
```

**Bearish Signals to Flag:**
- P/E premium > 50% vs sector average
- P/B > 3x historical average
- P/S > 2x sector average
- Forward P/E << Trailing P/E (implies aggressive growth expectations)

### Step 4: Fundamental Deterioration

```python
# Gross margin trend
if 'Gross Profit' in financials.index and 'Total Revenue' in financials.index:
    gross_margins = financials.loc['Gross Profit'] / financials.loc['Total Revenue']
    # Check for compression: latest < previous
    
# Quarterly revenue trend
q_revenue = quarterly_financials.loc['Total Revenue']
# Check for deceleration
```

**Bearish Signals to Flag:**
- Gross margin compression (latest < previous by >100 bps)
- Revenue growth deceleration
- Operating margin peak
- Free cash flow declining despite revenue growth
- Insider selling activity
- Institutional ownership reduction

### Step 5: Risk Metrics

```python
returns = df['Close'].pct_change().dropna()

# Volatility
daily_vol = returns.std()
annual_vol = daily_vol * np.sqrt(252)

# VaR (Historical)
var_95 = -returns.quantile(0.05)
var_99 = -returns.quantile(0.01)

# CVaR / Expected Shortfall
cvar_95 = -returns[returns < -var_95].mean()

# Beta vs market
spy_df = yf.download("^GSPC", start=start_date, end=end_date, progress=False)
spy_ret = spy_df['Close'].pct_change().dropna()
common = returns.index.intersection(spy_ret.index)
beta = np.cov(returns.loc[common], spy_ret.loc[common])[0,1] / np.var(spy_ret.loc[common])

# Drawdown
cumulative = (1 + returns).cumprod()
drawdown = (cumulative - cumulative.cummax()) / cumulative.cummax()
max_dd = drawdown.min()

# Tail risk (GPD)
from scipy.stats import genpareto
threshold = returns.quantile(0.05)
exceedances = threshold - returns[returns < threshold]
shape, loc, scale = genpareto.fit(exceedances)  # ξ > 0 = fat tail
```

**Bearish Signals to Flag:**
- Beta > 1.5 (high market sensitivity)
- Annual volatility > 40%
- VaR(95%) > 5% daily
- Max drawdown > 30%
- GPD shape parameter ξ > 0.5 (fat tail)
- Kurtosis > 4

### Step 6: Monte Carlo Simulation

```python
np.random.seed(42)
n_paths = 10000
n_days = 252
S0 = current_price
mu_annual = returns.mean() * 252
sigma_annual = returns.std() * np.sqrt(252)

dt = 1/252
Z = np.random.standard_normal((n_paths, n_days))
log_returns = (mu_annual - 0.5 * sigma_annual**2) * dt + sigma_annual * np.sqrt(dt) * Z
prices = S0 * np.exp(np.cumsum(log_returns, axis=1))

final_returns = prices[:, -1] / S0 - 1
worst_5pct = np.percentile(final_returns, 5)
worst_1pct = np.percentile(final_returns, 1)
```

### Step 7: Synthesis

**Bear Target Prices:**
1. Sector P/E mean reversion: `EPS × sector_pe_avg`
2. Historical P/E mean reversion: `EPS × historical_pe_avg`
3. 52-week low
4. Monte Carlo worst 5% scenario
5. Stress scenario (-40% from current)

**Top Risk Bullets:** Extract top 3-5 most severe bearish signals with severity ratings (HIGH/MEDIUM/LOW)

**Disproof Conditions:** List what would invalidate the bear thesis with specific thresholds

**Confidence Scoring:**
- Count total bearish signals triggered across all 6 dimensions
- HIGH confidence: ≥10 signals
- MEDIUM confidence: 6-9 signals
- LOW confidence: <6 signals

**Actionable Recommendations:**
- For long holders: trim levels, protective put strikes, stop-loss
- For short sellers: entry zone, stop-loss, price targets
- For options traders: spread structures, overwriting strategies

## Output Format

**Artifact Path Rule:**
- Never hardcode `/app/agent/...`, `agent/...`, or any absolute output path.
- If you save helper artifacts, use runtime-relative paths only so Hermes keeps them under the active task/session artifact directory.

```markdown
# [STOCK] BEAR-SIDE RESEARCH REPORT

## Top Bear Risk Bullets
| Risk | Severity | Evidence |
|------|----------|----------|
| ... | ... | ... |

## Technical Breakdown
[Indicators and signals]

## Valuation Bubble Assessment
[Multiple comparison vs sector/historical]

## Fundamental Deterioration
[Margin trends, growth deceleration]

## Risk Metrics
[VaR, CVaR, Beta, Drawdown, Tail risk]

## Bear Target Prices
| Target | Price | Downside | Rationale |
|--------|-------|----------|-----------|
| ... | ... | ... | ... |

## What Would Disprove Bear Case
[Conditions that would invalidate thesis]

## 操作策略 / Action Plan
- ✅ Use emoji-led Markdown bullets for trim zone, hedge zone, short entry zone, stop loss, and downside targets; or
- 📋 Use a Markdown pipe-table with columns such as `Scenario | Trigger | Action | Target | Risk Control`
- Make Markdown the default for this section. Keep it as standard bullets or a pipe-table, not as a separate visual layout.
```

## Common Pitfalls

1. **yfinance MultiIndex (2025+)**: Yahoo Finance now returns MultiIndex columns. Always check and flatten:
   ```python
   if isinstance(df.columns, pd.MultiIndex):
       df.columns = df.columns.droplevel(1)  # Remove ticker level, keeps metric names
   ```
2. **Series formatting in f-strings**: Pandas Series cannot be directly formatted — explicitly convert to float first: `float(df['Close'].iloc[-1])` not `df['Close'].iloc[-1]`
3. **File paths**: Use absolute paths or `.` for current directory, not nested paths that may not exist. In swarm contexts, write to `artifacts/<agent_name>/` subdirectory.
4. **Beta calculation failures**: Covariance/correlation can fail with dimensionality errors. Wrap in try/except and use defensive checks:
   ```python
   try:
       beta = aligned_returns['NVDA'].cov(aligned_returns['SPY']) / aligned_returns['SPY'].var()
   except Exception:
       beta = None  # Handle gracefully
   # Later: if beta is not None and beta > 1.5: ...
   ```
5. **yfinance financials iteration**: `quarterly_financials.loc['Total Revenue']` returns a Series with dates as index — iterate over `series.items()` or `list(series.index)`, NOT `series.columns`
4. **Sector benchmarks**: Use appropriate sector averages (tech ~22x P/E, utilities ~15x, etc.)
5. **GPD fitting**: Requires sufficient tail data (>10 exceedances); handle fit failures gracefully
6. **Beta calculation**: Align dates between stock and market returns before computing covariance
7. **Margin trends**: Distinguish between cyclical compression and structural deterioration
8. **Forward vs Trailing P/E**: Large gap implies aggressive growth expectations - any miss = multiple compression
9. **yfinance None values**: Use defensive pattern `info.get('field', 0) or 0` to handle both missing keys AND None values in one line
10. **Data availability**: yfinance may not provide all fundamental fields for all tickers — gracefully handle missing data with fallbacks or "N/A" messaging
11. **yfinance API changes**: Yahoo Finance occasionally changes response structure — always test data fetching separately before full analysis
12. **Insider transactions column names**: Use `'Transaction Start Date'` not `'Transaction Date'`; wrap in try/except as structure varies
13. **Major holders parsing**: Values are numpy.float64, not strings — don't call `.replace()` on them; access via `.iloc[row, col]`
14. **Earnings history columns**: Use `'epsEstimate'` and `'epsActual'` (lowercase), not `'EPS Estimate'`
15. **Institutional holders change**: Column `'Change in Shares'` may be missing — check with `if 'Change in Shares' in df.columns`
16. **yfinance earnings can be None**: `ticker.earnings` may return `None` (not just empty DataFrame) — check `if earnings is not None and not earnings.empty`
17. **Quarterly financials iteration**: After `.loc['Total Revenue']`, result is a Series with dates as index — iterate over `list(revenue.index)` not `revenue.columns`
19. **Institutional holders column variations**: Column name may be `'% Out'` or `'Pct Out'` — use `row.get('% Out', row.get('Pct Out', 0))`
20. **Insider transactions returning N/A**: yfinance sometimes returns all 'N/A' values for insider data — this is a Yahoo limitation, not a bug
21. **yfinance financials structure**: `quarterly_financials` and `financials` are DataFrames with metrics as rows and dates as columns — access via `.loc['Metric Name']`
22. **yfinance abbreviated columns**: Recent yfinance versions may return abbreviated column names (`C`, `H`, `L`, `O`, `V`) — rename after fetching: `df = df.rename(columns={'C': 'Close', 'H': 'High', 'L': 'Low', 'O': 'Open', 'V': 'Volume'})`
23. **Complete column handling pattern**: Combine MultiIndex flattening + column renaming in one block:
```python
if isinstance(df.columns, pd.MultiIndex):
    df = df.droplevel(1, axis=1)
    df.columns = [col[0] for col in df.columns]
column_map = {'C': 'Close', 'H': 'High', 'L': 'Low', 'O': 'Open', 'V': 'Volume'}
if 'C' in df.columns:
    df = df.rename(columns=column_map)
```
24. **Revenue growth iteration**: When iterating quarterly revenue for growth calculation, use `revenue.pct_change()` on the Series directly — don't try to iterate over columns
25. **Earnings can be None**: `ticker.earnings` may return `None` (not just empty DataFrame) — check `if earnings is not None and not earnings.empty`

## Enhanced Analysis: Insider & Institutional Flows

Add this section for catalyst identification:

```python
# Insider Transactions
insider = ticker.insider_transactions
if insider is not None and len(insider) > 0:
    recent_6m = insider[insider['Transaction Start Date'] >= (datetime.now() - timedelta(days=180))]
    buys = len(recent_6m[recent_6m['Shares'] > 0])
    sells = len(recent_6m[recent_6m['Shares'] < 0])
    # Bearish if sells > buys * 2

# Institutional Holders
institutions = ticker.institutional_holders
if institutions is not None:
    if 'Change in Shares' in institutions.columns:
        net_change = institutions['Change in Shares'].sum()
        # Bearish if net_change < 0 (reduction)

# Options Sentiment (Put/Call Ratio)
options = ticker.options
if options and len(options) > 0:
    opt_chain = ticker.option_chain(options[0])
    put_call_ratio = opt_chain.puts['openInterest'].sum() / opt_chain.calls['openInterest'].sum()
    # Bearish if > 1.2 (hedging or speculative puts)
```

## Enhanced Output Format (with Severity & Actions)

```markdown
## Top Bear Risk Bullets
| Risk | Severity | Evidence |
|------|----------|----------|
| Valuation Bubble | HIGH | P/E 76% premium to sector |
| Technical Overextension | HIGH | RSI 74.9, Bollinger 96.4% |
| Margin Compression | MEDIUM | Gross margin -3.9pp |
| Fat Tail Risk | HIGH | GPD ξ=1.03, kurtosis 4.74 |
| Insider Selling | MEDIUM | $100M+ sales in recent month |

## Recommended Actions

### For Long Holders
- Trim position at resistance zone
- Buy protective puts: strike X, expiry Y
- Set stop-loss: $Z (below critical support)

### For Short Sellers
- Entry zone: $A-$B (near resistance)
- Stop-loss: $C (above 52W high)
- Targets: $D (-30%), $E (-50%)

### Bear Case Confidence: HIGH/MEDIUM/LOW
Signal Count: N/15 indicators triggered

> Format rule: keep `## Recommended Actions` and any `## 操作策略` section in normal Markdown, using bullets or pipe-tables as the default presentation.
```

## Dependencies

```bash
pip install yfinance pandas numpy scipy
```

## Example Usage

```python
# See nvda_bear_analysis.py for full implementation
# Run: python3 bear_research.py TICKER
```

## Related Skills

- `risk-analysis`: Deeper VaR/CVaR/Monte Carlo methodology
- `technical-basic`: Technical indicator calculations
- `fundamental-filter`: Fundamental screening logic
- `yfinance`: Data fetching patterns and quirks
