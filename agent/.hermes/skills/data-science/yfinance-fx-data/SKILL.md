---
name: yfinance-fx-data
description: Fetch and clean FX data using yfinance with proper multi-index column handling
category: data-science
tags: [yfinance, fx, data-cleaning, pandas]
---

# yfinance FX Data Handling

## Overview

Fetch and clean FX (foreign exchange) data using yfinance. Covers the critical multi-index column handling issue that causes `KeyError` when accessing columns like 'Close'.

## Core Problem

yfinance returns DataFrames with **multi-index columns** for many tickers (especially futures like DXY `DX-Y.NYB` and some FX pairs). Direct column access like `df['Close']` fails with `KeyError: 'Close'`.

**Signs you have multi-index columns:**
- `KeyError: 'Close'` when accessing `df['Close']`
- Columns show as `MultiIndex([('Close', 'DX-Y.NYB'), ...])`
- Common with: futures (`DX-Y.NYB`), some FX pairs, indices

## Solution: Flatten Columns

```python
import yfinance as yf
import pandas as pd

def get_df_clean(ticker, start, end):
    """Download and flatten yfinance data for FX/futures"""
    df = yf.download(ticker, start=start, end=end, progress=False)
    if df is None or df.empty:
        return None
    
    # Flatten multi-index columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in df.columns]
        # Rename to simple column names
        df = df.rename(columns={
            f"Close_{ticker}": "Close",
            f"Open_{ticker}": "Open", 
            f"High_{ticker}": "High",
            f"Low_{ticker}": "Low",
            f"Volume_{ticker}": "Volume"
        })
    return df

# Usage example
dxy_df = get_df_clean("DX-Y.NYB", "2026-01-01", "2026-04-12")
current = float(dxy_df['Close'].iloc[-1])  # Now works correctly
```

## FX Ticker Reference

| Currency Pair | yfinance Ticker | Notes |
|---------------|-----------------|-------|
| Dollar Index (DXY) | `DX-Y.NYB` | Futures contract, multi-index columns |
| USD/CNY (onshore) | `CNY=X` | May have multi-index |
| USD/CNH (offshore) | `CNH=X` | May have multi-index |
| USD/HKD | `HKD=X` | Pegged currency |
| EUR/USD | `EURUSD=X` | Major pair |
| USD/JPY | `JPY=X` | Major pair, watch BOJ intervention |
| GBP/USD | `GBPUSD=X` | Major pair |
| USD/CHF | `USDCHF=X` | Safe haven pair |
| AUD/USD | `AUDUSD=X` | Commodity currency |
| USD/CAD | `USDCAD=X` | Commodity currency |

## Complete Analysis Template

```python
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

def get_df_clean(ticker, start, end):
    """Download and flatten yfinance data"""
    df = yf.download(ticker, start=start, end=end, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in df.columns]
        df = df.rename(columns={
            f"Close_{ticker}": "Close",
            f"Open_{ticker}": "Open", 
            f"High_{ticker}": "High",
            f"Low_{ticker}": "Low",
            f"Volume_{ticker}": "Volume"
        })
    return df

# Setup dates
end_date = datetime.now()
start_date_30d = end_date - timedelta(days=30)

# Fetch FX data
fx_data = {}
for name, ticker in {'DXY': 'DX-Y.NYB', 'USD/CNY': 'CNY=X'}.items():
    df = get_df_clean(ticker, start_date_30d.strftime('%Y-%m-%d'), 
                     end_date.strftime('%Y-%m-%d'))
    if df is not None and not df.empty:
        fx_data[name] = df
        current = float(df['Close'].iloc[-1])
        prev = float(df['Close'].iloc[0])
        change_pct = ((current - prev) / prev) * 100
        print(f"{name}: {current:.4f} ({change_pct:+.2f}%)")
```

## Key Analysis Patterns

### 1. Moving Averages
```python
dxy_df['MA5'] = dxy_df['Close'].rolling(5).mean()
dxy_df['MA20'] = dxy_df['Close'].rolling(20).mean()
current = float(dxy_df['Close'].iloc[-1])
ma20 = float(dxy_df['MA20'].iloc[-1])
signal = 'Above' if current > ma20 else 'Below'
```

### 2. Range Analysis
```python
high_30d = float(df['High'].max())
low_30d = float(df['Low'].min())
current = float(df['Close'].iloc[-1])
position = (current - low_30d) / (high_30d - low_30d) * 100
```

### 3. Correlation Between Pairs
```python
dxy_ret = dxy_df['Close'].pct_change().dropna()
btc_ret = btc_df['Close'].pct_change().dropna()
min_len = min(len(dxy_ret), len(btc_ret))
corr = dxy_ret.iloc[-min_len:].corr(btc_ret.iloc[-min_len:])
```

## Pitfalls

1. **Always check for multi-index**: Run `print(df.columns)` after download
2. **Use `.copy()` before adding columns**: `df = df.copy()` then `df['MA5'] = ...`
3. **Convert to float explicitly**: `float(df['Close'].iloc[-1])` not `df['Close'].iloc[-1]`
4. **Handle empty DataFrames**: Check `if df is not None and not df.empty`
5. **FX markets close**: Weekend data may be stale; use appropriate date ranges

## Related Tickers

| Asset Class | Tickers |
|-------------|---------|
| US Equity | `SPY`, `QQQ`, `^GSPC`, `^IXIC` |
| Bonds | `TLT` (20Y), `^TNX` (10Y yield) |
| Gold | `GLD` |
| Volatility | `^VIX` |
| Crypto | `BTC-USD`, `ETH-USD` |

## Notes

- yfinance is free, no API key required
- Rate limits may apply for high-frequency requests
- Futures data (like DXY) may have gaps on weekends/holidays
- For production use, consider dedicated FX data providers (Refinitiv, Bloomberg)
