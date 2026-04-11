---
name: detailed-risk-analysis
description: Perform detailed risk analysis involving data fetching, cleaning, volatility calculation, VaR, maximum drawdown analysis, and ensuring compatibility of the output for JSON serialization.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Risk, Analysis, Volatility, VaR, Drawdown]
    related_skills: [data-cleaning, risk-analysis]
---

# Detailed Risk Analysis

## Data Fetching and Cleaning

### Fetch Financial Data for NVDA
```python
import yfinance as yf
import pandas as pd
import json

def fetch_nvda_data():
    # Define the ticker symbol
    ticker = 'NVDA'

    # Fetch historical data for the past 5 years
    data = yf.download(ticker, start='2021-01-01', end='2026-03-30', progress=False)
    data.to_csv('nvda_data.csv')

    # Fetch additional company information
    nvda = yf.Ticker(ticker)
    info = nvda.info
    financials = nvda.financials
    balance_sheet = nvda.balance_sheet
    cashflow = nvda.cashflow

    # Save the additional company information to JSON files
    with open('nvda_info.json', 'w') as f:
        json.dump(info, f)
    with open('nvda_financials.json', 'w') as f:
        financials.T.to_json(f)
    with open('nvda_balance_sheet.json', 'w') as f:
        balance_sheet.T.to_json(f)
    with open('nvda_cashflow.json', 'w') as f:
        cashflow.T.to_json(f)
```

### Cleaning and Analysis

#### Pitfall: yfinance MultiIndex Columns

**CRITICAL:** yfinance now returns MultiIndex columns (e.g., `('Close', 'NVDA')`). You MUST flatten them before accessing:

```python
# After yf.download(), flatten MultiIndex columns
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
```

If you skip this, `float(df['Close'].iloc[-1])` throws `TypeError: float() argument must be a string or a real number, not 'Series'`.

### Load Historical Data

```python
import pandas as pd
import numpy as np
from scipy.stats import norm
import json

# Load historical data
data = pd.read_csv('nvda_data.csv', skiprows=3, index_col=0, parse_dates=True)

# Correct column names if needed
if len(data.columns) == 6:
    data.columns = ['Adj Close', 'Close', 'High', 'Low', 'Open', 'Volume']
elif len(data.columns) == 5:
    data.columns = ['Close', 'High', 'Low', 'Open', 'Volume']

# Use 'Adj Close' if present, else 'Close'
column_to_use = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
returns = data[column_to_use].pct_change().dropna()
```

### Volatility Calculation
```python
# Calculate historical volatility
hv_20 = returns.rolling(window=20).std() * np.sqrt(252)
hv_60 = returns.rolling(window=60).std() * np.sqrt(252)
```

### Value-at-Risk (VaR)
```python
# Calculate VaR using historical and parametric methods

def historical_var(returns, confidence=0.95, horizon=1):
    sorted_returns = returns.sort_values()
    index = int((1 - confidence) * len(sorted_returns))
    var_1d = -sorted_returns.iloc[index]
    return var_1d * np.sqrt(horizon)

def parametric_var(returns, confidence=0.95, horizon=1):
    mu = returns.mean()
    sigma = returns.std()
    z = norm.ppf(1 - confidence)
    var_1d = -(mu + z * sigma)
    return var_1d * np.sqrt(horizon)

var_historical = historical_var(returns)
var_parametric = parametric_var(returns)
```

### CVaR (Conditional VaR / Expected Shortfall)

CVaR measures the average loss beyond VaR—more conservative than VaR and captures fat tail risk.

```python
def historical_cvar(returns, confidence=0.95):
    """Average loss in the worst (1-confidence)% of cases."""
    var = historical_var(returns, confidence)
    tail_losses = returns[returns < -var]
    return -tail_losses.mean() if len(tail_losses) > 0 else var

cvar_95 = historical_cvar(returns, 0.95)

# Fat tail indicator: CVaR/VaR ratio > 1.5 indicates significant tail risk
tail_risk_ratio = cvar_95 / var_historical
print(f"CVaR/VaR Ratio: {tail_risk_ratio:.2f}x (>1.5 = fat tail risk)")
```

### Tail Risk Metrics

```python
# Distribution characteristics
skewness = returns.skew()  # <0 = left-skewed (more downside)
kurtosis = returns.kurtosis()  # >3 = fat tails

# Tail ratio: worst 5% vs best 5%
worst_5_pct = returns.quantile(0.05)
best_5_pct = returns.quantile(0.95)
tail_ratio = abs(worst_5_pct) / best_5_pct  # >1 = larger downside

print(f"Skewness: {skewness:.2f}")
print(f"Kurtosis: {kurtosis:.2f} (>3 = fat tails)")
print(f"Tail Ratio: {tail_ratio:.2f}")
```

### Correlation & Beta

```python
# Fetch benchmark (SPY) for correlation
spy = yf.download('SPY', start='2021-01-01', end='2026-03-30', progress=False)
if isinstance(spy.columns, pd.MultiIndex):
    spy.columns = spy.columns.get_level_values(0)

spy_returns = spy['Close'].pct_change().dropna()

# Align series
common_idx = returns.index.intersection(spy_returns.index)
aligned_asset = returns.loc[common_idx]
aligned_spy = spy_returns.loc[common_idx]

correlation = aligned_asset.corr(aligned_spy)

# Beta = Cov(asset, market) / Var(market)
cov_matrix = np.cov(aligned_asset, aligned_spy)
beta = cov_matrix[0, 1] / cov_matrix[1, 1]

print(f"Correlation with SPY: {correlation:.2f}")
print(f"Beta: {beta:.2f} (market sensitivity)")
```

### Maximum Drawdown
```python
# Calculate maximum drawdown

def max_drawdown(equity):
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    max_dd = drawdown.min()
    trough_idx = drawdown.idxmin()
    peak_idx = equity[:trough_idx].idxmax()
    recovery = equity[trough_idx:][equity[trough_idx:] >= equity[peak_idx]]
    recovery_date = recovery.index[0] if len(recovery) > 0 else None
    return {
        'max_drawdown': max_dd,
        'peak_date': peak_idx.strftime('%Y-%m-%d'),
        'trough_date': trough_idx.strftime('%Y-%m-%d'),
        'recovery_date': recovery_date.strftime('%Y-%m-%d') if recovery_date else None
    }

equity = (returns + 1).cumprod()
max_dd_info = max_drawdown(equity)
```

### JSON Serialization
```python
# Store the results
results = {
    'hv_20': hv_20.iloc[-1],
    'hv_60': hv_60.iloc[-1],
    'var_historical': var_historical,
    'var_parametric': var_parametric,
    'max_drawdown': max_dd_info
}

with open('nvda_risk_analysis.json', 'w') as f:
    json.dump(results, f)
```

### Position Sizing Methods

```python
# Kelly Criterion (simplified)
win_rate = 0.55  # assumed win probability
win_loss_ratio = 2.0  # assumed reward/risk ratio
kelly = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
half_kelly = kelly / 2  # conservative sizing

# Volatility-adjusted sizing
target_port_vol = 0.15  # target portfolio vol (15% annual)
asset_vol = hv_20.iloc[-1]
vol_adjusted_weight = target_port_vol / asset_vol

# Beta-adjusted concentration cap
single_name_cap = 0.10
beta_adjusted_cap = single_name_cap / beta
```

### Stop-Loss Levels

```python
# ATR-based stops
tr = pd.concat([data['High']-data['Low'], 
                abs(data['High']-data['Close'].shift(1)),
                abs(data['Low']-data['Close'].shift(1))], axis=1).max(axis=1)
atr_14 = tr.rolling(14).mean().iloc[-1]
atr_stop_2x = current_price - 2 * atr_14

# Technical support
recent_low = data['Low'].rolling(60).min().iloc[-1]
```

### Stress Testing

```python
STRESS_SCENARIOS = {
    'covid_2020': -0.35,
    'rate_hike_2022': -0.25,
    'tech_correction': -0.20,
}
for name, shock in STRESS_SCENARIOS.items():
    print(f"{name}: ${position_notional * shock/1e6:.1f}M loss")
```

## Workflow

1. Fetch with yfinance → flatten MultiIndex columns
2. Compute returns → VaR/CVaR/tail metrics
3. Correlation/Beta → market sensitivity
4. Position sizing → Kelly, vol-adjusted, beta-adjusted
5. Stop-losses → ATR, percentage, technical
6. Stress test → historical scenarios
7. Hedge recs → puts, collars, beta hedge
8. JSON output

Complete skill for comprehensive risk analysis: data fetching, volatility, VaR/CVaR, tail risk, correlation/beta, position sizing, stop-losses, stress testing, and hedge recommendations.