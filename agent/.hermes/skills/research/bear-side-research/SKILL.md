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

**Top Risk Bullets:** Extract top 3-5 most severe bearish signals

**Disproof Conditions:** List what would invalidate the bear thesis

## Output Format

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
```

## Common Pitfalls

1. **yfinance MultiIndex**: Always check `isinstance(df.columns, pd.MultiIndex)` and flatten with `df.columns = df.columns.get_level_values(0)` (more robust than `droplevel`)
2. **Series formatting in f-strings**: Pandas Series cannot be directly formatted — explicitly convert to float first: `float(df['Close'].iloc[-1])` not `df['Close'].iloc[-1]`
3. **File paths**: Use absolute paths or `.` for current directory, not nested paths that may not exist
4. **Sector benchmarks**: Use appropriate sector averages (tech ~22x P/E, utilities ~15x, etc.)
5. **GPD fitting**: Requires sufficient tail data (>10 exceedances); handle fit failures gracefully
6. **Beta calculation**: Align dates between stock and market returns before computing covariance
7. **Margin trends**: Distinguish between cyclical compression and structural deterioration
8. **Forward vs Trailing P/E**: Large gap implies aggressive growth expectations - any miss = multiple compression
9. **yfinance None values**: Use defensive pattern `info.get('field', 0) or 0` to handle both missing keys AND None values in one line
10. **Data availability**: yfinance may not provide all fundamental fields for all tickers — gracefully handle missing data with fallbacks or "N/A" messaging
11. **yfinance API changes**: Yahoo Finance occasionally changes response structure — always test data fetching separately before full analysis

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
