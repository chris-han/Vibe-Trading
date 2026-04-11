---
name: bull-side-research
description: Systematic multi-dimensional bull-side stock research framework — technical, valuation, fundamental, and sentiment analysis for upside thesis building. Complements bear-side-research.
category: research
tags: [stocks, research, bull-case, valuation, technical-analysis, sentiment]
---

# Bull-Side Stock Research Framework

## Purpose

Systematic multi-dimensional bull-side research methodology for identifying upside potential, growth catalysts, and fundamental strengths in individual stocks. Combines technical analysis, valuation assessment, fundamental trend analysis, and sentiment/positioning metrics into a comprehensive bull case.

## When to Use

- User requests bull-side research on a specific stock
- Building long investment thesis
- Investment committee bull analyst role
- Pre-trade opportunity assessment
- Complementing bear-side analysis for balanced view

## Six-Dimension Framework

| Dimension | Key Metrics | Bullish Signals |
|-----------|-------------|-----------------|
| **1. Technical** | RSI, MA Stack, MACD, Volume, Support/Resistance | Price > all MAs, MACD golden cross, RSI 40-70 (healthy), Volume expanding on rallies |
| **2. Valuation** | P/E, PEG, Forward P/E, EV/Sales vs growth | Forward P/E < growth rate (PEG <1), Discount to peers despite superior growth |
| **3. Fundamental** | Revenue growth, Margin trends, ROE/ROIC | Revenue growth >30%, Expanding margins, ROE >20%, FCF growth |
| **4. Sentiment** | Put/Call Ratio, Short Interest, Institutional flows | PCR <0.7, Low short interest (<3%), Institutional accumulation |
| **5. Catalysts** | Earnings, Product launches, Industry events | Near-term catalysts identified, Positive guidance expected |
| **6. Competitive Moat** | Market share, Switching costs, Network effects | Dominant position (>50% share), High switching costs, Ecosystem lock-in |

## Implementation Steps

### Step 1: Data Fetching (yfinance)

```python
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

ticker = yf.Ticker("SYMBOL")
end_date = datetime.now()
start_date = end_date - timedelta(days=730)  # 2 years for technical analysis

df = yf.download("SYMBOL", start=start_date.strftime("%Y-%m-%d"), 
                 end=end_date.strftime("%Y-%m-%d"), progress=False)

# CRITICAL: Handle MultiIndex columns (yfinance quirk)
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.droplevel(1)  # Drop ticker level

info = ticker.info  # Fundamental snapshot
financials = ticker.financials
quarterly_financials = ticker.quarterly_financials
institutional = ticker.institutional_holders
recommendations = ticker.recommendations
```

**Pitfall Avoidance:**
- Always check for MultiIndex columns before accessing column names
- Calculate ALL technical indicators BEFORE extracting values from latest row
- Handle None values from `info.get()` gracefully
- Handle yfinance edge cases:
```python
# Calendar can be dict or DataFrame
calendar = ticker.calendar
if isinstance(calendar, dict):
    for key, value in calendar.items():
        print(f"{key}: {value}")
elif hasattr(calendar, 'to_string'):
    print(calendar.to_string())

# News items may not be well-formed dicts
news = ticker.news
if news:
    for item in news[:5]:
        if isinstance(item, dict):
            title = item.get('title', 'N/A')
            pub_time = item.get('providerPublishTime', 0)
        else:
            title = str(item)

# Recommendations mean requires numeric columns only
if recommendations is not None:
    rec_numeric = recommendations.select_dtypes(include=[np.number])
    rec_summary = rec_numeric.mean()

# major_holders may have unexpected shape — use info as fallback
inst_pct = info.get('institutionsPercentHeld', 0.70)  # More reliable than major_holders
```

### Step 2: Technical Analysis

```python
# Moving Averages
df['MA5'] = df['Close'].rolling(5).mean()
df['MA20'] = df['Close'].rolling(20).mean()
df['MA60'] = df['Close'].rolling(60).mean()
df['MA250'] = df['Close'].rolling(250).mean()

# MACD
exp1 = df['Close'].ewm(span=12, adjust=False).mean()
exp2 = df['Close'].ewm(span=26, adjust=False).mean()
df['MACD'] = exp1 - exp2
df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
df['MACD_Hist'] = df['MACD'] - df['Signal']

# RSI
delta = df['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
rs = gain / loss
df['RSI'] = 100 - (100 / (1 + rs))

# Volume
df['Vol_MA20'] = df['Volume'].rolling(20).mean()
df['Vol_Ratio'] = df['Volume'] / df['Vol_MA20']

# Extract latest values (AFTER all calculations)
latest = df.iloc[-1]
current_price = float(latest['Close'])
ma5 = float(latest['MA5'])
ma20 = float(latest['MA20'])
ma60 = float(latest['MA60'])
ma250 = float(latest['MA250'])
macd = float(latest['MACD'])
signal = float(latest['Signal'])
rsi = float(latest['RSI'])
vol_ratio = float(latest['Vol_Ratio'])
recent_vol_avg = float(df['Vol_Ratio'].iloc[-10:].mean())

# Support/Resistance
support = float(df['Low'].iloc[-60:].min())
resistance = float(df['High'].iloc[-60:].max())
```

**Bullish Signals to Flag:**
- MA Stack: Price > MA5 > MA20 > MA60 > MA250 (perfect bullish order)
- MACD > Signal (golden cross) AND MACD rising
- RSI between 40-70 (healthy, room to run)
- Volume ratio >1.0 on up days (accumulation)
- Price within 5% of resistance (breakout setup)

### Step 3: Valuation Analysis

```python
pe = info.get('trailingPE')
forward_pe = info.get('forwardPE')
pb = info.get('priceToBook')
peg = info.get('pegRatio')
market_cap = info.get('marketCap')

# Growth metrics
rev_growth = None
try:
    revenue = financials.loc['Total Revenue']
    if len(revenue) >= 2:
        rev_growth = (revenue.iloc[0] - revenue.iloc[1]) / revenue.iloc[1] * 100
except:
    pass

# Fair value estimate
if pe and forward_pe:
    industry_avg_pe = 25  # Adjust by sector
    growth_premium = 1.5  # For market leaders
    fair_pe = industry_avg_pe * growth_premium
    eps_current = current_price / pe
    target_valuation = eps_current * fair_pe
```

**Bullish Signals to Flag:**
- Forward P/E < Trailing P/E (earnings acceleration expected)
- PEG < 1.0 (growth not fully priced in)
- P/E premium to sector justified by superior growth/margins
- Market cap room to grow vs TAM

### Step 4: Fundamental Strength

```python
roe = info.get('returnOnEquity')
roa = info.get('returnOnAssets')
profit_margin = info.get('profitMargins')
operating_margin = info.get('operatingMargins')

# Revenue/Income growth
ni_growth = None
try:
    net_income = financials.loc['Net Income']
    if len(net_income) >= 2:
        ni_growth = (net_income.iloc[0] - net_income.iloc[1]) / net_income.iloc[1] * 100
except:
    pass
```

**Bullish Signals to Flag:**
- ROE > 20% (excellent capital efficiency)
- ROE > 50% (best-in-class, like NVDA at 101%)
- Profit margin > 30% (pricing power, scale advantages)
- Operating margin expanding (operating leverage)
- Revenue growth > 30% YoY
- Net income growth tracking revenue growth (quality earnings)

### Step 5: Sentiment & Positioning

```python
# Options sentiment
pcr = None
try:
    options = ticker.options
    if len(options) > 0:
        nearest_expiry = options[0]
        opt_chain = ticker.option_chain(nearest_expiry)
        total_call_vol = opt_chain.calls['volume'].sum()
        total_put_vol = opt_chain.puts['volume'].sum()
        pcr = total_put_vol / total_call_vol if total_call_vol > 0 else 0
except:
    pass

# Short interest
short_pct = info.get('shortPercentOfFloat')
shares_short = info.get('sharesShort')
```

**Bullish Signals to Flag:**
- Put/Call Ratio < 0.7 (call dominance, bullish positioning)
- Short interest < 3% (limited bearish positioning)
- Institutional ownership stable/increasing
- Analyst upgrades > downgrades

### Step 6: Analyst Targets & Recommendations

```python
target_high = info.get('targetHighPrice')
target_low = info.get('targetLowPrice')
target_mean = info.get('targetMeanPrice')
upside = (target_mean / current_price - 1) * 100 if target_mean else None

# Recommendations
if recommendations is not None and len(recommendations) > 0:
    latest_rec = recommendations.iloc[-1]
    strong_buy = latest_rec.get('Strong Buy', 0)
    buy = latest_rec.get('Buy', 0)
    hold = latest_rec.get('Hold', 0)
    sell = latest_rec.get('Sell', 0)
    strong_sell = latest_rec.get('Strong Sell', 0)
    
    bull_score = (strong_buy + buy) / (strong_buy + buy + hold + sell + strong_sell)
```

**Bullish Signals to Flag:**
- Analyst mean target implies >20% upside
- Strong Buy + Buy > 70% of recommendations
- Recent target price increases

### Step 7: Catalyst Calendar

```python
earnings_date = info.get('earningsDate')

# Typical catalysts to research:
# - Earnings dates
# - Product launches
# - Industry conferences
# - Regulatory decisions
# - Partnership announcements
```

### Step 8: Synthesis & Scoring

```python
# Technical Score (0-10)
tech_score = 0
if current_price > ma5 > ma20 > ma60 > ma250:
    tech_score += 3  # Perfect MA stack
if macd > signal:
    tech_score += 2  # MACD bullish
if macd > df.iloc[-2]['MACD']:
    tech_score += 1  # MACD rising
if 40 < rsi < 70:
    tech_score += 2  # Healthy RSI
if recent_vol_avg > 1.0:
    tech_score += 2  # Volume confirming

# Fundamental Score (0-10)
fund_score = 0
if pe and pe < 40:
    fund_score += 2
elif pe and pe < 60:
    fund_score += 1
if forward_pe and forward_pe < 30:
    fund_score += 2
if roe and roe > 0.3:
    fund_score += 3
elif roe and roe > 0.15:
    fund_score += 2
if profit_margin and profit_margin > 0.3:
    fund_score += 2
```

## Output Format

```markdown
# [STOCK] BULL-SIDE RESEARCH REPORT

## Top Bull Points
| # | Bull Point | Confidence |
|---|------------|------------|
| 1 | ... | HIGH/MEDIUM/LOW |

## Technical Analysis
[MA stack, MACD, RSI, Volume, Key levels]

## Fundamental Strength
[Valuation, Growth, Profitability, ROE/ROIC]

## Sentiment & Positioning
[PCR, Short interest, Institutional flows, Analyst targets]

## Catalyst Calendar
[Near-term events that could drive price]

## Bull Target Prices
| Methodology | Target | Upside | Assumptions |
|-------------|--------|--------|-------------|
| Analyst Consensus | $X | +Y% | Street estimates |
| Technical Breakout | $X | +Y% | Breakout above resistance |
| Valuation Re-rating | $X | +Y% | P/E expansion to Zx |

## Key Risks to Bull Case
[List top 3-5 risks that could invalidate thesis]

## Investment Recommendation
[OVERWEIGHT/BUY/HOLD with entry strategy, stop loss, position sizing]
```

## Common Pitfalls

1. **yfinance MultiIndex**: Always check `isinstance(df.columns, pd.MultiIndex)` and drop level before accessing columns
2. **Calculation Order**: Calculate ALL technical indicators BEFORE extracting values from `latest` row
3. **None Handling**: Use `info.get()` with conditional checks; don't assume metrics exist
4. **Sector Context**: P/E of 40x may be cheap for 60% growth stock, expensive for 10% growth
5. **Volume Interpretation**: High volume on down days = distribution; high volume on up days = accumulation
6. **RSI Extremes**: RSI >70 can persist in strong trends; don't automatically sell overbought
7. **Forward P/E Trap**: Low forward P/E may imply unrealistic growth expectations
8. **Catalyst Timing**: Verify earnings dates via web search; yfinance `earningsDate` often None
9. **Calendar Dict vs DataFrame**: `ticker.calendar` may return a dict OR DataFrame — check `isinstance(calendar, dict)` before calling `.to_string()`
10. **News Format Variations**: `ticker.news` items may be dicts with missing keys or non-dict objects — check `isinstance(item, dict)` before accessing `.get()`
11. **Recommendations Mean Calculation**: `recommendations.tail(4).mean()` fails on string columns — use `select_dtypes(include=[np.number])` first
12. **major_holders Shape**: `major_holders.iloc[0, 1]` may fail if DataFrame has only 1 column — use `info.get('institutionsPercentHeld')` as fallback
13. **Earnings History Index**: `earnings_history` uses quarter dates as index — access via `.loc[]` or iterate carefully

## Dependencies

```bash
pip install yfinance pandas numpy
```

## Example Usage

```python
# See nvda_bull_analysis.py for full implementation
# Run: python3 bull_research.py TICKER
```

## Related Skills

- `bear-side-research`: Complementary downside analysis framework
- `technical-basic`: Technical indicator calculations
- `fundamental-filter`: Fundamental screening logic
- `yfinance`: Data fetching patterns and quirks
- `sentiment-analysis`: Deeper sentiment/positioning analysis

## Quick Reference: Bullish Signal Thresholds

| Metric | Bullish Threshold | Interpretation |
|--------|-------------------|----------------|
| MA Stack | Price > MA5 > MA20 > MA60 > MA250 | Strong uptrend |
| MACD | MACD > Signal AND rising | Momentum building |
| RSI | 40-70 | Healthy, room to run |
| Volume Ratio | >1.0 on up days | Accumulation |
| Forward P/E | < PEG of 1.0 | Growth discount |
| ROE | >20% | Capital efficiency |
| Profit Margin | >30% | Pricing power |
| Revenue Growth | >30% YoY | Strong demand |
| Put/Call Ratio | <0.7 | Bullish options flow |
| Short Interest | <3% | Limited bearish positioning |
| Analyst Upside | >20% to mean target | Street sees value |
