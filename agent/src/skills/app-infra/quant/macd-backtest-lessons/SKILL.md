---
name: macd-backtest-lessons
description: MACD strategy backtesting lessons — parameter selection, common pitfalls, and when MACD fails vs buy-and-hold
---

## Key Findings from MSFT MACD Backtest (2016-2026)

### Parameter Sensitivity

| Parameter Set | Trading Days | Trades | Total Return | Annual Return | Max DD |
|--------------|--------------|--------|--------------|---------------|--------|
| (60,130,45) "weekly" | ~10 years | 1 | +656% | +21.8% | -37.6% |
| (12,26,9) standard | Daily | 114 | -21.6% | -2.3% | -44.9% |
| (24,52,18)+200DMA | Daily | 52 | +23.2% | +2.1% | -30.7% |
| **Buy-and-hold benchmark** | N/A | 1 | **+650%** | **+21.6%** | **-37.6%** |

### Critical Insights

#### 1. MACD Underperforms on Strong Trending Stocks

**Finding**: MSFT gained 650% over 10 years. Any timing strategy that exits during the trend massively underperforms.

**Why MACD fails**:
- MACD is a **lagging indicator** — signals occur after price has already moved
- **Whipsaw in consolidation** — 2016-2018 produced repeated false signals
- **Missed compounding** — being out during major rallies cannot be recovered
- **Transaction costs** — 114 trades × 0.1% commission = ~11% drag

**When to use MACD**:
- ✅ Range-bound / oscillating markets
- ✅ Mean-reverting stocks (high volatility, no clear trend)
- ✅ Short-term tactical overlays on core positions
- ❌ Strong secular growth stocks (MSFT, NVDA, AAPL long-term)
- ❌ Buy-and-hold portfolios

#### 2. Parameter Selection Guidelines

```
Fast parameters (12,26,9):
  - Pros: Catches moves early
  - Cons: Many false signals, high turnover
  - Best for: Short-term trading, high-volatility stocks

Medium parameters (24,52,18):
  - Pros: Fewer false signals, better risk-adjusted returns
  - Cons: Still underperforms strong trends
  - Best for: Swing trading, medium-term positions

Slow parameters (60,130,45):
  - Pros: Captures major trends, low turnover
  - Cons: May only trade once per decade
  - Best for: Long-term tactical overlays

Rule of thumb: 
  - Daily trading: (12,26,9) or (24,52,18)
  - Weekly simulation: Multiply by 2-5× daily parameters
  - Always test against buy-and-hold benchmark
```

#### 3. Essential Filters to Add

| Filter | Purpose | Implementation |
|--------|---------|----------------|
| **200-day MA** | Trade only with long-term trend | `close > close.rolling(200).mean()` |
| **ADX > 25** | Confirm trend strength | `adx > 25` for directional trades |
| **Volume filter** | Avoid low-liquidity signals | `volume > volume.rolling(20).mean()` |
| **ATR stop-loss** | Limit downside | Exit if loss > 2× ATR |
| **Time stop** | Exit stagnant positions | Close if no profit after N days |

#### 4. Backtest Workflow for MACD Strategies

```python
# 1. Always compare against buy-and-hold benchmark
benchmark_return = (price[-1] / price[0]) - 1

# 2. Check these metrics before accepting strategy:
required_checks = {
    'trade_count': '> 10',  # Statistical significance
    'sharpe': '> 0.5',      # Risk-adjusted returns
    'max_drawdown': '< -30%',  # Acceptable risk
    'vs_benchmark': 'positive or close',  # Don't massively underperform
}

# 3. If strategy underperforms buy-and-hold by >10% annually:
#    → Question whether timing adds value for this asset
```

#### 5. Asset-Specific Recommendations

| Asset Type | MACD Effectiveness | Recommended Approach |
|------------|-------------------|---------------------|
| **Tech growth (MSFT, NVDA)** | ❌ Poor | Buy-and-hold core + small tactical overlay |
| **Cyclical stocks** | ⚠️ Mixed | Add sector/trend filters |
| **Commodities** | ✅ Good | Mean-reverting, MACD works well |
| **FX pairs** | ✅ Good | Range-bound, MACD effective |
| **Crypto** | ⚠️ Mixed | High volatility, needs wider stops |
| **Index ETFs** | ⚠️ Mixed | Depends on market regime |

### Common Pitfalls

1. **Overfitting parameters** — Optimizing (12,26,9) to (11,28,7) rarely helps out-of-sample
2. **Ignoring transaction costs** — High turnover strategies die from commission + slippage
3. **No benchmark comparison** — Always test vs buy-and-hold
4. **Wrong asset class** — MACD works better on mean-reverting vs trending assets
5. **Signal lag** — By the time MACD crosses, 30-50% of the move may already be done

### When to Abandon MACD for a Stock

Exit signal for the strategy itself (not the trade):

```
IF (strategy_annual_return < benchmark_annual_return - 5%) 
   AND (trade_count > 50) 
   AND (backtest_period > 5 years):
   → MACD does not add value for this asset
   → Consider: buy-and-hold, or different strategy (momentum, mean-reversion)
```

### Quick Start Template

```python
import pandas as pd
import numpy as np
from typing import Dict

class SignalEngine:
    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        signals = {}
        
        for code, df in data_map.items():
            if df.empty:
                signals[code] = pd.Series(index=df.index, data=0.0)
                continue
            
            # Parameters
            ema_short, ema_long, signal_period = 12, 26, 9
            
            close = df['close']
            
            # MACD calculation
            ema_fast = close.ewm(span=ema_short, adjust=False).mean()
            ema_slow = close.ewm(span=ema_long, adjust=False).mean()
            macd = ema_fast - ema_slow
            signal_line = macd.ewm(span=signal_period, adjust=False).mean()
            
            # Signals
            bullish = (macd > signal_line) & (macd.shift(1) <= signal_line.shift(1))
            bearish = (macd < signal_line) & (macd.shift(1) >= signal_line.shift(1))
            
            # Position
            position = pd.Series(index=df.index, data=np.nan)
            position[bullish] = 1.0
            position[bearish] = 0.0
            position = position.ffill().fillna(0.0)
            
            signals[code] = position
        
        return signals
```

## References

- MSFT backtest results (2016-2026): Standard MACD -21.6% vs Buy-and-hold +650%
- Optimized version with 200-day MA filter: +23.2% (still underperforms)
- Conclusion: For strong trending stocks, timing strategies cannot capture full upside