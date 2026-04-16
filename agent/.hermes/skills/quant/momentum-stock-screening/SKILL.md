---
name: momentum-stock-screening
description: Screen equity universes for momentum strategy candidates using multi-factor momentum signals, liquidity filters, and fundamental overlays
category: quant
tags: [momentum, screening, equities, yfinance, tushare, quantitative]
---

# Momentum Stock Screening

## Overview

Systematic screening workflow for identifying momentum strategy candidates. Uses a multi-stage funnel: universe → liquidity filter → momentum filter → composite ranking → fundamental overlay.

## Core Workflow

### Stage 1: Define Universe
- **True A-shares**: Use tushare API with CSI 300/500/1000 constituent lists
- **Proxy universe**: Use yfinance with ADRs + HK listings when tushare unavailable
- **Typical size**: 300-500 stocks for major indices

### Stage 2: Data Collection
```python
import yfinance as yf
import pandas as pd

def fetch_price_data(ticker, period='2y'):
    """Fetch price data with multi-index handling"""
    df = yf.download(ticker, period=period, progress=False)
    if df is None or df.empty:
        return None
    
    # CRITICAL: Handle multi-index columns (common with HK stocks, futures)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in df.columns]
        df = df.rename(columns={
            f"Close_{ticker}": "Close",
            f"Volume_{ticker}": "Volume"
        })
    
    # Ensure Close column exists
    if 'Close' not in df.columns:
        close_cols = [c for c in df.columns if 'Close' in str(c)]
        if close_cols:
            df = df.rename(columns={close_cols[0]: 'Close'})
    
    return df

def fetch_fundamentals(ticker):
    """Fetch fundamental metrics"""
    stock = yf.Ticker(ticker)
    info = stock.info
    return {
        'pe_ratio': info.get('trailingPE'),
        'pb_ratio': info.get('priceToBook'),
        'roe': info.get('returnOnEquity'),
        'market_cap': info.get('marketCap'),
        'dividend_yield': info.get('dividendYield'),
        'beta': info.get('beta'),
    }
```

### Stage 3: Momentum Factor Calculation
```python
def calculate_momentum_factors(df):
    """Calculate momentum factors for ranking"""
    close = df['Close'].dropna()
    
    # 12-month momentum excluding recent 1 month (classic momentum)
    if len(close) >= 252:
        mom_12m_excl_1m = (close.iloc[-21] / close.iloc[-252]) - 1
    else:
        mom_12m_excl_1m = np.nan
    
    # 6-month momentum
    if len(close) >= 126:
        mom_6m = (close.iloc[-1] / close.iloc[-126]) - 1
    else:
        mom_6m = np.nan
    
    # 3-month momentum
    if len(close) >= 63:
        mom_3m = (close.iloc[-1] / close.iloc[-63]) - 1
    else:
        mom_3m = np.nan
    
    # Volatility (annualized)
    daily_ret = close.pct_change()
    volatility = daily_ret.std() * np.sqrt(252)
    
    return {
        'mom_12m_excl_1m': mom_12m_excl_1m,
        'mom_6m': mom_6m,
        'mom_3m': mom_3m,
        'volatility': volatility,
        'avg_volume': df['Volume'].mean(),
    }
```

### Stage 4: Screening Funnel
```python
# Typical thresholds
LIQUIDITY_THRESHOLD = 0.5  # 50% of median volume
MOMENTUM_THRESHOLD = -0.60  # Exclude extreme losers (>60% decline)
TOP_N = 20  # Final candidate count

# Funnel stages:
# 1. Initial universe (e.g., 300 stocks)
# 2. After data fetch (remove failed downloads)
# 3. After liquidity filter (remove illiquid stocks)
# 4. After momentum filter (remove extreme losers)
# 5. Final ranked candidates
```

### Stage 5: Composite Scoring & Ranking
```python
def calculate_composite_score(row):
    """Weighted composite momentum score with NaN handling"""
    if pd.notna(row['mom_12m_excl_1m']):
        # Full formula when 12M data available
        return (0.5 * row['mom_12m_excl_1m'] + 
                0.3 * row['mom_6m'] + 
                0.2 * row['mom_3m'])
    else:
        # Fallback to 6M/3M only
        return (0.6 * row['mom_6m'] + 
                0.4 * row['mom_3m'])

df_results['momentum_score'] = df_results.apply(calculate_composite_score, axis=1)
df_results = df_results.sort_values('momentum_score', ascending=False)
top_candidates = df_results.head(TOP_N)
```

## Common Pitfalls & Solutions

### 1. Multi-Index Column Error
**Symptom**: `KeyError: 'Close'` when accessing `df['Close']`
**Cause**: yfinance returns MultiIndex columns for HK stocks, futures, some ADRs
**Fix**: Flatten columns immediately after download (see `fetch_price_data` above)

### 2. NaN Momentum Values
**Symptom**: All 12-month momentum values are NaN
**Cause**: Insufficient data period (1y not enough for 252 trading days)
**Fix**: Use `period='2y'` minimum; add fallback scoring using 6M/3M only

### 3. Overly Strict Filters
**Symptom**: Zero candidates after momentum filter
**Cause**: Requiring positive momentum in bear markets eliminates all stocks
**Fix**: Use relative thresholds (e.g., >-60%) instead of absolute (>0%)

### 4. Empty DataFrame Output
**Symptom**: `OSError: Cannot save file into a non-existent directory`
**Cause**: Output path doesn't exist
**Fix**: Use absolute paths or ensure directory exists before `to_csv()`

## Momentum Factor Definitions

| Factor | Calculation | Rationale |
|--------|-------------|-----------|
| 12M-1M | (Price 11 months ago / Price 12 months ago) - 1 | Classic momentum, excludes recent reversal |
| 6M | (Current price / Price 6 months ago) - 1 | Medium-term trend |
| 3M | (Current price / Price 3 months ago) - 1 | Short-term acceleration |
| Composite | 50%×(12M-1M) + 30%×(6M) + 20%×(3M) | Weighted combination |

## Fundamental Overlay (Optional)

Add value/quality filters to momentum screen:
- **PE ratio**: < 30 (exclude extreme valuations)
- **ROE**: > 5% (profitable companies)
- **Market cap**: > $1B (liquidity/safety)
- **Beta**: < 1.5 (risk control)

## Output Format

```csv
code,name,current_price,mom_12m_excl_1m,mom_6m,mom_3m,momentum_score,pe_ratio,pb_ratio,roe,market_cap,beta
NIO,NIO Inc,6.47,0.787,-0.036,0.334,0.449,,26.5,-1.187,16360424448,0.99
2318.HK,Ping An Insurance,63.30,0.393,0.189,-0.098,0.233,7.4,1.0,0.116,1257524297728,0.77
```

## Data Provider Notes

| Provider | Coverage | API Key | Best For |
|----------|----------|---------|----------|
| tushare | True A-shares | Required | Production A-share screening |
| yfinance | ADRs + HK listings | None | Quick screening, international proxies |
| akshare | A-shares | None | China domestic data (alternative to tushare) |

## Related Skills

- `multi-factor-alpha`: IC-based dynamic factor weighting for portfolio construction
- `portfolio-optimizer-comparison`: Compare optimizers after candidate selection
