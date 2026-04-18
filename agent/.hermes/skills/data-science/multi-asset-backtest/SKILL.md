---
name: multi-asset-backtest
description: Backtest portfolios with mixed asset classes (stocks + crypto) using Vibe-Trading engine, including limitations and workarounds for timestamp alignment issues.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Backtest, Portfolio, Multi-Asset, Crypto, Stocks, Risk-Parity]
    related_skills: [strategy-generate, detailed-risk-analysis]
---

# Multi-Asset Backtesting Guide

## Overview

This skill covers backtesting portfolios with mixed asset classes (stocks + crypto) using the Vibe-Trading backtest engine, including important limitations and workarounds.

## Key Limitation: Timestamp Alignment

**Critical finding**: The daily backtest engine **alternates between asset classes** rather than holding all assets simultaneously when mixing crypto and stocks:

- **Crypto (OKX)**: Uses UTC timestamps with time component (e.g., `2024-01-02 16:00:00`)
- **US Stocks (yfinance)**: Uses date-only timestamps (e.g., `2024-01-02`)
- **China A-shares (tushare)**: Uses date-only timestamps

The engine creates separate snapshots for each market's trading hours, preventing true simultaneous multi-asset portfolio holding.

### Impact on Optimizers

Built-in optimizers (`risk_parity`, `equal_weight`, `mean_variance`, `max_diversification`) **produce identical or near-identical results** for mixed portfolios because:
1. Only one asset class is active at each timestamp snapshot
2. Within each snapshot, weight differentiation is limited
3. Risk parity's inverse-volatility weighting converges to equal weight within subsets

## Recommended Approaches

### Option 1: Single Asset Class (Recommended)

Run separate backtests for homogeneous portfolios:

```json
// Stocks only - optimizers work correctly
{
  "source": "yfinance",
  "codes": ["MSFT.US", "AAPL.US", "GOOGL.US"],
  "optimizer": "risk_parity",
  "optimizer_params": {"lookback": 60}
}
```

```json
// Crypto only
{
  "source": "okx",
  "codes": ["BTC-USDT", "ETH-USDT", "SOL-USDT"],
  "optimizer": "risk_parity"
}
```

### Option 2: Manual Weight Allocation

For mixed portfolios, implement weights directly in `signal_engine.py`:

```python
import pandas as pd
import numpy as np
from typing import Dict

class SignalEngine:
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        # Equal weight: each asset gets 1/N
        n_assets = len(data_map)
        weight = 1.0 / n_assets
        
        signals = {}
        for code, df in data_map.items():
            signals[code] = pd.Series(weight, index=df.index)
        return signals
```

For risk parity (inverse volatility) - **SIMPLE VERSION for mixed assets**:

⚠️ **Important**: Rolling-window volatility calculation often fails with mixed assets due to empty date intersections. Use this full-period approach instead:

```python
import pandas as pd
import numpy as np
from typing import Dict

class SignalEngine:
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """Risk parity: allocate based on inverse volatility (full-period calc)."""
        signals = {}
        codes = list(data_map.keys())
        
        # Calculate volatility for each asset from available data
        volatilities = {}
        for code, df in data_map.items():
            if len(df) > 20:
                returns = df['close'].pct_change().dropna()
                vol = returns.std() * np.sqrt(252)  # Annualized
                volatilities[code] = vol
            else:
                volatilities[code] = np.nan
        
        # Calculate inverse volatility weights
        valid_vols = {k: v for k, v in volatilities.items() if pd.notna(v) and v > 0}
        
        if len(valid_vols) == 0:
            # Fallback to equal weight
            weight = 1.0 / len(codes)
            for code, df in data_map.items():
                signals[code] = pd.Series(weight, index=df.index)
            return signals
        
        # Risk parity: weight proportional to inverse volatility
        inv_vols = {k: 1.0/v for k, v in valid_vols.items()}
        total_inv_vol = sum(inv_vols.values())
        weights = {k: v/total_inv_vol for k, v in inv_vols.items()}
        
        # Apply constant weights to all timestamps
        for code, df in data_map.items():
            if code in weights:
                signals[code] = pd.Series(weights[code], index=df.index)
            else:
                signals[code] = pd.Series(0.0, index=df.index)
        
        return signals
```

**Why this works**: It calculates volatility from each asset's full available history, avoiding the need for aligned dates. The weights are constant (buy-and-hold), which is appropriate given the engine's limitations.

**Example output** (2024 MSFT/BTC/AAPL):
- BTC (vol 40.3%): weight = 20.8%
- AAPL (vol 22.5%): weight = 37.3%
- MSFT (vol 19.9%): weight = 42.0%

## Workflow

1. **Setup**: Use `setup_backtest_run()` with appropriate config
2. **Signal Engine**: Implement weight logic directly (don't rely on optimizers for mixed assets)
3. **Run**: Call `backtest(run_dir=...)`
4. **Validate**: Check `artifacts/positions.csv` for actual weight allocation
5. **Analyze**: Read `artifacts/metrics.csv` and `artifacts/equity.csv`

## Individual Asset Returns

**Reference: 2024 Full-Year Performance**
| Asset | Return | Sharpe | Max DD |
|-------|--------|--------|--------|
| BTC-USDT | +108.8% | 1.76 | -26.1% |
| MSFT+AAPL (50/50) | +25.95% | 1.37 | -12.7% |

To get individual asset performance for comparison:

```python
import pandas as pd
import glob

files = glob.glob('artifacts/ohlcv_*.csv')
for f in sorted(files):
    df = pd.read_csv(f)
    if len(df) > 0:
        start_price = df['close'].iloc[0]
        end_price = df['close'].iloc[-1]
        ret = (end_price - start_price) / start_price
        asset = f.split('/')[-1].replace('ohlcv_', '').replace('.csv', '')
        print(f'{asset}: {ret*100:.1f}% ({start_price:.2f} -> {end_price:.2f})')
```

## Config Template

```json
{
  "source": "auto",
  "codes": ["MSFT.US", "BTC-USDT", "AAPL.US"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "interval": "1D",
  "initial_cash": 1000000,
  "commission": 0.001,
  "extra_fields": null,
  "optimizer": null,
  "optimizer_params": {},
  "engine": "daily"
}
```

**Note**: Set `optimizer: null` and implement weights in signal_engine.py for mixed portfolios.

## Verification Checklist

- [ ] Check `artifacts/positions.csv` - do weights sum to ~1.0 at each timestamp?
- [ ] Verify all assets have non-zero positions simultaneously (if expected)
- [ ] Compare positions at start vs end - are weights dynamic or static? (Static = buy-and-hold)
- [ ] Compare against individual asset returns for sanity check
- [ ] Watch for timestamp gaps in equity curve
- [ ] For optimizer comparison: verify different weights produce different trade quantities
- [ ] **Debug optimizer issues**: Run both risk_parity and equal_weight, then:
  ```bash
  diff run1/artifacts/positions.csv run2/artifacts/positions.csv
  diff run1/artifacts/metrics.csv run2/artifacts/metrics.csv
  diff run1/artifacts/equity.csv run2/artifacts/equity.csv
  ```
  If all identical → optimizer not functioning (timestamp misalignment)
- [ ] **Check trade distribution**: `cut -d, -f2 artifacts/trades.csv | sort | uniq -c` should show trades across all assets, not concentrated in one
- [ ] **Verify individual asset performance** (for comparison):
  ```python
  import pandas as pd, glob
  for f in sorted(glob.glob('artifacts/ohlcv_*.csv')):
      df = pd.read_csv(f); asset = f.split('/')[-1].replace('ohlcv_', '').replace('.csv', '')
      ret = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]
      print(f'{asset}: {ret*100:.1f}%')
  ```

## Pitfalls

1. **Assuming optimizer works**: Built-in optimizers don't handle mixed timestamp formats correctly
2. **Ignoring position file**: Always verify actual positions, not just final metrics
3. **Benchmark comparison**: The benchmark_return may not be meaningful for mixed portfolios
4. **Data availability**: Crypto trades 365 days, stocks trade ~252 days - expect alignment gaps
5. **Buy-and-hold limitation**: The backtest engine is **buy-and-hold**, not rebalancing. Even when optimizers produce dynamic weights (e.g., risk parity adjusting from 33%/33%/33% to 43%/31%/26% over time), positions are opened on day 1 and held throughout. To capture risk parity benefits, implement **periodic rebalancing logic** in `signal_engine.py` that generates exit/entry signals at rebalance dates.
6. **Identical results indicate misalignment**: If risk-parity and equal-weight produce *identical* metrics AND identical positions.csv, the optimizer is not functioning. This happens because:
   - Crypto timestamps include time component (e.g., `2024-01-02 16:00:00`)
   - Stock timestamps are date-only (e.g., `2024-01-02 00:00:00`)
   - The merged index has ~617 unique timestamps (366 crypto + 251 stocks)
   - At each timestamp, only one asset class has valid data → optimizer sees single-asset subsets
   - Solution: Use homogeneous portfolios OR implement manual weights in signal_engine.py
7. **Verify trading activity**: Check `artifacts/trades.csv` - if only one asset is trading (e.g., only BTC with 57 trades, no AAPL/MSFT trades), the portfolio isn't diversified as intended.
8. **Rolling volatility fails with mixed assets**: The intersection of dates across stocks and crypto is often empty or too small for rolling window calculations. Use full-period volatility instead.
9. **Alternating positions in positions.csv**: You'll see patterns like:
   ```
   2024-01-02 00:00:00, 0.0, 0.333, 0.0    <- BTC only
   2024-01-02 16:00:00, 0.333, 0.0, 0.333  <- AAPL + MSFT
   ```
   This confirms the timestamp alignment issue - weights alternate rather than being simultaneous.

### Real Example: MSFT/BTC/AAPL 2024 (Risk-Parity vs Equal-Weight)

Both optimizers produced **byte-identical results** (verified via `diff`):
- Final value: $1,211,711 (21.17% return)
- Max drawdown: -23.27%, Sharpe: 0.57
- Trade count: 57 (ALL in BTC-USDT, zero in AAPL/MSFT)
- Positions pattern: alternated `0.0,1.0,0.0` (100% BTC) ↔ `0.5,0.0,0.5` (50% AAPL + 50% MSFT)
- Benchmark: 53.24% (portfolio underperformed by 32%)

**Verification commands**:
```bash
# Confirm identical outputs
diff run_riskparity/artifacts/equity.csv run_equalweight/artifacts/equity.csv  # empty = identical
diff run_riskparity/artifacts/metrics.csv run_equalweight/artifacts/metrics.csv

# Check trade distribution (should show all assets, not just one)
cut -d, -f2 artifacts/trades.csv | sort | uniq -c
# Output: 57 BTC-USDT (problem: no AAPL/MSFT trades)
```

**Verification commands used**:
```bash
diff run1/artifacts/equity.csv run2/artifacts/equity.csv  # empty = identical
diff run1/artifacts/metrics.csv run2/artifacts/metrics.csv  # empty = identical
cut -d, -f2 artifacts/trades.csv | sort | uniq -c  # shows 57 BTC-USDT, 0 others
```

**Contrast: Stocks-only portfolio (MSFT + AAPL)**:
- Risk parity **DOES work** for homogeneous portfolios
- Weights varied 46-54% throughout 2024 based on relative volatility
- Both optimizers still produced identical returns (25.95%) because AAPL/MSFT have similar volatilities
- Risk parity weights: AAPL 45.8-50.1%, MSFT 49.9-54.2% (May 2024: AAPL 45.8%, MSFT 54.2%)
- This confirms the optimizer works correctly when timestamps align

## Rebalancing Strategy Template

For true risk-parity testing, implement monthly/quarterly rebalancing:

```python
import pandas as pd
import numpy as np
from typing import Dict

class SignalEngine:
    def __init__(self, config=None):
        self.lookback = 60
        self.rebalance_freq = 21  # ~monthly (trading days)
    
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """Risk parity with monthly rebalancing."""
        signals = {}
        codes = list(data_map.keys())
        
        # Get aligned index
        all_dates = None
        for df in data_map.values():
            if all_dates is None:
                all_dates = set(df.index)
            else:
                all_dates &= set(df.index)
        all_dates = sorted(all_dates)
        
        # Initialize signals
        for code in codes:
            signals[code] = pd.Series(0.0, index=data_map[code].index)
        
        # Calculate risk parity weights at rebalance dates
        for i, date in enumerate(all_dates):
            if i % self.rebalance_freq == 0 and i >= self.lookback:
                # Calculate inverse vol weights
                inv_vols = []
                for code in codes:
                    df = data_map[code]
                    rets = df['close'].pct_change().iloc[:i]
                    vol = rets.tail(self.lookback).std() * np.sqrt(252)
                    inv_vols.append(1.0 / vol if vol > 0 else 0)
                
                total = sum(inv_vols)
                weights = [w/total for w in inv_vols]
                
                # Set signal = weight for next period
                for code, w in zip(codes, weights):
                    signals[code].loc[date] = w
        
        # Forward-fill weights between rebalances
        for code in codes:
            signals[code] = signals[code].ffill().fillna(0.0)
        
        return signals
```
