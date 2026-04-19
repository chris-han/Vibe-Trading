---
name: factor-backtest-troubleshooting
description: Diagnose and fix failed multi-factor backtests — IC vs performance gap, high turnover, regime mismatch, and data quality issues.
---

# Factor Backtest Troubleshooting Guide

## When to Use This Skill

Use this when a multi-factor strategy shows **positive cross-sectional IC** but **negative backtest returns**. This is a common failure mode that requires systematic diagnosis.

## Typical Failure Symptoms

| Symptom | Threshold | Interpretation |
|---------|-----------|----------------|
| Negative annual return | < 0% | Strategy loses money |
| Negative excess return | < -5% | Underperforms benchmark significantly |
| Win rate | < 45% | Less than half of trades profitable |
| Profit factor | < 0.8 | Gross losses exceed gross gains |
| Max drawdown | > 20% | Severe peak-to-trough loss |
| Trade count | > 60/year | Excessive turnover |
| Sharpe ratio | < 0 | Negative risk-adjusted returns |

## Root Cause Analysis Framework

### 1. Transaction Cost Drag

**Diagnosis**: High trade count × commission/slippage > factor edge

**Calculation**:
```
Annual cost drag = trade_count × (commission + slippage) × 2
Example: 80 trades/year × 0.2% × 2 = 32% cost drag
```

**Fix**:
- Increase rebalance frequency from 15 days to **20-30 days**
- Add minimum signal change threshold (only trade if weight changes > 3%)
- Reduce TopN concentration (fewer rebalances when stocks drift in/out)

### 2. Factor Regime Mismatch

**Diagnosis**: Factor IC is regime-dependent; strategy was calibrated on one regime but tested across multiple

**Common Patterns**:
- Low-vol anomaly reverses in strong bull markets (2020-2021)
- Momentum crashes during market reversals
- Value factors underperform in growth-dominated regimes

**Fix**:
- Add **market regime filter**: Only go long when index > 200-day MA
- Use **dynamic factor weighting**: Increase vol weight when VIX > 20
- Test on **rolling windows** to identify regime boundaries

### 3. Concentration Risk

**Diagnosis**: Top-10 equal weight creates idiosyncratic exposure; single-stock drawdowns dominate portfolio

**Fix**:
- Expand from Top-10 to **Top-20 or Top-30** (3-5% weight each)
- Add **sector constraints**: Max 20% in any single sector
- Use **risk parity optimizer** instead of equal weight

### 4. Data Quality Issues

**Diagnosis**: Many stocks in universe return no data (delisted, illiquid, or API restrictions)

**Symptoms**:
- Backtest warnings: "no usable data for XXX"
- Effective universe < 50% of intended codes
- Survivorship bias (only successful stocks remain)

**Fix**:
- Filter universe to **liquid large-caps only** (CSI 300 core constituents)
- Switch data source: tushare → yfinance (or vice versa) based on API permissions
- Pre-screen codes: remove any that fail data fetch in pilot test

### 5. Signal Implementation Bugs

**Diagnosis**: Code logic error causes wrong signals

**Checklist**:
- [ ] Factor directions aligned correctly (negative IC factors reversed)
- [ ] Z-score computed cross-sectionally (not time-series)
- [ ] Rebalance logic: signals held constant between rebalance dates
- [ ] TopN selection: exactly N stocks selected, each gets 1/N weight
- [ ] No look-ahead bias (factors use only past data)

## Step-by-Step Debugging Workflow

### Step 1: Verify Data Quality

```python
# After backtest, check how many stocks returned data
# Expectation: >70% of codes should have usable data
# If <50%, reduce universe to liquid names only
```

**Action**: Re-run with smaller, higher-quality universe (e.g., CSI 300 top 100 by market cap)

### Step 2: Analyze Trade Frequency

```
Trade count: 241 over 3 years = 80 trades/year
Target: 30-50 trades/year for daily strategies
```

**Action**: Increase `rebalance_freq` from 15 to 25 days

### Step 3: Check Market Exposure

```
Did strategy stay invested during bear markets?
If yes → add market filter
```

**Action**: Add regime filter in signal_engine.py:
```python
# Only go long if CSI 300 > 200-day MA
market_ma = benchmark_close.rolling(200).mean()
if close.iloc[-1] < market_ma.iloc[-1]:
    return {code: pd.Series(0, index=df.index) for code in data_map}
```

### Step 4: Review Factor Weights

```
Current: Vol 65.7%, RSI 29.4%, Turnover 5.0%
Question: Are these weights optimal for current regime?
```

**Action**: Re-run `factor_analysis` on recent 12-month window; adjust weights if IC rankings changed

### Step 5: Add Risk Controls

**Stop-loss**: Force exit if individual stock loses >10% from entry

**Position limits**: Max 5% per stock instead of 10%

**Sector caps**: Max 20% in any GICS sector

## Improvement Priority Matrix

| Fix | Effort | Impact | Priority |
|-----|--------|--------|----------|
| Increase rebalance period (15→25 days) | Low | High | P0 |
| Add market regime filter | Medium | High | P0 |
| Expand TopN (10→20 stocks) | Low | Medium | P1 |
| Add stop-loss mechanism | Medium | Medium | P1 |
| Dynamic factor weighting | High | Medium | P2 |
| Risk parity optimizer | Low | Low | P2 |

## Pre-Deployment Checklist

Before deploying any multi-factor strategy:

- [ ] Backtest shows positive excess return (> 2% annual)
- [ ] Sharpe ratio > 0.5
- [ ] Max drawdown < 15%
- [ ] Win rate > 50%
- [ ] Profit factor > 1.0
- [ ] Trade count < 50/year
- [ ] Tested across multiple market regimes (bull, bear, sideways)
- [ ] Transaction costs included (commission + slippage ≥ 0.15%)
- [ ] Data quality verified (> 80% codes returned data)

## Key Lessons

1. **IC is necessary but not sufficient**: Cross-sectional predictive power doesn't guarantee time-series portfolio performance
2. **Costs compound quickly**: 0.2% round-trip × 80 trades = 16% annual drag
3. **Regime matters more than factors**: A good factor in the wrong regime loses money
4. **Diversification is free lunch**: Top-10 concentration adds risk without commensurate return
5. **Simple filters beat complex models**: 200-day MA market filter often adds more value than ML optimization

## Related Skills

- `multi-factor`: Core multi-factor ranking implementation
- `factor-research`: IC/IR analysis and factor validation
- `backtest-diagnose`: General backtest failure diagnosis
- `risk-analysis`: Drawdown and risk metric analysis
