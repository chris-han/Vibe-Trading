#!/usr/bin/env python3
"""
Momentum Stock Screening Template
Reusable template for screening equity universes for momentum candidates.
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================

UNIVERSE = {
    # Define your universe here
    # Example: CSI 300 proxies
    'BABA': 'Alibaba Group',
    'JD': 'JD.com',
    '0700.HK': 'Tencent Holdings',
    # Add more symbols...
}

SCREENING_PARAMS = {
    'min_volume_percentile': 0.5,  # 50% of median volume
    'max_decline_6m': -0.60,       # Exclude >60% decline
    'top_n': 20,                   # Final candidate count
}

# ============================================================================
# DATA FETCHING
# ============================================================================

def fetch_price_data(ticker, period='2y'):
    """Fetch price data with multi-index handling"""
    try:
        df = yf.download(ticker, period=period, progress=False)
        if df is None or df.empty:
            return None
        
        # Handle multi-index columns (critical for HK stocks, futures)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in df.columns]
            df = df.rename(columns={
                f"Close_{ticker}": "Close",
                f"Volume_{ticker}": "Volume"
            })
        
        if 'Close' not in df.columns:
            close_cols = [c for c in df.columns if 'Close' in str(c)]
            if close_cols:
                df = df.rename(columns={close_cols[0]: 'Close'})
        
        return df
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

def fetch_fundamentals(ticker):
    """Fetch fundamental metrics"""
    try:
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
    except:
        return {'pe_ratio': None, 'pb_ratio': None, 'roe': None,
                'market_cap': None, 'dividend_yield': None, 'beta': None}

# ============================================================================
# MOMENTUM CALCULATION
# ============================================================================

def calculate_momentum_factors(df):
    """Calculate momentum factors"""
    if df is None or len(df) < 60:
        return None
    
    close = df['Close'].dropna()
    if len(close) < 60:
        return None
    
    # 12-month momentum excluding recent 1 month
    mom_12m_excl_1m = (close.iloc[-21] / close.iloc[-252]) - 1 if len(close) >= 252 else np.nan
    
    # 6-month momentum
    mom_6m = (close.iloc[-1] / close.iloc[-126]) - 1 if len(close) >= 126 else np.nan
    
    # 3-month momentum
    mom_3m = (close.iloc[-1] / close.iloc[-63]) - 1 if len(close) >= 63 else np.nan
    
    # Volatility
    volatility = close.pct_change().std() * np.sqrt(252)
    
    return {
        'mom_12m_excl_1m': mom_12m_excl_1m,
        'mom_6m': mom_6m,
        'mom_3m': mom_3m,
        'volatility': volatility,
        'avg_volume': df['Volume'].mean() if 'Volume' in df.columns else np.nan,
        'current_price': close.iloc[-1],
    }

# ============================================================================
# SCREENING
# ============================================================================

def run_screen(universe, params):
    """Run momentum screen"""
    print(f"Screen Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Universe Size: {len(universe)} symbols\n")
    
    results = []
    for ticker, name in universe.items():
        df = fetch_price_data(ticker, period='2y')
        if df is not None:
            metrics = calculate_momentum_factors(df)
            if metrics:
                fundamentals = fetch_fundamentals(ticker)
                results.append({
                    'code': ticker, 'name': name, **metrics, **fundamentals
                })
    
    df_results = pd.DataFrame(results)
    
    # Liquidity filter
    volume_threshold = df_results['avg_volume'].median() * params['min_volume_percentile']
    df_results = df_results[df_results['avg_volume'] >= volume_threshold]
    
    # Momentum filter
    df_results = df_results[df_results['mom_6m'] > params['max_decline_6m']]
    
    # Composite score with NaN handling
    df_results['momentum_score'] = df_results.apply(
        lambda row: (0.5 * row['mom_12m_excl_1m'] + 0.3 * row['mom_6m'] + 0.2 * row['mom_3m']
                     if pd.notna(row['mom_12m_excl_1m'])
                     else 0.6 * row['mom_6m'] + 0.4 * row['mom_3m']),
        axis=1
    )
    
    df_results = df_results.sort_values('momentum_score', ascending=False)
    return df_results.head(params['top_n'])

if __name__ == '__main__':
    candidates = run_screen(UNIVERSE, SCREENING_PARAMS)
    print(candidates[['code', 'name', 'current_price', 'momentum_score', 'pe_ratio', 'roe']].to_string())
