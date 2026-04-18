---
title: Earnings Event Options Analysis
name: earnings-options-analysis
version: 1.0
description: |
  Comprehensive framework for analyzing options positioning, implied vs realized volatility,
  and developing event-driven trade setups around earnings announcements.
  Covers implied move extraction, historical realized move comparison, options flow analysis,
  and specific trade structure recommendations with risk management.
triggers:
  - "earnings options analysis"
  - "implied move vs realized"
  - "options positioning around earnings"
  - "event trade setups"
  - "earnings straddle"
  - "pre-earnings options"
  - "IV crush trade"
  - "earnings volatility"
requires:
  - web_search
  - web_extract
  - options_pricing
---

# Earnings Event Options Analysis

## Purpose

Analyze options market positioning around earnings events to identify:
- Whether options are overpriced or underpriced relative to historical realized moves
- Current options flow and sentiment (put/call ratios, skew, open interest)
- Optimal trade structures for the specific implied/realized dynamic
- Risk parameters and position sizing for event-driven trades

## Workflow

### Step 1: Gather Core Data

**A. Earnings Date & Timing**
- Search for next earnings date and time (BMO/AMC)
- Confirm days to earnings
- Note any recent earnings surprises or guidance changes

**B. Current Stock Price & Implied Move**
- Get current stock price
- Find implied move from options market (typically via straddle price)
- Sources: Optionslam, MarketChameleon, Barchart, TipRanks

**C. Historical Realized Moves**
- Extract last 8 quarters of 1-day post-earnings moves
- Calculate average, median, and range
- Note directional bias (up vs down frequency)

### Step 2: Implied vs Realized Analysis

**Calculate the Differential:**
```
Implied Move = Market-priced expected move (from ATM straddle)
Realized Avg = Historical average 1-day move
Differential % = (Implied - Realized) / Realized × 100
```

**Interpretation:**
| Differential | Signal | Preferred Strategy |
|--------------|--------|-------------------|
| Implied > Realized +20% | Options overpriced | Sell premium (Iron Condor, Straddle Sale) |
| Implied ≈ Realized ±10% | Fairly priced | Directional spreads or skip |
| Implied < Realized -20% | Options underpriced | Buy premium (Long Straddle) |

### Step 3: Options Flow & Positioning

**A. Put/Call Ratio**
- Volume P/C ratio: <0.7 bullish, >1.0 bearish
- OI P/C ratio: Indicates positioning vs trading flow

**B. Open Interest Analysis**
- Call OI concentration: Resistance/target levels
- Put OI concentration: Support levels
- Unusual OI changes: Institutional positioning

**C. Skew Analysis**
- Put skew steepness: Fear of downside
- Call skew flatness: Bullish complacency or hedging

### Step 4: Trade Structure Recommendations

**When Implied > Realized (Overpriced):**

1. **Iron Condor (Defined Risk)**
   - Sell put spread below expected range
   - Sell call spread above expected range
   - Profit if stock stays within implied move range
   - Max loss = spread width - net credit

2. **Straddle/Strangle Sale (Undefined Risk)**
   - Sell ATM straddle or slightly OTM strangle
   - High risk if gap exceeds breakeven
   - Requires strict position sizing

**When Implied < Realized (Underpriced):**

1. **Long Straddle**
   - Buy ATM call + ATM put
   - Profit if move exceeds implied move + premium paid
   - Benefits from volatility expansion

2. **Long Strangle**
   - Lower cost alternative to straddle
   - Wider breakeven, lower probability

**Post-Earnings PEAD Setup:**
- Enter after earnings if reaction seems overdone
- Look for positive surprise with muted reaction (bullish PEAD)
- Look for negative surprise with overreaction (potential reversal)

### Step 5: Risk Management

**Position Sizing:**
- Max 2-3% of portfolio for earnings events
- Rationale: Gap risk beyond stop-losses

**Time Decay Considerations:**
- Theta accelerates into expiry
- 18-21 DTE optimal for earnings plays
- Exit day after earnings to capture IV crush

**Key Risks:**
| Risk | Mitigation |
|------|------------|
| Gap risk | Use spreads (iron condor) not naked shorts |
| IV crush | Exit day after earnings, don't hold to expiry |
| Directional | Neutral structures when uncertain |
| Liquidity | Stick to liquid strikes (ATM, ±10%) |

## Black-Scholes Reference

Use `options_pricing` tool for theoretical valuations:
```python
# ATM Straddle Price = Call Price + Put Price
# Implied Move % = (Straddle Price / Spot) × 100
```

## Data Sources

| Data Type | Sources |
|-----------|---------|
| Earnings Dates | Optionslam, Wall Street Horizon, Yahoo Finance |
| Implied Moves | MarketChameleon, Options AI, Barchart |
| Historical Moves | Optionslam, Options AI (earnings history) |
| Options Flow | Barchart P/C ratios, Unusual Whales, Fintel |
| Pricing | Black-Scholes calculator |

## Common Pitfalls

1. **Recency Bias:** Don't overweight the most recent earnings move
2. **Sample Size:** Need minimum 6-8 quarters for reliable historical average
3. **IV Timing:** Implied moves change daily as earnings approaches
4. **Guidance vs EPS:** Stock reacts to guidance, not just EPS beat/miss
5. **Sector Rotation:** Macro themes can override earnings results

## Output Template

Structure your analysis as:
1. Executive Summary (price, date, implied move)
2. Implied vs Realized Comparison (with verdict)
3. Options Flow & Positioning (P/C ratio, skew, OI)
4. Event Trade Setups (specific structures with strikes)
5. Risk Parameters (position sizing, max loss, exit plan)