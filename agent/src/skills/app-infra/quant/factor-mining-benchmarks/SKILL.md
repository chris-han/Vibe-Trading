---
name: factor-mining-benchmarks
description: Empirical IC/IR benchmarks and factor correlation patterns from CSI 300 factor mining (2023-2025). Reference for expected factor performance and combination weights.
---

# Factor Mining Benchmarks (CSI 300)

## Overview

This skill contains empirical benchmarks from systematic factor mining on CSI 300 constituents (50 stocks, 2023-2025 sample). Use these as reference expectations when evaluating new factors or validating factor analysis results.

## Empirical IC/IR Benchmarks

| Factor | Formula | Typical IC | Typical IR | Hit Rate | Direction | Notes |
|--------|---------|-----------|-----------|----------|-----------|-------|
| **Volatility** | 20d rolling std of returns | -0.05 to -0.08 | -0.20 to -0.30 | 35-40% | Negative | **Strongest |IC|**; low-vol anomaly |
| **RSI** | 14-day RSI oscillator | 0.02 to 0.04 | 0.10 to 0.15 | 54-57% | Positive | Best positive IC; excellent monotonicity |
| **Momentum** | 20-day return | 0.01 to 0.03 | 0.05 to 0.10 | 52-56% | Positive | Weaker than expected; regime-dependent |
| **Reversal** | 5-day return | 0.01 to 0.02 | 0.05 to 0.08 | 53-56% | Positive | Mild mean reversion signal |
| **MACD Hist** | MACD - Signal | 0.01 to 0.02 | 0.05 to 0.08 | 50-53% | Positive | Redundant with RSI (corr ~0.70) |
| **Turnover** | Volume / MA20(Volume) | -0.01 to 0.01 | -0.03 to 0.03 | 45-50% | Negative | Essentially noise; skip |

### Interpretation

- **|IC| > 0.05**: Strong factor (volatility qualifies)
- **|IC| 0.02-0.05**: Moderate factor (RSI, momentum qualify)
- **|IC| < 0.02**: Weak/noise (turnover, possibly reversal)
- **IR > 0.10**: Stable factor (only volatility and RSI qualify)
- **Hit Rate < 45%**: Consider reversing direction (volatility)

## Factor Correlation Matrix

| | Momentum | Reversal | Volatility | Turnover | RSI | MACD Hist |
|---|----------|----------|------------|----------|-----|-----------|
| **Momentum** | 1.00 | 0.46 | -0.31 | 0.19 | **0.72** | **0.66** |
| **Reversal** | 0.46 | 1.00 | -0.16 | 0.14 | 0.52 | 0.56 |
| **Volatility** | -0.31 | -0.16 | 1.00 | -0.11 | -0.21 | -0.12 |
| **Turnover** | 0.19 | 0.14 | -0.11 | 1.00 | 0.18 | 0.17 |
| **RSI** | **0.72** | 0.52 | -0.21 | 0.18 | 1.00 | **0.72** |
| **MACD Hist** | **0.66** | 0.56 | -0.12 | 0.17 | **0.72** | 1.00 |

### Correlation Rules of Thumb

| Correlation | Action |
|-------------|--------|
| > 0.65 | **Highly redundant** — keep only the one with higher IC |
| 0.40-0.65 | **Moderately correlated** — consider keeping both if ICs are strong |
| < 0.30 | **Good diversification** — safe to combine |
| < 0.15 | **Orthogonal** — valuable for reducing portfolio factor risk |

### Pruning Strategy

1. Rank factors by |IC|
2. Start with highest |IC| factor
3. Skip any factor with correlation > 0.65 to already-selected factors
4. Continue until 3-5 uncorrelated factors selected

**Example from benchmarks:**
- Select Volatility (|IC|=0.072) ✓
- Select RSI (|IC|=0.032, corr with vol=-0.21) ✓
- Skip Momentum (corr with RSI=0.72) ✗
- Skip MACD Hist (corr with RSI=0.72) ✗
- Skip Reversal (corr with RSI=0.52, borderline) ✗
- Select Turnover (low corr with all, but weak IC) → optional

## Recommended Factor Combinations

### For CSI 300 Momentum Strategy

```python
# IC-weighted composite (optimal)
weights = {
    'volatility': 0.65,   # Negative IC, so use -volatility
    'rsi': 0.30,          # Positive IC
    'turnover': 0.05,     # Negative IC, so use -turnover (or skip)
}

# Composite score calculation
composite = (
    weights['volatility'] * zscore(-volatility) +
    weights['rsi'] * zscore(rsi) +
    weights['turnover'] * zscore(-turnover)
)
```

**Expected Performance:**
- Composite IC: ~0.04-0.06
- Composite IR: ~0.15-0.25
- Hit Rate: ~55%

### Alternative: Volatility + RSI Only

If you want a simpler 2-factor model:

```python
weights = {'volatility': 0.70, 'rsi': 0.30}
```

This captures ~95% of the 3-factor model's IC with less estimation error.

## Factor Decay Monitoring

Monitor these metrics quarterly:

| Metric | Warning Threshold | Action |
|--------|------------------|--------|
| Rolling 3M IC | < 50% of historical mean | Reduce weight by 25% |
| Rolling 3M IR | < 0.5 × historical IR | Investigate regime shift |
| Factor correlation drift | > 0.80 with another factor | Prune one factor |
| Hit rate | < 45% (for positive IC factors) | Consider reversing direction |

## Common Pitfalls

1. **Overweighting momentum factors**: RSI, momentum, and MACD are highly correlated. Don't triple-count the same signal.

2. **Ignoring volatility**: The low-vol anomaly has the strongest |IC| but is often overlooked in "momentum" strategies. It provides crucial diversification.

3. **Including weak factors**: Turnover and similar low-IC factors add noise, not signal. If |IC| < 0.02 and IR < 0.05, exclude it.

4. **Daily rebalancing**: Causes excessive turnover. Use 10-20 day rebalancing cycles for momentum strategies.

5. **Not reversing negative-IC factors**: Volatility has negative IC — you want LOW volatility stocks. Remember to flip the sign.

## Usage Example

```python
# After running factor_analysis on each factor:
import json

factors = ['volatility', 'rsi', 'momentum', 'turnover']
ic_summary = {}

for f in factors:
    with open(f'analysis_{f}/ic_summary.json') as file:
        ic_summary[f] = json.load(file)

# Rank by |IC|
ranked = sorted(ic_summary.items(), key=lambda x: abs(x[1]['ic_mean']), reverse=True)

# Select uncorrelated factors (threshold=0.65)
selected = []
for name, stats in ranked:
    is_uncorrelated = True
    for sel in selected:
        corr = correlation_matrix.loc[name, sel]
        if abs(corr) > 0.65:
            is_uncorrelated = False
            break
    if is_uncorrelated:
        selected.append(name)

# Calculate IC weights
total_ic = sum(abs(ic_summary[f]['ic_mean']) for f in selected[:4])
weights = {f: abs(ic_summary[f]['ic_mean']) / total_ic for f in selected[:4]}
```

## References

- `factor-research` skill: Full workflow for factor IC/IR analysis
- `multi-factor` skill: Signal engine implementation with factor combination
- Output files: `ic_summary.json`, `ic_series.csv`, `group_equity.csv`
