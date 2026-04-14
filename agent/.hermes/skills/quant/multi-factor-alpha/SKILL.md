---
name: multi-factor-alpha
title: Multi-Factor Alpha Model with IC-Weighted Factor Synthesis
description: Build cross-sectional multi-factor equity strategies with Information Coefficient (IC) based dynamic factor weighting for alpha generation.
triggers:
  - "multi-factor alpha"
  - "factor model"
  - "IC weighted"
  - "cross-sectional factor"
  - "factor synthesis"
  - "quantitative equity strategy"
  - "alpha model"
---

# Multi-Factor Alpha Model with IC-Weighted Synthesis

## Overview

This skill implements a quantitative equity strategy that combines multiple alpha factors using Information Coefficient (IC) weighted synthesis. The model dynamically adjusts factor weights based on each factor's recent predictive power.

## Core Concepts

### Factors Implemented

| Factor | Calculation | Direction | Rationale |
|--------|-------------|-----------|-----------|
| **Momentum** | N-day return (default 20) | Positive | Trend continuation |
| **Reversal** | Short-term return (default 5-day) | Negative | Mean reversion |
| **Volatility** | Std dev of returns (default 20-day) | Negative | Low volatility anomaly |
| **Turnover** | Volume / avg volume (default 20-day) | Negative | Low turnover preference |

### IC-Weighted Synthesis

1. **Calculate IC**: Spearman rank correlation between factor values and forward returns
2. **Rolling IC**: 60-day rolling mean of IC for stability
3. **Weight Factors**: |IC| / sum(|IC|) - higher predictive power = higher weight
4. **Composite Score**: Sum of standardized factor values × IC weights

## Implementation

### Signal Engine Template

```python
import pandas as pd
import numpy as np
from typing import Dict

class SignalEngine:
    """
    Multi-Factor Alpha Model with IC-Weighted Factor Synthesis
    """
    
    def __init__(self):
        self.momentum_window = 20
        self.reversal_window = 5
        self.vol_window = 20
        self.turnover_window = 20
        self.ic_lookback = 60
        self.rebalance_freq = 20
        self.top_n = 10
        
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        signals = {}
        factor_data = {}
        
        # Calculate factors for each stock
        for code, df in data_map.items():
            if len(df) < self.ic_lookback + self.momentum_window + 10:
                continue
                
            returns = df['close'].pct_change()
            
            factor_data[code] = {
                'momentum': df['close'].pct_change(self.momentum_window),
                'reversal': df['close'].pct_change(self.reversal_window),
                'volatility': returns.rolling(self.vol_window).std(),
                'turnover': df['volume'] / df['volume'].rolling(self.turnover_window).mean(),
                'returns': returns,
                'close': df['close']
            }
        
        if len(factor_data) < 5:
            return {code: pd.Series(0.0, index=df.index) for code, df in data_map.items()}
        
        # Build cross-sectional factor matrices
        all_dates = pd.Index(sorted(set().union(*[
            f['close'].index for f in factor_data.values()
        ])))
        
        factor_matrices = {
            'momentum': pd.DataFrame(index=all_dates, columns=factor_data.keys()),
            'reversal': pd.DataFrame(index=all_dates, columns=factor_data.keys()),
            'volatility': pd.DataFrame(index=all_dates, columns=factor_data.keys()),
            'turnover': pd.DataFrame(index=all_dates, columns=factor_data.keys()),
            'returns': pd.DataFrame(index=all_dates, columns=factor_data.keys())
        }
        
        for code, factors in factor_data.items():
            for fname in factor_matrices:
                factor_matrices[fname].loc[factors[fname].index, code] = factors[fname].values
        
        for fname in factor_matrices:
            factor_matrices[fname] = factor_matrices[fname].astype(float)
        
        # Calculate IC for each factor
        forward_returns = factor_matrices['returns'].shift(-1)
        ic_series = {}
        
        for factor_name in ['momentum', 'reversal', 'volatility', 'turnover']:
            factor_vals = factor_matrices[factor_name]
            ic_vals = []
            
            for date in factor_vals.index:
                f_vals = factor_vals.loc[date].dropna()
                r_vals = forward_returns.loc[date].dropna()
                common = f_vals.index.intersection(r_vals.index)
                
                if len(common) < 3:
                    ic_vals.append(np.nan)
                    continue
                
                rank_f = f_vals[common].rank()
                rank_r = r_vals[common].rank()
                ic_vals.append(rank_f.corr(rank_r, method='pearson'))
            
            ic_series[factor_name] = pd.Series(ic_vals, index=factor_vals.index)
        
        # Calculate IC weights
        ic_weights = {}
        for fname in ic_series:
            ic_rolling = ic_series[fname].rolling(self.ic_lookback, min_periods=20).mean()
            ic_weights[fname] = ic_rolling.abs()
        
        total_ic = pd.DataFrame(ic_weights).sum(axis=1)
        for fname in ic_weights:
            ic_weights[fname] = ic_weights[fname] / total_ic
            ic_weights[fname] = ic_weights[fname].fillna(0.25)
        
        # Standardize factors
        standardized = {}
        for fname in ['momentum', 'reversal', 'volatility', 'turnover']:
            vals = factor_matrices[fname]
            zscore = vals.sub(vals.mean(axis=1), axis=0).div(vals.std(axis=1).replace(0, np.nan), axis=0)
            standardized[fname] = zscore.fillna(0)
        
        # Adjust directions
        standardized['reversal'] = -standardized['reversal']
        standardized['volatility'] = -standardized['volatility']
        standardized['turnover'] = -standardized['turnover']
        
        # Composite score
        composite = pd.DataFrame(0.0, index=all_dates, columns=factor_data.keys())
        for fname in ['momentum', 'reversal', 'volatility', 'turnover']:
            for date in all_dates:
                if date in ic_weights[fname].index:
                    composite.loc[date] += standardized[fname].loc[date] * ic_weights[fname].loc[date]
        
        # Generate signals
        rebalance_dates = all_dates[::self.rebalance_freq]
        
        for code in factor_data.keys():
            signal_series = pd.Series(0.0, index=factor_data[code]['close'].index)
            
            for i, rd in enumerate(rebalance_dates):
                next_rd = rebalance_dates[i + 1] if i + 1 < len(rebalance_dates) else all_dates[-1]
                
                if rd not in composite.index:
                    continue
                
                scores = composite.loc[rd].dropna()
                if len(scores) == 0:
                    continue
                
                ranked = scores.rank(ascending=False)
                selected = ranked[ranked <= self.top_n].index.tolist()
                weight = 1.0 / self.top_n if code in selected else 0.0
                
                mask = (signal_series.index >= rd) & (signal_series.index < next_rd)
                signal_series.loc[mask] = weight
            
            signals[code] = signal_series
        
        for code in data_map.keys():
            if code not in signals:
                signals[code] = pd.Series(0.0, index=data_map[code].index)
        
        return signals
```

## Configuration

```json
{
  "source": "yfinance",
  "codes": ["000001.SZ", "000002.SZ", "..."],
  "start_date": "2023-01-01",
  "end_date": "2024-12-31",
  "interval": "1D",
  "initial_cash": 10000000,
  "commission": 0.0015,
  "slippage": 0.001,
  "engine": "daily"
}
```

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `momentum_window` | 20 | Days for momentum calculation |
| `reversal_window` | 5 | Days for reversal (short-term) |
| `vol_window` | 20 | Days for volatility calculation |
| `turnover_window` | 20 | Days for turnover average |
| `ic_lookback` | 60 | Days for rolling IC calculation |
| `rebalance_freq` | 20 | Trading days between rebalances |
| `top_n` | 10 | Number of stocks to select |

## Pitfalls

1. **Minimum Universe Size**: Need at least 5+ stocks for meaningful cross-sectional Z-scores
2. **Lookback Period**: Ensure data history > `ic_lookback + max(factor_windows) + 10`
3. **IC Stability**: Short IC lookback may cause erratic weights; long lookback may miss regime changes
4. **Factor Collinearity**: Highly correlated factors will receive similar weights - consider orthogonalization
5. **Rebalancing Costs**: Frequent rebalancing increases transaction costs - balance with `rebalance_freq`

## Extensions

- Add fundamental factors (PE, PB, ROE) if `extra_fields` available
- Implement sector-neutral weighting
- Add risk model constraints (max sector exposure, tracking error)
- Use machine learning for non-linear factor combinations

---

## Momentum Factor Library (A-Share Tested)

For momentum-specific strategies, these 6 factors have been empirically tested on CSI 300:

| Factor | Formula | Direction | Typical IC (CSI 300) | Notes |
|--------|---------|-----------|---------------------|-------|
| **Breakout** | `(Close - High(60D)) / High(60D)` | Positive | 0.018 | Highest ICIR; watch for false breakouts |
| **Momentum** | `Close[t] / Close[t-20] - 1` | Positive | 0.004 | Core trend factor; 13% annual factor return |
| **Vol Momentum** | `Volume / MA(Volume, 20)` | Positive | 0.003 | Low correlation diversifier |
| **Reversal** | `Close[t] / Close[t-5] - 1` | Negative | -0.002 | Mean reversion; hedge for choppy markets |
| **RSI** | `100 - 100/(1 + RS)` | Negative | -0.001 | Weak standalone; correlated with momentum |
| **Vol-Adj Momentum** | `Momentum(20D) / StdDev(20D)` | Positive | ~0 | Too correlated with raw momentum (0.94) |

### Recommended 4-Factor Combo (Equal Weight)
```python
selected_factors = ['breakout', 'vol_momentum', 'momentum', 'reversal']
# Combined IC: ~0.014, ICIR: ~0.053, Hit Rate: ~53%
```

---

## Post-Backtest Factor Analysis Workflow

After running a backtest, analyze factor performance with this script:

```python
# Save as factor_analysis.py in the run directory
import pandas as pd, numpy as np, glob, os, json

def load_ohlcv_data(artifact_dir):
    data_map = {}
    for f in glob.glob(os.path.join(artifact_dir, 'ohlcv_*.csv')):
        code = os.path.basename(f).replace('ohlcv_', '').replace('.csv', '')
        data_map[code] = pd.read_csv(f, index_col=0, parse_dates=True)
    return data_map

def calculate_ic(factor_vals, forward_returns, min_stocks=5):
    """Compute IC for a single date"""
    common = factor_vals.dropna().index.intersection(forward_returns.dropna().index)
    if len(common) < min_stocks:
        return np.nan
    return factor_vals[common].rank().corr(forward_returns[common].rank(), method='pearson')

# Key outputs:
# - ic_series.csv: Daily IC for each factor
# - factor_stats.json: Mean IC, ICIR, hit rate, annual factor return
# - factor_correlation.csv: Correlation matrix for pruning redundant factors
```

**Interpretation Guidelines:**
- **IC > 0.02**: Strong predictive power (rare in practice)
- **ICIR > 0.5**: Excellent risk-adjusted factor performance
- **Hit Rate 50-55%**: Normal for equity factors
- **Correlation > 0.7**: Consider removing one of the pair

---

## A-Share Specific Considerations

### Data Source Issues
- **tushare**: Requires API permissions; many endpoints need paid tiers
- **yfinance**: Shenzhen stocks (`.SZ`) work reliably; Shanghai stocks (`.SH`) often fail with timezone errors
- **Recommendation**: Start with Shenzhen constituents or use local data providers

### Factor Decay & Cyclicality
| Factor | Decay Trigger | Half-life | Mitigation |
|--------|--------------|-----------|------------|
| Momentum | Policy shifts, liquidity crunches | 15-30 days | Rolling IC weights |
| Reversal | Strong trending markets | 3-10 days | Combine with momentum |
| Breakout | False breakouts at resistance | 5-15 days | Volume confirmation |

### Market Structure Effects
- **Retail-dominated** (~80% turnover): Stronger short-term reversal patterns
- **Policy-driven cycles**: Factor rotation every 6-12 months with monetary easing/tightening
- **Sector concentration**: CSI 300 heavily weighted to financials/industrials — apply sector neutrality

### Risk Monitoring
- Watch for factor correlation spikes (>0.8) as regime change warnings
- Monitor IC decay — if rolling IC turns negative for 20+ days, reduce weight
- Track max drawdown vs benchmark — momentum strategies can underperform in sharp reversals
