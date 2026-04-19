---
name: semiconductor-analysis
description: Semiconductor and memory stock analysis framework — DRAM/NAND price cycles, HBM/AI demand drivers, foundry dynamics, and sector-specific valuation metrics for companies like NVDA, MU, TSM, AMD, INTC.
category: research
tags: [semiconductor, memory, hardware, ai, valuation, industry-analysis]
---

# Semiconductor Stock Analysis Framework

## Purpose

Comprehensive analysis methodology for semiconductor and memory companies. Covers industry-specific drivers (price cycles, capacity, technology nodes), company-specific factors (product mix, customer concentration), and sector-appropriate valuation metrics.

## When to Use

- Analyzing semiconductor stocks (design, foundry, memory, equipment)
- Building investment thesis for chip companies
- Understanding AI/HBM demand impact on valuations
- Cyclical timing for memory stocks (MU, Samsung, SK H力士)

---

## Semiconductor Subsector Classification

| Subsector | Companies | Key Drivers | Cycle Sensitivity |
|-----------|-----------|-------------|-------------------|
| **Memory** | MU, Samsung, SK H力士 | DRAM/NAND prices, inventory levels | 🔴 Very High |
| **GPU/AI** | NVDA, AMD | AI capex, datacenter demand, software ecosystem | 🟠 High |
| **Foundry** | TSM, UMC, SMIC | Utilization rates, node migration, geopolitics | 🟠 High |
| **Design (Fabless)** | QCOM, AVGO, TXN | End-market demand (mobile, auto, IoT) | 🟡 Moderate |
| **Equipment** | AMAT, LRCX, KLAC | Industry capex, technology transitions | 🟠 High |
| **Analog/Power** | TXN, ADI, ON | Industrial/auto demand, pricing power | 🟢 Lower |

---

## Memory-Specific Analysis (MU, Samsung, SK H力士)

### 1. DRAM/NAND Price Cycle

**Key Metrics to Track:**
```
• DRAM Contract Price (PC/Server/Mobile) — quarterly changes
• NAND Flash Price (Enterprise/Client/Mobile) — quarterly changes
• Inventory Days (DOI — Days of Inventory) — target: 60-90 days
• Bit Growth vs Demand Growth — supply/demand balance
```

**Cycle Phases:**
| Phase | Price Trend | Margin | Stock Performance |
|-------|-------------|--------|-------------------|
| Trough | Bottoming | Negative/LOW | Early accumulation |
| Recovery | +10-20% QoQ | Improving | Strong rally |
| Peak | Plateau | Peak margins | Distribution |
| Downturn | -10-30% QoQ | Compressing | Sharp decline |

**Data Sources:**
- TrendForce DRAMeXchange (industry standard)
- Company earnings calls (guidance on pricing)
- Yole Développement (market research)

### 2. AI/HBM Demand Analysis

**HBM (High Bandwidth Memory) Opportunity:**
```
• HBM3/HBM3E pricing: 5-10x standard DRAM
• AI server memory content: 3-5x traditional servers
• Capacity allocation: % of total DRAM bit production
• Technology leadership: 1βnm, 1αnm node status
```

**Key Questions:**
1. What % of revenue from HBM? (Target: >20% for MU by 2025)
2. HBM capacity constrained through when?
3. Customer concentration (NVIDIA, AMD, hyperscalers)?

### 3. Competitive Dynamics

**DRAM Market Structure (Oligopoly):**
```
Samsung:    ~50% market share
SK H力士:    ~30% market share
Micron:     ~20% market share
```

**Analysis Points:**
- CapEx discipline (all three restraining supply?)
- Technology parity (node leadership?)
- Customer diversification (PC/server/mobile/auto mix)

---

## GPU/AI Analysis (NVDA, AMD)

### 1. Demand Drivers

```
• Hyperscaler capex guidance (MSFT, GOOGL, META, AMZN)
• AI model training vs inference mix
• Sovereign AI initiatives (country-level purchases)
• Enterprise AI adoption rate
```

### 2. Supply Constraints

```
• TSMC CoWoS packaging capacity (bottleneck for H100/H200)
• HBM supply (SK H力士, Samsung, MU capacity)
• Lead times (normal: 8-12 weeks, constrained: 20-50 weeks)
```

### 3. Competitive Moat

```
• CUDA ecosystem lock-in (switching costs)
• Software stack (TensorRT, Triton, etc.)
• Customer relationships (design wins)
• Technology lead (next-gen architecture timing)
```

---

## Foundry Analysis (TSM, UMC, SMIC)

### 1. Capacity & Utilization

```
• Fab utilization rate (target: >85% for profitability)
• Capacity expansion plans (new fabs, capex)
• Technology node mix (7nm, 5nm, 3nm revenue %)
```

### 2. Customer Concentration

```
• Top 5 customer revenue % (TSM: ~60% from top 5)
• Apple dependence (TSM: ~25% of revenue)
• Geographic exposure (US, China, Taiwan %)
```

### 3. Geopolitical Risk

```
• Export controls (advanced nodes to China)
• CHIPS Act subsidies (US fab incentives)
• Taiwan risk (geopolitical scenarios)
```

---

## Sector-Specific Valuation Metrics

| Metric | Memory | GPU/AI | Foundry | Design |
|--------|--------|--------|---------|--------|
| **P/E** | Cyclical (ignore at trough) | 25-40x growth | 15-25x | 20-30x |
| **P/B** | 1-2x (trough), 3-5x (peak) | 10-20x | 5-10x | 5-10x |
| **EV/Sales** | 2-4x (trough), 6-10x (peak) | 15-25x | 5-10x | 8-15x |
| **P/FCF** | Not useful (negative at trough) | 30-50x | 15-25x | 20-30x |
| **Key Focus** | Book value, replacement cost | Growth, TAM expansion | Utilization, node mix | Margins, R&D efficiency |

### Memory-Specific Valuation

```python
# Memory stocks trade on P/B through the cycle
# Buy when P/B < 1.5x (trough valuation)
# Sell when P/B > 4x (peak valuation)

# Alternative: Sum-of-parts on asset value
# • DRAM bit capacity × replacement cost per bit
# • NAND bit capacity × replacement cost per bit
# • Cash - Debt
```

---

## Macro Factor Correlations (Empirical)

Based on 2-year analysis of MU (2024-2026):

| Factor | Correlation | Interpretation |
|--------|-------------|----------------|
| SOX (Semiconductor Index) | **0.78+** | Primary β driver |
| SMH (Semiconductor ETF) | **0.78+** | Sector exposure |
| XLK (Tech ETF) | **0.70** | Tech β |
| NASDAQ | **0.65** | Growth stock β |
| VIX | **-0.48** | Risk-off negative |
| Copper (HG=F) | **0.25** | Industrial demand proxy |
| 10Y Yield (TNX) | **0.12** | Low rate sensitivity |
| TLT (Bonds) | **-0.02** | Minimal bond sensitivity |

**Trading Implications:**
- Semiconductor stocks are **high β to sector indices** (SOX/SMH)
- **VIX hedging** is valuable (negative correlation -0.48)
- **Rate sensitivity varies** by subsector (memory lower, growth higher)

---

## Key Data Points to Monitor

### Weekly/Monthly
- [ ] SOX/SMH technical levels
- [ ] VIX levels (risk sentiment)
- [ ] Taiwan/NKX futures (TSM sentiment)

### Quarterly
- [ ] DRAM/NAND contract prices (TrendForce)
- [ ] Company earnings (guidance on pricing, capex)
- [ ] Inventory days (DOI) trends
- [ ] Hyperscaler capex guidance

### Annual
- [ ] Industry capex plans
- [ ] Technology node roadmaps
- [ ] Market share changes

---

## Red Flags

| Flag | Interpretation |
|------|----------------|
| Inventory days > 120 | Demand collapse or overproduction |
| Gross margin compression > 10pp QoQ | Pricing pressure |
| CapEx increase during downturn | Market share grab (risky) |
| Customer concentration > 50% | Single-customer risk |
| Technology node lag > 2 years | Competitive disadvantage |
| HBM not in product roadmap | Missing AI opportunity |

---

## Python Analysis Template

```python
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def analyze_semiconductor_stock(ticker_symbol, subsector='memory'):
    """Comprehensive semiconductor stock analysis."""
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    
    # Fetch sector ETFs for β analysis
    sector_etfs = {'SOX': '^SOX', 'SMH': 'SMH', 'XLK': 'XLK'}
    
    # Calculate correlations (see macro-factor-correlation skill)
    # ...
    
    # Subsector-specific metrics
    if subsector == 'memory':
        # P/B focus for cyclical valuation
        pb = info.get('priceToBook', 0)
        print(f"P/B: {pb:.2f}x")
        print(f"Valuation vs cycle: {'Attractive' if pb < 2 else 'Expensive' if pb > 4 else 'Neutral'}")
    
    elif subsector == 'gpu_ai':
        # PEG and growth focus
        pe = info.get('forwardPE', 0)
        growth = info.get('earningsGrowth', 0)
        peg = pe / (growth * 100) if growth else 0
        print(f"PEG: {peg:.2f}")
    
    # Return analysis
    return {
        'ticker': ticker_symbol,
        'subsector': subsector,
        'pb': info.get('priceToBook'),
        'pe': info.get('forwardPE'),
        'margin': info.get('profitMargins'),
        'roe': info.get('returnOnEquity'),
    }

# Usage
# mu_analysis = analyze_semiconductor_stock('MU', subsector='memory')
# nvda_analysis = analyze_semiconductor_stock('NVDA', subsector='gpu_ai')
```

---

## Common Pitfalls

1. **Valuing memory stocks on P/E at cycle trough** — Earnings are depressed/negative; use P/B instead
2. **Ignoring HBM mix shift** — AI memory has 5-10x ASP; traditional metrics miss this
3. **Overlooking capex cycles** — Semiconductor is capex-intensive; FCF volatile
4. **Assuming all chips are cyclical** — Analog/auto chips have lower cyclicality
5. **Missing geopolitical risk** — China exposure, export controls, Taiwan risk
6. **Using generic tech valuations** — Semiconductor requires subsector-specific metrics

---

## Related Skills

- `macro-factor-correlation` — Compute stock vs macro factor correlations
- `bull-side-research` — Comprehensive bull-case analysis framework
- `yfinance` — Data fetching patterns and quirks
- `valuation-model` — DCF and comparable company analysis

---

## Quick Reference: Semiconductor Subsectors

```
MEMORY (MU, Samsung, SK H力士)
├─ Drivers: DRAM/NAND prices, inventory, AI/HBM demand
├─ Valuation: P/B (1-2x trough, 3-5x peak)
└─ Cycle: 3-4 year memory supercycle

GPU/AI (NVDA, AMD)
├─ Drivers: AI capex, datacenter demand, software moat
├─ Valuation: PEG, EV/Sales (growth-focused)
└─ Cycle: Secular growth + cyclical capex

FOUNDRY (TSM, UMC)
├─ Drivers: Utilization, node migration, geopolitics
├─ Valuation: P/E 15-25x, P/B 5-10x
└─ Cycle: Capex-driven, 2-3 year cycles

DESIGN (QCOM, AVGO, TXN)
├─ Drivers: End-market (mobile, auto, IoT), pricing power
├─ Valuation: P/E 20-30x, FCF yield
└─ Cycle: Lower β, more stable

EQUIPMENT (AMAT, LRCX, KLAC)
├─ Drivers: Industry capex, technology transitions
├─ Valuation: P/E 15-25x (cyclical)
└─ Cycle: Leading indicator of fab capex
```
