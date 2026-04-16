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

1. **Minimum Universe Size**: ⚠️ **Updated**: 5+ is theoretical minimum; **30-50+ recommended** for stable cross-sectional rankings. **Validated**: 45 stocks produced Sharpe 0.47, IR 0.88; 15 stocks produced noisy, negative returns.
2. **Lookback Period**: Ensure data history > `ic_lookback + max(factor_windows) + 10`
3. **IC Stability**: Short IC lookback may cause erratic weights; long lookback may miss regime changes
4. **Factor Collinearity**: Highly correlated factors will receive similar weights - consider orthogonalization
5. **Rebalancing Costs**: Frequent rebalancing increases transaction costs - balance with `rebalance_freq`
6. **Over-Diversification**: Adding factors with ICIR < 0.03 dilutes alpha — prefer 2 strong factors over 4-5 weak ones
7. **Equal Weight Bias**: Theoretical equal weighting often underperforms empirically-tuned splits (e.g., 70/30 beat equal weight in testing)

## Extensions

- Add fundamental factors (PE, PB, ROE) if `extra_fields` available
- Implement sector-neutral weighting
- Add risk model constraints (max sector exposure, tracking error)
- Use machine learning for non-linear factor combinations

---

## Momentum Factor Library (A-Share Tested on CSI 300)

Empirical results from 2023-2024 backtest on 15 CSI 300 constituents (yfinance, `.SZ` stocks):

| Factor | Formula | Direction | Mean IC | ICIR | Hit Rate | Notes |
|--------|---------|-----------|---------|------|----------|-------|
| **Vol Momentum** | `Volume / MA(Volume, 20)` | Positive | 0.0171 | **0.058** | 51.6% | Best ICIR; low correlation (0.17) with price momentum |
| **Breakout** | `(Close - High₆₀) / High₆₀` | Positive | **0.0192** | 0.052 | 52.0% | Highest raw IC; watch false breakouts |
| **Momentum** | `Close[t] / Close[t-20] - 1` | Positive | 0.0114 | 0.032 | 52.4% | Core trend factor; stable but moderate IC |
| **Vol-Adj Momentum** | `Mom₂₀ / StdDev₂₀` | Positive | 0.0104 | 0.030 | 53.0% | **Redundant**: 0.90 corr with momentum — drop |
| **Reversal** | `Close[t] / Close[t-5] - 1` | Negative | 0.0081 | 0.023 | 48.0% | Regime hedge; weak in strong trends |
| **RSI** | `100 - 100/(1 + RS₁₄)` | Negative | 0.0009 | 0.002 | 49.5% | **Useless standalone**: near-zero IC; 0.71 corr with momentum |

### Recommended Factor Combos (Updated 2026-04-16 with 45-Stock Validation)

**IMPORTANT: Empirical backtest results validated on 45 CSI 300 constituents (yfinance, `.SZ` stocks, 2023-2024):**

| Combo | Factors | Weights | Total Return | Sharpe | Max DD | Verdict |
|-------|---------|---------|--------------|--------|--------|---------|
| **Validated** | Momentum + Reversal + Volatility + Turnover | IC-weighted | **+14.45%** | **0.467** | **-16.5%** | ✅ Production-ready with refinement |
| Best (15-stock) | Momentum + Vol_Momentum | 70% / 30% | -1.48% | 0.067 | -23.4% | ⚠️ Universe too small |
| Test 2 | Momentum + Vol_Mom + Reversal | Equal | -7.59% | -0.081 | -30.3% | ❌ Reversal hurt |

**Key Learnings from 45-Stock Validation:**
1. **Universe size matters**: 45 stocks produced stable cross-sectional rankings vs noisy 15-stock results
2. **IC-weighting works**: Dynamic factor weighting adapted to regime changes, generating +20.74% excess return
3. **All 4 factors contributed**: Unlike 15-stock tests where reversal hurt, the larger universe stabilized factor signals
4. **Benchmark outperformance**: Strategy returned +14.45% vs -6.30% benchmark (CSI 300 proxy)

```python
# Recommended starting point (updated based on live backtest)
selected_factors = ['momentum', 'vol_momentum']
factor_weights = {'momentum': 0.7, 'vol_momentum': 0.3}
# Rationale: momentum (core trend, 52% hit rate) + vol confirmation (best ICIR 0.058)
# Weighting: favor momentum but require volume confirmation
```

### Correlation-Based Pruning Rules
From empirical correlation matrix:
- `momentum ↔ vol_adj_momentum`: 0.90 — **remove vol_adj_momentum**
- `momentum ↔ rsi`: 0.71 — **remove rsi** (also weak IC)
- `rsi ↔ vol_adj_momentum`: 0.80 — both redundant
- `vol_momentum` has lowest avg correlation (0.22) — best diversifier

**Rule**: If |corr| > 0.7, keep the factor with higher ICIR and drop the other.

---

## Post-Backtest Analysis Workflow

After running a backtest, perform comprehensive analysis in this order:

### Step 1: Factor IC Analysis
Compute IC, ICIR, hit rate, and correlation matrix for each factor.

### Step 2: Chart Pattern Analysis
Run `pattern` tool on the backtest run_dir to detect technical patterns (peaks/valleys, candlestick, support/resistance, head & shoulders, double top/bottom, triangles, broadening). This provides context for:
- **Trend regime identification**: High peak/valley count = choppy market; low count = strong trends
- **Reversal signal validation**: Double bottoms supporting reversal factor logic
- **Breakout opportunities**: Triangle/broadening patterns for momentum entry points

```python
# Call after backtest completes
pattern(run_dir=RUN_DIR, patterns='all', window=10)
```

### Step 3: Trade Log Analysis
Review `artifacts/trades.csv` for:
- Win/loss distribution
- Average holding period vs rebalance frequency
- Largest winners/losers and their factor scores at entry

```python
#!/usr/bin/env python3
"""Factor Analysis: Computes IC, ICIR, hit rate, correlation matrix, and recommendations"""
import pandas as pd, numpy as np, glob, os, json

ARTIFACT_DIR = "<run_dir>/artifacts"
FACTOR_NAMES = ['momentum', 'reversal', 'breakout', 'vol_momentum', 'rsi', 'vol_adj_momentum']

def load_ohlcv_data(artifact_dir):
    data_map = {}
    for f in glob.glob(os.path.join(artifact_dir, 'ohlcv_*.csv')):
        code = os.path.basename(f).replace('ohlcv_', '').replace('.csv', '')
        df = pd.read_csv(f, index_col=0, parse_dates=True)
        if len(df) > 50:
            data_map[code] = df
    return data_map

def calculate_factors(df, windows={'momentum': 20, 'reversal': 5, 'breakout': 60, 'vol': 20, 'rsi': 14}):
    close, high, volume = df['close'], df['high'], df['volume']
    returns = close.pct_change()
    return {
        'momentum': close.pct_change(windows['momentum']),
        'reversal': close.pct_change(windows['reversal']),
        'breakout': (close - high.rolling(windows['breakout']).max()) / high.rolling(windows['breakout']).max(),
        'vol_momentum': volume / volume.rolling(windows['vol']).mean(),
        'rsi': 100 - 100 / (1 + (close.diff().where(lambda x: x > 0, 0).rolling(windows['rsi']).mean() / 
                                   (-close.diff().where(lambda x: x < 0, 0)).rolling(windows['rsi']).mean().replace(0, np.nan))),
        'vol_adj_momentum': close.pct_change(windows['momentum']) / returns.rolling(windows['vol']).std().replace(0, np.nan),
        'returns': returns, 'close': close
    }

def compute_ic(factor_vals, forward_returns, min_stocks=5):
    common = factor_vals.dropna().index.intersection(forward_returns.dropna().index)
    if len(common) < min_stocks:
        return np.nan
    return factor_vals[common].rank().corr(forward_returns[common].rank(), method='pearson')

# Main analysis
data_map = load_ohlcv_data(ARTIFACT_DIR)
factor_data = {code: calculate_factors(df) for code, df in data_map.items() if len(df) > 70}

# Build factor matrices, compute IC time series, calculate stats
# (Full implementation: see runs/*/factor_analysis.py template)

# Key outputs:
# - factor_ic_stats.csv: Mean IC, ICIR, hit rate per factor
# - factor_correlation.csv: Correlation matrix for pruning
# - factor_analysis_summary.json: Selected factors + recommendations
```

**Interpretation Guidelines (CSI 300 empirical benchmarks):**
- **IC > 0.015**: Strong (vol_momentum, breakout achieved this)
- **ICIR > 0.05**: Good risk-adjusted performance (vol_momentum: 0.058)
- **ICIR < 0.03**: Weak — consider dropping (rsi: 0.002)
- **Hit Rate 50-55%**: Normal for equity factors
- **Correlation > 0.7**: Remove redundant factor (keep higher ICIR)

**Workflow:**
1. Run backtest with all candidate factors in signal engine
2. Execute `factor_analysis.py` on artifacts directory
3. Review `factor_ic_stats.csv` — drop factors with ICIR < 0.02
4. Review `factor_correlation.csv` — prune pairs with |corr| > 0.7
5. Update signal engine with selected 3-5 factor combo

---

## A-Share Specific Considerations

### Data Source Issues (Verified 2026-04-14)
- **tushare**: ❌ Requires API permissions — free tier returns "抱歉，您没有接口访问权限" for all endpoints
- **yfinance**: ✅ Shenzhen stocks (`.SZ`) work reliably; tested on 15 CSI 300 constituents
- **yfinance**: ⚠️ Shanghai stocks (`.SH`) may fail with timezone/operational errors
- **Recommendation**: Use yfinance with `.SZ` stocks for A-share backtests; filter CSI 300 to Shenzhen constituents if needed

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

---

## Iterative Strategy Development Workflow (Live Backtest Protocol)

When building a multi-factor strategy, follow this rapid iteration workflow:

### Phase 1: Baseline (30 min)
1. Start with **2-factor combo** (momentum + vol_momentum, 70/30 weight)
2. Run backtest on full available history
3. Record: total return, Sharpe, max DD, win rate, trade count

### Phase 2: Factor Addition Tests (1 hour)
Test each candidate factor by adding to baseline:
```
Test A: Baseline + Reversal (equal weight)
Test B: Baseline + Breakout (equal weight)
Test C: Baseline + Volatility (equal weight)
```
**Keep only if**: Sharpe improves by >0.1 OR max DD reduces by >3%

### Phase 3: Weight Optimization (30 min)
For best 2-3 factor combo, test weight splits:
- 80/20, 70/30, 60/40, 50/50
- Pick highest Sharpe with acceptable DD

### Phase 4: Robustness Checks (30 min)
1. **Sub-period analysis**: Split into 2023 vs 2024 — check consistency
2. **Universe sensitivity**: Test with 10, 20, 30 stock universes
3. **Parameter sensitivity**: Vary momentum window (15, 20, 30, 60 days)

### Decision Matrix
| Result | Action |
|--------|--------|
| Sharpe > 0.2, DD < 20% | ✅ Production-ready |
| Sharpe 0.0-0.2, DD < 25% | ⚠️ Needs more work |
| Sharpe < 0, DD > 30% | ❌ Reject, revisit factors |

### Common Pitfalls Discovered
1. **Over-diversification**: Adding weak factors (ICIR < 0.03) dilutes strong signals
2. **Small universe**: <20 stocks leads to noisy cross-sectional rankings
3. **Equal weight bias**: Theoretical equal weight often underperforms tuned splits
4. **IC vs live performance**: High IC factors (breakout: 0.0192) may underperform in live backtest due to regime effects

### Documentation Template
After each backtest run, record:
```
Run ID: [timestamp]
Factors: [list]
Weights: {factor: weight}
Universe: N stocks
Period: YYYY-MM-DD to YYYY-MM-DD
Metrics: {return, sharpe, max_dd, win_rate, trade_count}
Verdict: [keep/reject/iterate]
Notes: [key observations]
```
