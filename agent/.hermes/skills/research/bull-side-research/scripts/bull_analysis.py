#!/usr/bin/env python3
"""
Bull-Side Stock Research Analysis Script
Usage: python bull_analysis.py TICKER

Generates comprehensive bull-side research report including:
- Technical analysis (MA stack, MACD, RSI, volume)
- Fundamental analysis (valuation, growth, profitability)
- Sentiment & positioning (options PCR, short interest)
- Catalyst calendar
- Price targets and investment recommendation
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import sys

def fetch_data(ticker_symbol, days=730):
    """Fetch historical data and company info."""
    ticker = yf.Ticker(ticker_symbol)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    df = yf.download(ticker_symbol, start=start_date.strftime("%Y-%m-%d"), 
                     end=end_date.strftime("%Y-%m-%d"), progress=False)
    
    # CRITICAL: Handle MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    
    info = ticker.info
    return ticker, df, info

def calculate_technicals(df):
    """Calculate all technical indicators."""
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
    
    return df

def extract_latest(df):
    """Extract latest values after all calculations."""
    latest = df.iloc[-1]
    return {
        'price': float(latest['Close']),
        'ma5': float(latest['MA5']),
        'ma20': float(latest['MA20']),
        'ma60': float(latest['MA60']),
        'ma250': float(latest['MA250']),
        'macd': float(latest['MACD']),
        'signal': float(latest['Signal']),
        'macd_hist': float(latest['MACD_Hist']),
        'macd_prev': float(df.iloc[-2]['MACD']),
        'rsi': float(latest['RSI']),
        'vol_ratio': float(latest['Vol_Ratio']),
        'vol_avg_10d': float(df['Vol_Ratio'].iloc[-10:].mean()),
        'support': float(df['Low'].iloc[-60:].min()),
        'resistance': float(df['High'].iloc[-60:].max())
    }

def get_sentiment(ticker):
    """Fetch options and short interest data."""
    pcr = None
    try:
        options = ticker.options
        if len(options) > 0:
            opt_chain = ticker.option_chain(options[0])
            call_vol = opt_chain.calls['volume'].sum()
            put_vol = opt_chain.puts['volume'].sum()
            pcr = put_vol / call_vol if call_vol > 0 else 0
    except:
        pass
    
    info = ticker.info
    return {
        'pcr': pcr,
        'short_pct': info.get('shortPercentOfFloat'),
        'shares_short': info.get('sharesShort')
    }

def calculate_scores(t, info, sentiment):
    """Calculate technical and fundamental scores."""
    # Technical Score
    tech_score = 0
    if t['price'] > t['ma5'] > t['ma20'] > t['ma60'] > t['ma250']:
        tech_score += 3
    if t['macd'] > t['signal']:
        tech_score += 2
    if t['macd'] > t['macd_prev']:
        tech_score += 1
    if 40 < t['rsi'] < 70:
        tech_score += 2
    if t['vol_avg_10d'] > 1.0:
        tech_score += 2
    
    # Fundamental Score
    pe = info.get('trailingPE')
    forward_pe = info.get('forwardPE')
    roe = info.get('returnOnEquity')
    profit_margin = info.get('profitMargins')
    
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
    
    return tech_score, fund_score

def generate_report(symbol, ticker, df, info, t, sentiment, tech_score, fund_score):
    """Generate the bull-side research report."""
    pe = info.get('trailingPE')
    forward_pe = info.get('forwardPE')
    pb = info.get('priceToBook')
    roe = info.get('returnOnEquity')
    profit_margin = info.get('profitMargins')
    market_cap = info.get('marketCap')
    
    # Growth
    rev_growth = None
    ni_growth = None
    try:
        revenue = ticker.financials.loc['Total Revenue']
        if len(revenue) >= 2:
            rev_growth = (revenue.iloc[0] - revenue.iloc[1]) / revenue.iloc[1] * 100
    except:
        pass
    try:
        net_income = ticker.financials.loc['Net Income']
        if len(net_income) >= 2:
            ni_growth = (net_income.iloc[0] - net_income.iloc[1]) / net_income.iloc[1] * 100
    except:
        pass
    
    # Analyst targets
    target_mean = info.get('targetMeanPrice')
    target_high = info.get('targetHighPrice')
    target_low = info.get('targetLowPrice')
    upside = (target_mean / t['price'] - 1) * 100 if target_mean else None
    
    # Valuation target
    target_valuation = None
    if pe:
        fair_pe = 25 * 1.5
        eps = t['price'] / pe
        target_valuation = eps * fair_pe
    
    # Technical target
    technical_target = t['resistance'] * 1.15 if t['resistance'] else None
    
    print("=" * 60)
    print(f"{symbol} BULL-SIDE RESEARCH REPORT")
    print("=" * 60)
    
    print(f"\nCurrent Price: ${t['price']:.2f}")
    print(f"Market Cap: ${market_cap/1e9:.1f}B" if market_cap else "")
    
    print("\n" + "=" * 60)
    print("TECHNICAL ANALYSIS")
    print("=" * 60)
    print(f"\nMA Stack:")
    print(f"  MA5:   ${t['ma5']:.2f}  ({((t['price']/t['ma5'])-1)*100:+.1f}%)")
    print(f"  MA20:  ${t['ma20']:.2f} ({((t['price']/t['ma20'])-1)*100:+.1f}%)")
    print(f"  MA60:  ${t['ma60']:.2f} ({((t['price']/t['ma60'])-1)*100:+.1f}%)")
    print(f"  MA250: ${t['ma250']:.2f} ({((t['price']/t['ma250'])-1)*100:+.1f}%)")
    print(f"\nMACD: {t['macd']:.2f} vs Signal {t['signal']:.2f} | Golden Cross: {t['macd'] > t['signal']}")
    print(f"RSI: {t['rsi']:.1f} | {'Overbought' if t['rsi'] > 70 else 'Healthy' if t['rsi'] > 30 else 'Oversold'}")
    print(f"Volume: {t['vol_ratio']:.2f}x current, {t['vol_avg_10d']:.2f}x 10D avg")
    print(f"Key Levels: Support ${t['support']:.2f}, Resistance ${t['resistance']:.2f}")
    print(f"\nTechnical Score: {tech_score}/10")
    
    print("\n" + "=" * 60)
    print("FUNDAMENTAL ANALYSIS")
    print("=" * 60)
    print(f"\nValuation:")
    print(f"  P/E (TTM): {pe:.1f}" if pe else "  P/E (TTM): N/A")
    print(f"  Forward P/E: {forward_pe:.1f}" if forward_pe else "  Forward P/E: N/A")
    print(f"  P/B: {pb:.2f}" if pb else "  P/B: N/A")
    print(f"\nProfitability:")
    print(f"  ROE: {roe*100:.1f}%" if roe else "  ROE: N/A")
    print(f"  Profit Margin: {profit_margin*100:.1f}%" if profit_margin else "  Profit Margin: N/A")
    print(f"\nGrowth:")
    print(f"  Revenue Growth (YoY): {rev_growth:.1f}%" if rev_growth else "  Revenue Growth: N/A")
    print(f"  Net Income Growth (YoY): {ni_growth:.1f}%" if ni_growth else "  Net Income Growth: N/A")
    print(f"\nFundamental Score: {fund_score}/10")
    
    print("\n" + "=" * 60)
    print("SENTIMENT & POSITIONING")
    print("=" * 60)
    print(f"\nPut/Call Ratio: {sentiment['pcr']:.2f}" if sentiment['pcr'] else "\nPut/Call Ratio: N/A")
    if sentiment['pcr']:
        print(f"  Interpretation: {'Bullish (<0.7)' if sentiment['pcr'] < 0.7 else 'Neutral' if sentiment['pcr'] < 1.2 else 'Bearish'}")
    print(f"Short Interest: {sentiment['short_pct']*100:.2f}%" if sentiment['short_pct'] else "Short Interest: N/A")
    
    print("\n" + "=" * 60)
    print("ANALYST TARGETS")
    print("=" * 60)
    print(f"\nMean Target: ${target_mean:.2f}" if target_mean else "\nMean Target: N/A")
    print(f"High Target: ${target_high:.2f}" if target_high else "High Target: N/A")
    print(f"Low Target: ${target_low:.2f}" if target_low else "Low Target: N/A")
    print(f"Upside to Mean: {upside:.1f}%" if upside else "")
    
    print("\n" + "=" * 60)
    print("PRICE TARGETS")
    print("=" * 60)
    print(f"\nValuation-Based: ${target_valuation:.2f}" if target_valuation else "")
    print(f"Analyst Consensus: ${target_mean:.2f} ({upside:.1f}% upside)" if target_mean else "")
    print(f"Technical Breakout: ${technical_target:.2f}" if technical_target else "")
    
    print("\n" + "=" * 60)
    print("KEY RISKS TO BULL CASE")
    print("=" * 60)
    print("\n1. Valuation Compression")
    print("2. Competition")
    print("3. Execution Risk")
    print("4. Macro/Cyclical Downturn")
    print("5. Regulatory/Geopolitical")
    
    print("\n" + "=" * 60)
    print("RECOMMENDATION")
    print("=" * 60)
    if tech_score >= 7 and fund_score >= 7:
        rec = "STRONG BUY"
    elif tech_score >= 5 and fund_score >= 5:
        rec = "BUY"
    elif tech_score >= 3 or fund_score >= 3:
        rec = "HOLD"
    else:
        rec = "AVOID"
    print(f"\nRating: {rec}")
    print(f"Entry: ${t['price']:.2f} or pullback to ${t['ma20']:.2f} (MA20)")
    print(f"Stop Loss: ${t['support']:.2f} ({((t['support']/t['price'])-1)*100:.1f}%)")
    print(f"Target: ${target_mean:.2f} ({upside:.1f}% upside)" if target_mean else "")
    
    # Save metrics
    output = {
        'symbol': symbol,
        'price': t['price'],
        'technical': {'score': tech_score, **t},
        'fundamental': {
            'score': fund_score,
            'pe': pe, 'forward_pe': forward_pe, 'pb': pb,
            'roe': roe, 'profit_margin': profit_margin,
            'rev_growth': rev_growth, 'ni_growth': ni_growth
        },
        'sentiment': sentiment,
        'targets': {
            'analyst_mean': target_mean,
            'valuation': target_valuation,
            'technical': technical_target
        }
    }
    
    with open(f"{symbol.lower()}_bull_metrics.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\nMetrics saved to {symbol.lower()}_bull_metrics.json")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bull_analysis.py TICKER")
        sys.exit(1)
    
    symbol = sys.argv[1].upper()
    print(f"Analyzing {symbol}...")
    
    ticker, df, info = fetch_data(symbol)
    df = calculate_technicals(df)
    t = extract_latest(df)
    sentiment = get_sentiment(ticker)
    tech_score, fund_score = calculate_scores(t, info, sentiment)
    generate_report(symbol, ticker, df, info, t, sentiment, tech_score, fund_score)
