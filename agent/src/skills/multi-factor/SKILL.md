---
name: multi-factor
description: Multi-factor cross-sectional stock ranking. Combines factor standardization, equal-weight or IC-weighted scoring, and TopN portfolio construction. Suitable for multi-instrument portfolio strategies.
---
# Multi-Factor Cross-Sectional Stock Ranking

## Purpose

On the same time cross-section, compute multiple factor values for many stocks, standardize them, combine them into a composite score, and select the top-ranked stocks to build a portfolio.

## Signal Logic

1. **Factor calculation**: calculate N factors for each stock (such as momentum, value, and quality)
2. **Cross-sectional standardization**: standardize each factor on the cross-section with Z-score normalization (subtract mean, divide by standard deviation)
3. **Composite scoring**: sum the factors with equal weights (or custom weights) to obtain a composite score
4. **Rank and select**: go long the TopN names, with weight = 1/N for each

## Built-In Factors

| Factor Name | Calculation Method | Direction |
|--------|---------|------|
| momentum | Return over the past N days | Positive (higher is better) |
| reversal | Return over the past 5 days | Negative (lower is better) |
| volatility | Standard deviation of returns over the past N days | Negative (lower is better) |
| volume_ratio | Today's volume / N-day average volume | Positive |

If `extra_fields` are available (China A-shares), you can also add:
- `pe_factor`: 1/PE (the larger, the cheaper)
- `pb_factor`: 1/PB
- `roe_factor`: ROE (the larger, the better)

## Parameters

| Parameter | Default | Description |
|------|--------|------|
| momentum_window | 20 | Momentum lookback window |
| vol_window | 20 | Volatility lookback window |
| top_n | 3 | Number of selected stocks |
| rebalance_freq | 20 | Rebalancing frequency (trading days) |

## IC-Weighted Factor Synthesis

For optimal factor combination, use IC-based weights from empirical analysis:

### Weight Calculation Formula
```
weight_i = |IC_mean_i| / sum(|IC_mean_j|)
Composite score = sum(weight_i * Z(factor_i))
```

### Typical Factor IC Rankings (China A-shares)
Based on empirical testing on CSI 300 constituents (2023-2024):

| Factor | Typical IC | Recommended Weight |
|--------|-----------|-------------------|
| Volatility | 0.08-0.10 | 35-40% |
| Turnover | -0.06 to -0.07 | 25-30% |
| Momentum | 0.04-0.05 | 20-25% |
| Reversal | -0.03 to -0.04 | 10-15% |

### Implementation Tips
- **Fixed weights > Rolling IC**: With limited universes (<50 stocks), fixed IC weights from historical analysis are more stable than rolling IC estimation
- **Run factor_analysis first**: Before deploying, run `factor_analysis` tool on each factor to get empirical IC/IR
- **Rebalance frequency**: Use 10-20 trading days to reduce turnover (daily rebalancing causes excessive trading)
- **Holding cap**: Limit to 3-10 stocks for focused exposure

## Common Pitfalls

- Cross-sectional standardization requires at least 3 stocks, otherwise Z-scores are meaningless
- Keep the previous signal unchanged between rebalance dates (do not rerank every day)
- Factors have different directions: momentum is positively sorted, volatility is negatively sorted, so directions must be aligned before standardization
- Portfolio weights must be normalized: each TopN stock gets 1/N, all others get 0

## Dependencies

```bash
pip install pandas numpy
```

## Data Source Notes

- **Tushare**: Requires API token authentication. If you get "no permission" errors, switch to yfinance
- **yfinance**: Free, no auth required. Use for global stocks (US, HK, A-shares via .SS/.SZ suffixes)
- **Universe size**: For meaningful IC calculation, use at least 20-30 stocks. Full CSI 300 preferred.

## Signal Convention

- `1/N` = selected into TopN (equal-weight long), `0` = not selected
