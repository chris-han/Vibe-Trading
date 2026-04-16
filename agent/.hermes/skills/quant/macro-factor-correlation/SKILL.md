---
name: macro-factor-correlation
description: Macro factor correlation analysis for individual stocks — fetch macroeconomic data via yfinance, compute return correlations, and generate comprehensive visualizations (heatmap, bar chart, scatter plots).
---

# Macro Factor Correlation Analysis

## Overview

This skill provides a complete workflow for analyzing how macroeconomic factors affect an individual stock. It covers data fetching via yfinance, correlation computation, and multi-panel visualization generation.

**Use cases**:
- Understand which macro factors drive a stock's returns
- Identify key risk exposures (market β, rate sensitivity, commodity exposure)
- Generate correlation reports for investment committees
- Screen for stocks with specific macro sensitivities

---

## Standard Macro Factor Universe

| Category | Factor | Ticker | Interpretation |
|----------|--------|--------|----------------|
| **Market** | S&P 500 | `^GSPC` | Broad equity market exposure |
| **Market** | NASDAQ | `^IXIC` | Tech-heavy index exposure |
| **Volatility** | VIX | `^VIX` | Market fear/volatility (usually negative correlation) |
| **Rates** | 10Y Treasury Yield | `^TNX` | Interest rate sensitivity |
| **Rates** | 20Y+ Treasury ETF | `TLT` | Bond market / rate expectations |
| **Currency** | US Dollar Index | `DX-Y.NYB` | USD strength exposure |
| **Commodities** | Crude Oil | `CL=F` | Energy cost / inflation exposure |
| **Commodities** | Gold | `GC=F` | Inflation hedge / safe haven |
| **Commodities** | Copper | `HG=F` | Industrial demand / growth proxy |
| **Sector** | Technology ETF | `XLK` | Tech sector exposure |
| **Sector** | Industrials ETF | `XLI` | Industrial sector exposure |

---

## Data Fetching Pattern

### Handle yfinance MultiIndex Columns

yfinance returns different column formats depending on version. Use this robust pattern:

```python
import yfinance as yf
import pandas as pd

def fetch_macro_data(tickers: dict, start: str, end: str) -> dict:
    """Fetch macro factor data with robust column handling.
    
    Args:
        tickers: Dict of {name: ticker_symbol}
        start, end: Date strings in YYYY-MM-DD format
    
    Returns:
        Dict of {name: pd.Series} with closing prices
    """
    price_data = {}
    
    for name, ticker in tickers.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False)
            if df is None or len(df) == 0:
                continue
            
            # Handle MultiIndex columns (yfinance >= 1.0)
            if isinstance(df.columns, pd.MultiIndex):
                # Try to find Close column
                close_cols = [c for c in df.columns if c[0] == 'Close']
                if close_cols:
                    price_data[name] = df[close_cols[0]]
                else:
                    continue
            # Handle single-level columns (yfinance < 1.0)
            elif 'Close' in df.columns:
                price_data[name] = df['Close']
            else:
                continue
                
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            continue
    
    return price_data
```

### Merge and Align Time Series

```python
def merge_and_compute_returns(price_data: dict) -> pd.DataFrame:
    """Merge price series and compute daily returns.
    
    Args:
        price_data: Dict of {name: pd.Series}
    
    Returns:
        DataFrame of daily returns, aligned by date
    """
    # Concatenate with keys, inner join for date alignment
    price_df = pd.DataFrame(price_data)
    price_df = price_df.dropna()  # Remove dates with missing data
    
    # Compute daily returns
    returns_df = price_df.pct_change().dropna()
    
    return returns_df
```

---

## Correlation Computation

```python
def compute_correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    """Compute Pearson correlation matrix.
    
    Args:
        returns_df: DataFrame of daily returns
    
    Returns:
        Correlation matrix as DataFrame
    """
    return returns_df.corr(method='pearson')

def extract_target_correlations(corr_matrix: pd.DataFrame, target: str) -> pd.Series:
    """Extract correlations with a target asset, sorted by magnitude.
    
    Args:
        corr_matrix: Full correlation matrix
        target: Target asset name (e.g., 'CLS')
    
    Returns:
        Sorted Series of correlations
    """
    return corr_matrix[target].sort_values(ascending=False)
```

### Correlation Interpretation Guide

| |corr| | Strength | Typical Action |
|---|---|---|---|
| > 0.7 | Very strong | Primary driver, high β exposure |
| 0.5 - 0.7 | Strong | Significant factor exposure |
| 0.3 - 0.5 | Moderate | Secondary factor, worth monitoring |
| 0.1 - 0.3 | Weak | Minor influence |
| < 0.1 | Negligible | Essentially independent |

**Note**: VIX typically shows **negative** correlation with equities (range: -0.3 to -0.7).

---

## Visualization Template

### 4-Panel Correlation Dashboard

```python
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

def plot_correlation_dashboard(
    corr_matrix: pd.DataFrame,
    target: str,
    returns_df: pd.DataFrame,
    output_path: str = 'macro_correlation.png',
    figsize: tuple = (16, 14),
) -> None:
    """Generate a 4-panel correlation analysis dashboard.
    
    Panels:
    1. Full correlation heatmap
    2. Bar chart of target vs all factors
    3. Scatter plot: target vs strongest positive correlation
    4. Scatter plot: target vs strongest negative correlation
    """
    fig, axes = plt.subplots(2, 2, figsize=figsize)
    fig.suptitle(f'Macro Factor Correlation Analysis: {target}', 
                 fontsize=16, fontweight='bold')
    
    # Panel 1: Heatmap
    ax1 = axes[0, 0]
    sns.heatmap(corr_matrix, annot=True, fmt='.3f', cmap='RdBu_r',
                center=0, square=True, linewidths=0.5, ax=ax1,
                cbar_kws={'shrink': 0.8})
    ax1.set_title('Correlation Heatmap')
    plt.setp(ax1.get_xticklabels(), rotation=45, ha='right')
    
    # Panel 2: Bar chart
    ax2 = axes[0, 1]
    target_corr = corr_matrix[target].drop(target)
    colors = ['darkred' if x < 0 else 'darkgreen' for x in target_corr.values]
    ax2.barh(range(len(target_corr)), target_corr.values, color=colors, alpha=0.7)
    ax2.set_yticks(range(len(target_corr)))
    ax2.set_yticklabels(target_corr.index)
    ax2.set_xlabel('Correlation Coefficient')
    ax2.set_title(f'{target} vs Macro Factors')
    ax2.axvline(x=0, color='black', linestyle='-', linewidth=0.8)
    ax2.grid(axis='x', alpha=0.3, linestyle='--')
    
    # Panel 3: Scatter - strongest positive
    ax3 = axes[1, 0]
    positive = target_corr[target_corr > 0]
    if len(positive) > 0:
        top_pos = positive.idxmax()
        ax3.scatter(returns_df[top_pos], returns_df[target], alpha=0.5, s=20)
        ax3.set_xlabel(f'{top_pos} Returns')
        ax3.set_ylabel(f'{target} Returns')
        ax3.set_title(f'{target} vs {top_pos} (r={positive.max():.3f})')
        ax3.grid(True, alpha=0.3)
        
        # Add trend line
        z = np.polyfit(returns_df[top_pos], returns_df[target], 1)
        ax3.plot(returns_df[top_pos].sort_values(),
                 np.poly1d(z)(returns_df[top_pos].sort_values()),
                 'r--', alpha=0.8)
    
    # Panel 4: Scatter - strongest negative
    ax4 = axes[1, 1]
    negative = target_corr[target_corr < 0]
    if len(negative) > 0:
        top_neg = negative.idxmin()
        ax4.scatter(returns_df[top_neg], returns_df[target], alpha=0.5, s=20)
        ax4.set_xlabel(f'{top_neg} Returns')
        ax4.set_ylabel(f'{target} Returns')
        ax4.set_title(f'{target} vs {top_neg} (r={negative.min():.3f})')
        ax4.grid(True, alpha=0.3)
        
        # Add trend line
        z = np.polyfit(returns_df[top_neg], returns_df[target], 1)
        ax4.plot(returns_df[top_neg].sort_values(),
                 np.poly1d(z)(returns_df[top_neg].sort_values()),
                 'r--', alpha=0.8)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Chart saved to: {output_path}")
```

---

## Complete Workflow Example

```python
from datetime import datetime, timedelta

def run_macro_correlation_analysis(
    target_stock: str,
    lookback_years: int = 2,
    output_dir: str = 'artifacts',
) -> dict:
    """Run complete macro correlation analysis.
    
    Args:
        target_stock: Stock ticker (e.g., 'CLS', 'AAPL')
        lookback_years: Years of historical data
        output_dir: Directory for output files
    
    Returns:
        Dict containing correlation matrix, statistics, and file paths
    """
    # Define macro factors
    macro_tickers = {
        target_stock: target_stock,
        'SP500': '^GSPC',
        'NASDAQ': '^IXIC',
        'VIX': '^VIX',
        'TNX': '^TNX',
        'DXY': 'DX-Y.NYB',
        'OIL': 'CL=F',
        'GOLD': 'GC=F',
        'COPPER': 'HG=F',
        'TLT': 'TLT',
        'XLK': 'XLK',
        'XLI': 'XLI',
    }
    
    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * lookback_years)
    
    # Fetch data
    print(f"Fetching data from {start_date.date()} to {end_date.date()}...")
    price_data = fetch_macro_data(macro_tickers, start_date, end_date)
    
    if target_stock not in price_data:
        raise ValueError(f"Could not fetch data for {target_stock}")
    
    # Compute returns
    returns_df = merge_and_compute_returns(price_data)
    
    # Compute correlations
    corr_matrix = compute_correlation_matrix(returns_df)
    
    # Generate visualization
    output_path = f'{output_dir}/macro_correlation_{target_stock}.png'
    plot_correlation_dashboard(corr_matrix, target_stock, returns_df, output_path)
    
    # Save correlation matrix to CSV
    csv_path = f'{output_dir}/correlation_matrix_{target_stock}.csv'
    corr_matrix.to_csv(csv_path)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"Correlation Summary for {target_stock}")
    print(f"{'='*60}")
    
    target_corr = corr_matrix[target_stock].drop(target_stock).sort_values(ascending=False)
    for factor, corr in target_corr.items():
        strength = "Strong" if abs(corr) > 0.5 else "Moderate" if abs(corr) > 0.3 else "Weak"
        direction = "Positive" if corr > 0 else "Negative"
        print(f"{factor:10s}: {corr:7.4f} ({direction}, {strength})")
    
    return {
        'correlation_matrix': corr_matrix,
        'returns_df': returns_df,
        'chart_path': output_path,
        'csv_path': csv_path,
        'n_observations': len(returns_df),
    }

# Usage
# results = run_macro_correlation_analysis('CLS')
```

---

## Interpretation Guidelines

### Typical Stock Profiles

| Stock Type | Expected High Correlations | Expected Low/Negative Correlations |
|------------|---------------------------|-----------------------------------|
| **Tech Growth** | NASDAQ, XLK, VIX (neg) | TLT, GOLD, DXY |
| **Financial** | SP500, TNX, XLK | GOLD, VIX (neg) |
| **Industrial** | XLI, SP500, COPPER | TLT, GOLD |
| **Energy** | OIL, SP500 | TLT, GOLD |
| **Consumer Staples** | SP500 (lower β) | VIX (neg, weaker) |
| **Utilities** | TLT, TNX (neg) | SP500 (lower) |

### Red Flags

- **Correlation > 0.9 with index**: Stock may be a proxy for beta, limited alpha potential
- **VIX correlation > 0**: Unusual for equities; may indicate hedging characteristics
- **No significant correlations**: Stock may be idiosyncratic or data quality issue
- **Correlations changing sign**: Regime-dependent behavior, requires deeper analysis

---

## Dependencies

```bash
pip install yfinance pandas numpy matplotlib seaborn scipy
```

---

## Notes

1. **yfinance version differences**: Newer versions (>=1.0) return MultiIndex columns. Always handle both formats.

2. **Date alignment**: Use inner join when merging. Do not forward-fill across non-trading days.

3. **Returns vs prices**: Always compute correlations on **returns**, not prices. Price correlations are spurious.

4. **Sample size**: Minimum 100 observations recommended. 250+ (1 year) preferred for stable estimates.

5. **Chinese fonts**: If using Chinese labels, install CJK fonts or expect warnings (charts still render).

6. **Lookback sensitivity**: Test multiple lookback periods (1Y, 2Y, 5Y) to check correlation stability.

7. **Sector ETFs**: Often more informative than broad indices for industry-specific stocks.
