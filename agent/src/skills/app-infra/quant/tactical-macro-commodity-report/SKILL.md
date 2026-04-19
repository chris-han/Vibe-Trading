---
name: tactical-macro-commodity-report
description: Generate tactical macro environment and commodity analysis reports with asset allocation recommendations for 1-3 month horizons
category: quant
---

# Tactical Macro & Commodity Analysis Report

## Overview

Generate comprehensive Q2 2026-style macro environment analysis combining programmatic market data fetching with web research for fundamental indicators. Outputs tactical asset allocation recommendations for 1-3 month horizon.

## When to Use

- User requests macro environment analysis (Fed policy, inflation, growth, asset allocation)
- Quarterly or monthly tactical outlook needed
- Commodity/inflation dynamics are central to the question
- Need to synthesize market data + fundamental research into actionable recommendations

## Workflow

### Step 1: Fetch Current Market Data (yfinance)

```python
#!/usr/bin/env python3
import yfinance as yf
import json
from datetime import datetime

COMMODITIES = {
    'WTI': 'CL=F', 'Brent': 'BZ=F', 'Natural_Gas': 'NG=F',
    'Gold': 'GC=F', 'Silver': 'SI=F', 'Copper': 'HG=F',
}
MACRO = {
    'DXY': 'DX-Y.NYB', 'VIX': '^VIX', 'TNX': '^TNX',
    'TLT': 'TLT', 'SPY': 'SPY',
}

def fetch_data(tickers, period='3mo'):
    data = {}
    for name, ticker in tickers.items():
        try:
            obj = yf.Ticker(ticker)
            hist = obj.history(period=period)
            if not hist.empty:
                data[name] = {
                    'current': hist['Close'].iloc[-1],
                    'change_pct': ((hist['Close'].iloc[-1] / hist['Close'].iloc[0]) - 1) * 100,
                }
        except Exception as e:
            print(f"✗ {name}: {e}")
    return data
```

### Step 2: Web Research for Fundamentals

Search for:
- **Fed policy**: "FOMC projections [current quarter] [year]", "Federal Reserve interest rate policy outlook"
- **Inflation data**: "US CPI PCE inflation [month] [year]", "core PCE Federal Reserve"
- **Commodity fundamentals**: 
  - Oil: "WTI crude OPEC production [year] Iran Israel conflict"
  - Gold: "central bank gold buying [year] WGC"
  - Copper: "copper demand China economic indicator"
- **Global growth**: "China CPI PPI [month] [year] GDP forecast"

### Step 3: Structure the Report

```
## I. ENERGY COMPLEX
- Current prices + 3M changes
- Supply-demand balance (supply, OPEC stance, demand, key risks)
- Inflation transmission mechanism

## II. METALS
- Gold: price, central bank buying, real rates impact
- Silver: industrial vs monetary demand
- Copper: Dr. Copper economic signal, China demand

## III. INFLATION ASSESSMENT
- US: Core PCE YoY/MoM, CPI, Fed stance/projections
- China: CPI, PPI, GDP forecast
- Stagflation risk evaluation

## IV. ASSET ALLOCATION IMPLICATIONS
- Overweight: assets + rationale + weight adjustment
- Neutral: assets + rationale
- Underweight: assets + rationale + weight adjustment

## V. SCENARIO ANALYSIS
- Base case (50%): description, implications
- Bull case (20%): description, implications
- Bear case (30%): description, implications

## EXECUTIVE SUMMARY
- 5 key findings (numbered)
- Tactical recommendations (bullet points)
- Key monitoring triggers
```

### Step 4: Scoring Framework

Use commodity-analysis skill framework for scoring:

```python
commodity_score = {
    "supply_demand": +1,    # -2 to +2
    "inventory_cycle": +2,  # -2 to +2
    "term_structure": +1,   # -2 to +2
    "seasonality": 0,       # -2 to +2
    "macro_env": -1,        # -2 to +2
}
# Total: -10 to +10, map to bullish/bearish/neutral
```

### Step 5: Asset Allocation Mapping

| Macro Regime | Overweight | Underweight |
|--------------|------------|-------------|
| Rising inflation + growth | Commodities, cyclicals, TIPS | Long bonds, defensive |
| Stagflation | Gold, energy, defensives, TIPS | Long bonds, growth stocks |
| Disinflation + growth | Growth stocks, long bonds | Commodities, value |
| Deflation + recession | Long bonds, USD, defensives | Equities, commodities, EM |

## Key Data Sources

| Data Type | Source | Frequency |
|-----------|--------|-----------|
| Commodity prices | yfinance (futures) | Real-time |
| Fed projections | federalreserve.gov (FOMC SEP) | Quarterly |
| US inflation | BLS (CPI), BEA (PCE) | Monthly |
| China data | NBS, Trading Economics | Monthly |
| Central bank gold | WGC quarterly reports | Quarterly |
| Oil supply/demand | IEA OMR, OPEC reports | Monthly |

## Pitfalls

1. **PDF access issues**: BLS/fed PDFs may return 403 via web_extract — use web_search snippets instead
2. **yfinance symbol changes**: Treasury yield symbols (^UST10Y, ^UST2Y) may be delisted — have fallbacks
3. **Conflicting data**: Web sources may disagree on inflation figures — cite specific source/date
4. **Forward-looking statements**: Clearly label projections vs. realized data
5. **Geopolitical sensitivity**: Oil analysis requires monitoring headlines — note conflict risk explicitly

## Output Quality Checklist

- [ ] All prices have 3-month change percentages
- [ ] Fed policy stance clearly stated with rate projection
- [ ] Inflation data includes both YoY and MoM
- [ ] Asset allocation has specific weight adjustments (+/- %)
- [ ] Scenarios have probabilities summing to 100%
- [ ] Key monitoring triggers are actionable/specific
- [ ] Executive summary is skimmable (5 key findings max)

## Example Commands

```bash
# Fetch market data
python commodity_analysis.py

# Generate report
python final_report.py
```

## Related Skills

- `commodity-analysis`: Supply-demand framework for individual commodities
- `global-macro`: Central bank policy, exchange rate, geopolitics framework
- `detailed-risk-analysis`: Risk assessment methodology

## Notes

- This skill produces research reports, not trading signals
- Always verify yfinance data against known benchmarks (e.g., oil should be ~$70-100 in normal markets)
- Web search results may be truncated — use multiple queries for comprehensive coverage
- For backtesting integration, export signals to CSV compatible with factor_analysis skill
