---
name: factor-ic-validation
description: Validate factor ICs empirically before deploying multi-factor models — literature values are reference only, actual ICs vary by data source and universe.
---

# Factor IC Validation: Empirical Analysis Before Deployment

## Purpose

Before deploying a multi-factor model, always validate factor ICs (Information Coefficients) empirically on your specific data. Literature IC values are reference only — actual ICs vary significantly by:
- Data source (tushare vs yfinance vs other providers)
- Universe composition (CSI 300 vs S&P 500 vs custom)
- Factor calculation method (windows, transformations)
- Time period (market regime matters)

## Workflow

### Step 1: Calculate Individual Factors
Extract each factor separately into its own CSV file:

```python
# For each factor (momentum, reversal, volatility, turnover, etc.)
factor_df = pd.DataFrame(index=all_dates)
for code, df in data_map.items():
    factor_df[code] = df[factor_name]
factor_df.to_csv(f'factors_{factor_name}.csv')
```

### Step 2: Calculate Forward Returns
Compute forward returns (1-day or N-day) aligned with factor dates:

```python
# Factor at day T, return from T close to T+1 close (no look-ahead)
return_df = pd.DataFrame(index=all_dates[:-1])
for code, df in data_map.items():
    returns = []
    for i, date in enumerate(all_dates[:-1]):
        current_idx = df.index.get_loc(date)
        if current_idx + 1 < len(df):
            next_date = df.index[current_idx + 1]
            ret = df.loc[next_date, 'close'] / df.loc[date, 'close'] - 1
            returns.append(ret)
        else:
            returns.append(np.nan)
    return_df[code] = returns
return_df.to_csv('returns_1d.csv')
```

### Step 3: Run Factor Analysis Tool
Call `factor_analysis` for each factor:

```bash
factor_analysis \
  --factor_csv factors_volatility.csv \
  --return_csv returns_1d.csv \
  --output_dir analysis_volatility \
  --n_groups 5
```

### Step 4: Interpret Results

| Metric | Threshold | Interpretation |
|--------|-----------|----------------|
| IC mean | > 0.03 | Factor has basic predictive power |
| IC mean | > 0.05 | Strong predictive power |
| IC mean | < -0.03 | Negative factor (flip sign for use) |
| IR (IC/IC_std) | > 0.5 | Stably effective |
| IC positive ratio | > 55% | Stable direction |

**Critical**: Negative IC is still useful — just flip the sign when combining factors.

### Step 5: Calculate IC-Weighted Synthesis

```python
# Example empirical IC results (yfinance CSI 300, 2023-2024)
ic_values = {
    'volatility': -0.0584,   # Negative IC: low vol outperforms
    'turnover': -0.0156,     # Negative IC: low turnover outperforms
    'momentum': -0.0098,     # Slightly negative
    'reversal': 0.0011       # Near zero (weak factor)
}

# Calculate weights proportional to absolute IC
total_ic = sum(abs(ic) for ic in ic_values.values())
weights = {f: abs(ic) / total_ic for f, ic in ic_values.items()}
# Result: volatility=68%, turnover=18%, momentum=12%, reversal=1%

# In signal engine, flip negative factors:
composite = (
    weights['volatility'] * (-Z(volatility)) +   # Flip negative IC
    weights['turnover'] * (-Z(turnover)) +       # Flip negative IC
    weights['momentum'] * (-Z(momentum)) +       # Flip negative IC
    weights['reversal'] * (Z(reversal))          # Positive IC stays positive
)
```

## Case Study: CSI 300 Multi-Factor (2023-2024)

### Expected vs Actual IC

| Factor | Literature IC | Actual IC (yfinance) | Action |
|--------|--------------|---------------------|--------|
| Volatility | +0.08 | -0.058 | Flip sign, highest weight |
| Turnover | -0.065 | -0.016 | Keep negative, moderate weight |
| Momentum | +0.047 | -0.010 | Flip sign, low weight |
| Reversal | -0.035 | +0.001 | Near zero, minimal weight |

### Backtest Results

| Metric | Value |
|--------|-------|
| Total Return | +56.8% |
| Annual Return | +26.4% |
| Max Drawdown | -8.4% |
| Sharpe Ratio | 1.77 |
| Calmar Ratio | 3.16 |
| Benchmark Return | +9.8% |
| Excess Return | +47.0% |
| Information Ratio | 1.27 |

## Common Pitfalls

### 1. Using Literature ICs Without Validation
**Problem**: Documentation suggests volatility IC ~0.08, but your data shows -0.058.
**Solution**: Always run `factor_analysis` on your specific dataset before setting weights.

### 2. Ignoring IC Sign
**Problem**: Using negative IC factors with positive weights destroys alpha.
**Solution**: Check IC sign for each factor. Flip the sign in composite calculation if IC is negative.

### 3. Look-Ahead Bias in Returns
**Problem**: Calculating returns from same day as factor (T return with T factor).
**Solution**: Factor at day T close, return from T close to T+1 close.

### 4. Insufficient Sample Size
**Problem**: IC computed on <20 stocks is noisy and unreliable.
**Solution**: Use at least 50+ stocks for meaningful IC statistics. CSI 300 (300 stocks) is ideal.

### 5. Ignoring Factor Decay
**Problem**: 1-day IC may not reflect N-day holding period performance.
**Solution**: Run factor_analysis with different return horizons (1d, 5d, 20d) to find optimal holding period.

## Dependencies

```bash
pip install pandas numpy scipy
```

## Files Generated by factor_analysis

| File | Contents |
|------|----------|
| ic_series.csv | Daily IC time series |
| ic_summary.json | IC mean, IC std, IR, IC positive ratio |
| group_equity.csv | Cumulative returns for each quantile group |

## When to Re-Validate

- **New data source**: Switching from tushare to yfinance? Re-run IC analysis.
- **Universe change**: Moving from CSI 300 to CSI 500? Re-run IC analysis.
- **Regime shift**: After major market events (e.g., 2020 crash, 2022 bear market)? Re-run IC analysis.
- **Quarterly review**: ICs can decay over time. Review quarterly.
