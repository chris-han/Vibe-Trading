---
name: portfolio-backtest-optimizer-limitations
description: Critical limitations of the daily backtest engine when using portfolio optimizers (risk_parity, equal_volatility, etc.) and how to properly test allocation strategies.
---

# Portfolio Optimizer Backtest Limitations

## Key Finding

The **daily backtest engine** interprets signals as **entry/exit triggers**, not as continuous target portfolio weights. This fundamentally limits how portfolio optimizers (`risk_parity`, `equal_volatility`, `mean_variance`, `max_diversification`) behave in backtests.

## What Happens with Constant Signals

When you return `signal = 1.0` for all assets (intending a buy-and-hold portfolio):

| Expected Behavior | Actual Behavior |
|-------------------|-----------------|
| Continuous exposure to all assets with optimizer-determined weights | Engine flips in/out of positions based on internal daily logic |
| Optimizer sets overall portfolio allocation | Optimizer only affects **intra-asset splits** when engine happens to hold multiple assets |
| Monthly/quarterly rebalancing of target weights | Daily trading with no persistent portfolio state |

## Empirical Example: MSFT + BTC-USDT + AAPL (2024)

### Test Setup
```json
{
  "source": "auto",
  "codes": ["MSFT.US", "BTC-USDT", "AAPL.US"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_cash": 1000000,
  "commission": 0.001
}
```

### Results Comparison

| Config | Position Pattern | Stock Weights | Total Return |
|--------|------------------|---------------|--------------|
| No optimizer (equal-weight) | 100% BTC ↔ 50% AAPL + 50% MSFT (daily flip) | Fixed 50/50 | 21.17% |
| `risk_parity` + `lookback: 60` | 100% BTC ↔ variable stock split (daily flip) | Dynamic: 55-59% AAPL, 41-45% MSFT | 21.17% |

**Both produced identical returns** because the overall trading pattern was identical. The optimizer only changed the AAPL/MSFT split within the stock portion, which had negligible impact on overall P&L.

### Position File Evidence

**Equal-weight positions.csv:**
```
timestamp,AAPL.US,BTC-USDT,MSFT.US
2024-12-19,0.5,0.0,0.5
2024-12-20,0.0,1.0,0.0
2024-12-23,0.5,0.0,0.5
```

**Risk-parity positions.csv:**
```
timestamp,AAPL.US,BTC-USDT,MSFT.US
2024-12-19,0.589,0.0,0.411
2024-12-20,0.0,1.0,0.0
2024-12-23,0.568,0.0,0.432
```

The optimizer IS working (variable weights vs fixed 50/50), but the daily flipping pattern is identical.

## When Optimizers Work as Expected

Portfolio optimizers produce meaningful differences when:

1. **Continuous exposure**: All assets maintain non-zero weights throughout the backtest
2. **No daily flipping**: The signal engine doesn't trigger daily entry/exit
3. **Long-term allocation**: Monthly or quarterly rebalancing, not daily trading
4. **Verified positions**: `positions.csv` shows all assets with persistent weights

## How to Properly Backtest Portfolio Allocators

### Option 1: Verify Continuous Exposure First

Before trusting optimizer results, always check `artifacts/positions.csv`:

```bash
# Check if all assets have non-zero weights throughout
head -50 artifacts/positions.csv
tail -50 artifacts/positions.csv

# Look for patterns like:
# - All assets > 0 on most days = good (optimizer can work)
# - Frequent 100% single-asset positions = bad (engine is flipping)
```

If you see daily flipping (100% in one asset, then 100% in another), the optimizer cannot produce meaningful allocation differences.

### Option 2: Implement Explicit Rebalancing Logic

For periodic rebalancing (e.g., monthly), implement in `signal_engine.py`:

```python
import pandas as pd
import numpy as np
from typing import Dict

class SignalEngine:
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """
        Buy-and-hold with constant 1.0 signals.
        The optimizer handles weight allocation.
        """
        signals = {}
        for code, df in data_map.items():
            # Constant signal = always long, let optimizer size positions
            signal = pd.Series(1.0, index=df.index, name=code)
            signals[code] = signal
        return signals
```

Then verify the positions show continuous exposure. If the engine still flips daily, the daily engine may not support true portfolio backtests.

### Option 3: Use a Different Engine Type

Check if the system supports a **portfolio engine** or **allocation engine** mode:

```json
{
  "engine": "portfolio",  // or "allocation" - check system capabilities
  "optimizer": "risk_parity",
  "optimizer_params": {"lookback": 60}
}
```

If only `"engine": "daily"` is available, portfolio optimizer comparisons may not be meaningful.

## Diagnostic Checklist

Before running an optimizer backtest:

- [ ] **Check engine type**: Is there a portfolio/allocation engine, or only daily?
- [ ] **Inspect positions.csv**: Do all assets have persistent non-zero weights?
- [ ] **Compare patterns**: Run with and without optimizer, compare positions.csv
- [ ] **Verify weight variation**: Does the optimizer produce different weights over time?
- [ ] **Check trade_count**: High trade count (>100/year for 3 assets) suggests daily flipping

## Alternative: Manual Weight Comparison

If the daily engine doesn't support true portfolio backtests, compare allocators manually:

1. **Extract historical prices** for all assets
2. **Compute optimizer weights** externally (using the same lookback window)
3. **Calculate portfolio returns** manually: `return_t = sum(weights_t-1 * returns_t)`
4. **Compare metrics**: Sharpe, max drawdown, turnover between allocators

This bypasses the daily engine's trading logic and directly tests the allocation strategy.

## Summary

| Scenario | Optimizer Effective? | Recommendation |
|----------|---------------------|----------------|
| Daily trading with entry/exit signals | No | Don't use optimizer; focus on signal logic |
| Buy-and-hold with continuous exposure | Yes (verify positions.csv) | Use optimizer, but verify weights persist |
| Periodic rebalancing (monthly/quarterly) | Yes | Implement rebalancing logic in signal_engine |
| Comparing risk_parity vs equal_weight | Only if continuous exposure | Always check positions.csv first |

## Related Skills

- `asset-allocation`: Theory and optimizer configuration
- `strategy-generate`: Signal engine implementation
- `backtest-diagnose`: Debugging failed or unexpected backtest results
