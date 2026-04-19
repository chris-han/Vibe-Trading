---
name: portfolio-optimizer-comparison
description: Compare portfolio optimizers (risk_parity, equal_volatility, etc.) against equal-weight baselines, with proper rebalancing setup.
---

## Overview

This skill covers how to properly compare portfolio optimizers (risk_parity, equal_volatility, mean_variance, max_diversification) against equal-weight baselines in the Vibe-Trading backtest system.

## Critical System Limitations

### 1. Rebalancing Behavior

**The backtest engine only trades on DIRECTION changes, not WEIGHT changes.**

- Location: `backtest/engines/base.py`, `_rebalance()` method
- Logic: Positions are only closed when `target_dir == 0 or target_dir != current_pos.direction`
- **Implication**: If you maintain long signals (1.0) for all assets, the optimizer calculates varying weights but NO rebalancing trades occur after the initial buy

**Example:**
```python
# This does NOT trigger rebalancing:
signal = pd.Series(1.0, index=df.index)  # Always long

# Risk parity weights may vary daily (AAPL: 36%, GOOGL: 26%, MSFT: 37%)
# But the engine won't trade to match these weights
```

### 2. Optimizer Lookback Period

**Optimizers skip the first N days (default 60).**

- Location: `backtest/optimizers/base.py`, line 59: `if i < self.lookback: continue`
- **Implication**: First 60 days use equal weights regardless of optimizer setting

### 3. Mixed-Asset Timestamp Alignment

**Crypto and stock data have different timestamp formats:**

| Asset Class | Timestamp Format | Example |
|-------------|-----------------|---------|
| Crypto (OKX) | With time component | `2024-01-01 16:00:00` |
| US Stocks (yfinance) | Date only | `2024-01-01` |
| China A-shares (tushare) | Date only | `2024-01-01` |

**Implication**: When mixing crypto + stocks, alignment issues cause only one asset class to trade.

## Proper Comparison Workflow

### Option A: Periodic Rebalancing Signal Engine

To force rebalancing, implement signals that periodically reset (triggering direction changes):

```python
from typing import Dict
import pandas as pd
import numpy as np


class SignalEngine:
    def __init__(self, rebalance_freq: int = 20):
        """
        Args:
            rebalance_freq: Rebalancing frequency in trading days
        """
        self.rebalance_freq = rebalance_freq
    
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        signals = {}
        for code, df in data_map.items():
            signal = pd.Series(1.0, index=df.index, dtype=float)
            # Periodically reset to 0 then back to 1 to trigger rebalance
            dates = df.index
            for i in range(self.rebalance_freq, len(dates), self.rebalance_freq):
                signal.iloc[i] = 0.0  # Flat for one bar
            signals[code] = signal
        return signals
```

**Config for risk parity:**
```json
{
  "source": "auto",
  "codes": ["AAPL.US", "GOOGL.US", "MSFT.US"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "optimizer": "risk_parity",
  "optimizer_params": {"lookback": 60}
}
```

**Config for equal weight baseline:**
```json
{
  "source": "auto",
  "codes": ["AAPL.US", "GOOGL.US", "MSFT.US"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "optimizer": null
}
```

### Option B: Single Asset Class Only

For clean comparisons, use only one asset class to avoid timestamp issues:

**Recommended portfolios:**
- US stocks only: `["AAPL.US", "GOOGL.US", "MSFT.US"]`
- Crypto only: `["BTC-USDT", "ETH-USDT", "SOL-USDT"]`
- China A-shares only: `["000001.SZ", "600519.SH", "000858.SZ"]`

**Avoid mixing:** `["AAPL.US", "BTC-USDT"]` unless you understand the alignment implications.

## Optimizer Reference

| Optimizer | Config Value | Best For | Parameters |
|-----------|--------------|----------|------------|
| Equal Volatility | `equal_volatility` | Simple baseline | `lookback: 60` |
| Risk Parity | `risk_parity` | Long-term robust allocation | `lookback: 60` |
| Mean-Variance | `mean_variance` | When return forecasts available | `lookback: 60, risk_free: 0.0` |
| Max Diversification | `max_diversification` | Low-correlation portfolios | `lookback: 60` |

## Verification Checklist

After running backtests, verify:

1. **Positions file shows varying weights** (risk parity) vs constant weights (equal weight):
   ```bash
   grep "2024-06" artifacts/positions.csv
   ```

2. **Trade count reflects rebalancing** - should be > number of assets if periodic rebalancing is working

3. **First trade timing** - should be within first `lookback` days if optimizer is active

4. **No NaN in equity curve**:
   ```bash
   grep "NaN" artifacts/equity.csv
   ```

## Common Pitfalls

| Symptom | Root Cause | Fix |
|---------|------------|-----|
| Identical metrics for both optimizers | No rebalancing occurring | Use periodic signal reset (Option A) |
| Only crypto trades in mixed portfolio | Timestamp misalignment | Use single asset class (Option B) |
| First 60 days show equal weights | Optimizer lookback period | Expected behavior; extend backtest period |
| Zero trades | Signal always flat or conditions too strict | Check signal values are non-zero |
| Alternating positions (e.g., 100% BTC one day, 50/50 stocks next) | Mixed-asset timestamp alignment causes engine to pick one asset class per bar | Use single asset class; verify with `positions.csv` |

## Mixed-Asset Backtest Findings (Empirical)

When testing mixed portfolios like `[\"MSFT.US\", \"BTC-USDT\", \"AAPL.US\"]` for 2024:

**Observed behavior:**
- Positions alternate between asset classes rather than holding all simultaneously
- Example pattern: `BTC-USDT: 100%` on crypto timestamps, then `AAPL.US: 50%, MSFT.US: 50%` on stock timestamps
- Risk-parity and equal-weight produce **identical metrics** because the optimizer can't properly allocate across misaligned timestamps

**Root cause:**
- Crypto (OKX) data has timestamps like `2024-01-02 00:00:00` and `2024-01-02 16:00:00`
- US stocks (yfinance) have timestamps like `2024-01-02` (date only)
- The engine aligns on exact timestamp matches, causing assets to trade on different bars

**Verification command:**
```bash
# Check if all assets are held simultaneously
head -50 artifacts/positions.csv | grep -E \"^[0-9]\" | awk -F, '{print $2, $3, $4}'
# If you see patterns like \"0.0,1.0,0.0\" alternating with \"0.5,0.0,0.5\", alignment is broken
```

## Example Comparison Output

```
## Portfolio Optimizer Comparison: US Tech Stocks (2024)

| Metric | Risk Parity | Equal Weight | Difference |
|--------|-------------|--------------|------------|
| Final Value | $1,303,900 | $1,303,900 | $0 |
| Total Return | 30.4% | 30.4% | 0% |
| Sharpe Ratio | 1.50 | 1.50 | 0.00 |
| Max Drawdown | -14.3% | -14.3% | 0% |
| Trade Count | 15 | 3 | +12 |

Note: Without periodic rebalancing signals, both strategies produce identical 
results because the engine doesn't rebalance on weight changes alone.
```

## Related Skills

- `strategy-generate`: General strategy backtest workflow
- `backtest-diagnose`: Debugging failed or abnormal backtests
