"""
Risk Audit Script for Strategy Backtest
Computes: Drawdown analysis, Volatility assessment, Tail risk (VaR/CVaR), 
          Overfitting checks, Risk recommendations
"""

import pandas as pd
import numpy as np
from scipy import stats
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')


def load_data(run_dir):
    """Load equity curve and trades from backtest artifacts."""
    equity_df = pd.read_csv(Path(run_dir) / "artifacts/equity.csv", index_col=0, parse_dates=True)
    equity = equity_df['equity']
    trades = pd.read_csv(Path(run_dir) / "artifacts/trades.csv", index_col=0, parse_dates=True)
    return equity, trades


def drawdown_analysis(equity):
    """Analyze historical drawdowns - depth, duration, recovery.
    
    FIX: Properly tracks trough within each drawdown event and calculates recovery_days.
    """
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    
    dd_events = []
    in_drawdown = False
    start_idx = None
    current_trough = None
    current_trough_val = 0
    
    # Track trough during drawdown, not after exit
    for idx in drawdown.index:
        dd = drawdown.loc[idx]
        if dd < -0.05 and not in_drawdown:
            in_drawdown = True
            start_idx = idx
            current_trough = idx
            current_trough_val = dd
        elif in_drawdown:
            if dd < current_trough_val:
                current_trough = idx
                current_trough_val = dd
            if dd >= -0.01:
                in_drawdown = False
                # Calculate recovery from trough to original peak
                peak_val = equity.loc[start_idx]
                recovery_mask = equity.loc[current_trough:] >= peak_val
                recovery_idx = recovery_mask[recovery_mask].index[0] if recovery_mask.any() else None
                
                dd_events.append({
                    'start': str(start_idx),
                    'trough': str(current_trough),
                    'end': str(idx),
                    'recovery': str(recovery_idx) if recovery_idx else None,
                    'depth': float(current_trough_val),
                    'duration_days': (idx - start_idx).days,
                    'recovery_days': (recovery_idx - current_trough).days if recovery_idx else None
                })
    
    dd_events = sorted(dd_events, key=lambda x: x['depth'])[:5]
    
    max_dd_idx = drawdown.idxmin()
    max_dd = drawdown.min()
    peak_idx = equity[:max_dd_idx].idxmax()
    
    peak_val = equity.loc[peak_idx]
    recovery_mask = equity.loc[max_dd_idx:] >= peak_val
    recovery_idx = recovery_mask[recovery_mask].index[0] if recovery_mask.any() else None
    
    dd_duration = (max_dd_idx - peak_idx).days
    
    return {
        'max_drawdown': float(max_dd),
        'max_dd_peak': peak_idx.strftime('%Y-%m-%d') if hasattr(peak_idx, 'strftime') else str(peak_idx),
        'max_dd_trough': max_dd_idx.strftime('%Y-%m-%d') if hasattr(max_dd_idx, 'strftime') else str(max_dd_idx),
        'max_dd_recovery': recovery_idx.strftime('%Y-%m-%d') if recovery_idx and hasattr(recovery_idx, 'strftime') else 'Not recovered',
        'max_dd_duration_days': dd_duration,
        'max_dd_recovery_days': (recovery_idx - max_dd_idx).days if recovery_idx else None,
        'top_drawdowns': dd_events,
        'avg_drawdown_depth': float(drawdown[drawdown < -0.05].mean()) if (drawdown < -0.05).any() else 0,
        'time_in_drawdown_pct': float((drawdown < -0.05).sum() / len(drawdown) * 100)
    }


def volatility_assessment(equity):
    """Calculate vol metrics and clustering."""
    returns = equity.pct_change().dropna()
    
    ann_vol = returns.std() * np.sqrt(252)
    vol_20d = returns.rolling(20).std() * np.sqrt(252)
    vol_60d = returns.rolling(60).std() * np.sqrt(252)
    
    downside_returns = returns[returns < 0]
    downside_vol = downside_returns.std() * np.sqrt(252)
    
    squared_returns = returns ** 2
    vol_clustering = squared_returns.autocorr(lag=1)
    
    vol_regimes = pd.cut(vol_60d, bins=[0, 0.15, 0.25, 1.0], labels=['Low', 'Medium', 'High'])
    high_vol_pct = (vol_regimes == 'High').mean()
    
    return {
        'annual_volatility': float(ann_vol),
        'downside_volatility': float(downside_vol),
        'vol_clustering_ac1': float(vol_clustering),
        'vol_clustering_significant': bool(vol_clustering > 0.1),
        'avg_20d_vol': float(vol_20d.mean()),
        'max_20d_vol': float(vol_20d.max()),
        'high_vol_regime_pct': float(high_vol_pct),
        'volatility_skew': float(returns.skew()),
        'volatility_kurtosis': float(returns.kurtosis())
    }


def tail_risk_analysis(equity):
    """Calculate VaR, CVaR, and tail metrics."""
    returns = equity.pct_change().dropna()
    
    def hist_var(returns, confidence):
        return -np.percentile(returns, (1 - confidence) * 100)
    
    def hist_cvar(returns, confidence):
        var = hist_var(returns, confidence)
        tail = returns[returns <= -var]
        return -tail.mean() if len(tail) > 0 else var
    
    var_95 = hist_var(returns, 0.95)
    var_99 = hist_var(returns, 0.99)
    cvar_95 = hist_cvar(returns, 0.95)
    cvar_99 = hist_cvar(returns, 0.99)
    
    mu, sigma = returns.mean(), returns.std()
    param_var_95 = -(mu + stats.norm.ppf(0.05) * sigma)
    
    cvar_var_ratio = cvar_95 / var_95 if var_95 > 0 else 1
    skew = returns.skew()
    kurt = returns.kurtosis()
    tail_ratio = abs(returns.quantile(0.05)) / returns.quantile(0.95)
    
    worst_days = returns.nsmallest(10)
    best_days = returns.nlargest(10)
    
    return {
        'var_95_daily': float(var_95),
        'var_99_daily': float(var_99),
        'cvar_95_daily': float(cvar_95),
        'cvar_99_daily': float(cvar_99),
        'param_var_95': float(param_var_95),
        'cvar_var_ratio': float(cvar_var_ratio),
        'skewness': float(skew),
        'kurtosis': float(kurt),
        'tail_ratio': float(tail_ratio),
        'fat_tail_indicator': bool(kurt > 3 or abs(skew) > 0.5),
        'worst_day_return': float(worst_days.min()),
        'best_day_return': float(best_days.max()),
        'worst_10_avg': float(worst_days.mean()),
        'best_10_avg': float(best_days.mean())
    }


def overfitting_checks(equity, trades):
    """Check IS vs OOS performance and trade-level metrics.
    
    FIX: Filter to sell trades only for win rate calculation (buy trades have pnl=0).
    """
    returns = equity.pct_change().dropna()
    
    split_idx = len(returns) * 2 // 3
    is_returns = returns.iloc[:split_idx]
    oos_returns = returns.iloc[split_idx:]
    
    is_cum = (1 + is_returns).cumprod()
    oos_cum = (1 + oos_returns).cumprod()
    
    is_return = is_cum.iloc[-1] - 1
    oos_return = oos_cum.iloc[-1] - 1
    
    is_sharpe = is_returns.mean() / is_returns.std() * np.sqrt(252) if is_returns.std() > 0 else 0
    oos_sharpe = oos_returns.mean() / oos_returns.std() * np.sqrt(252) if oos_returns.std() > 0 else 0
    
    monthly_returns = returns.resample('ME').sum()
    monthly_win_rate = (monthly_returns > 0).mean()
    
    # FIX: Filter to sell trades only (buy trades have pnl=0, skewing win rate)
    trade_win_rate = 0
    profit_factor = 0
    total_trades = 0
    if len(trades) > 0 and 'pnl' in trades.columns:
        sell_trades = trades[trades['side'] == 'sell'] if 'side' in trades.columns else trades[trades['pnl'] != 0]
        total_trades = len(sell_trades)
        if total_trades > 0:
            winning_trades = sell_trades[sell_trades['pnl'] > 0]
            losing_trades = sell_trades[sell_trades['pnl'] < 0]
            trade_win_rate = len(winning_trades) / total_trades
            gross_profit = winning_trades['pnl'].sum()
            gross_loss = abs(losing_trades['pnl'].sum())
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    overfitting_flags = []
    if oos_return - is_return < -0.1:
        overfitting_flags.append("Significant OOS return degradation (>10%)")
    if oos_sharpe - is_sharpe < -0.5:
        overfitting_flags.append("Significant OOS Sharpe degradation (>0.5)")
    if monthly_win_rate < 0.4:
        overfitting_flags.append("Low monthly win rate (<40%)")
    if trade_win_rate < 0.35:
        overfitting_flags.append("Low trade win rate (<35%)")
    
    return {
        'is_period': f"{returns.index[0].strftime('%Y-%m-%d')} to {returns.index[split_idx-1].strftime('%Y-%m-%d')}",
        'oos_period': f"{returns.index[split_idx].strftime('%Y-%m-%d')} to {returns.index[-1].strftime('%Y-%m-%d')}",
        'is_return_pct': float(is_return * 100),
        'oos_return_pct': float(oos_return * 100),
        'return_degradation_pct': float((oos_return - is_return) * 100),
        'is_sharpe': float(is_sharpe),
        'oos_sharpe': float(oos_sharpe),
        'sharpe_degradation': float(oos_sharpe - is_sharpe),
        'monthly_win_rate_pct': float(monthly_win_rate * 100),
        'trade_win_rate_pct': float(trade_win_rate * 100),
        'trade_profit_factor': float(profit_factor),
        'total_trades': total_trades,
        'overfitting_flags': overfitting_flags,
        'overfitting_risk': 'HIGH' if len(overfitting_flags) >= 2 else 'MEDIUM' if len(overfitting_flags) == 1 else 'LOW'
    }


def risk_recommendations(dd_analysis, vol_analysis, tail_analysis):
    """Generate prioritized risk control recommendations."""
    recommendations = []
    
    target_vol = 0.15
    current_vol = vol_analysis['annual_volatility']
    vol_adjusted_position = target_vol / current_vol if current_vol > 0 else 1.0
    
    recommendations.append({
        'category': 'Position Sizing',
        'issue': f'Current annual vol {current_vol:.1%} vs target {target_vol:.1%}',
        'recommendation': f'Scale positions to {vol_adjusted_position:.2f}x for target vol',
        'priority': 'HIGH' if current_vol > 0.25 else 'MEDIUM'
    })
    
    if dd_analysis['max_drawdown'] < -0.20:
        recommendations.append({
            'category': 'Stop-Loss',
            'issue': f"Max drawdown {dd_analysis['max_drawdown']:.1%} exceeds 20% threshold",
            'recommendation': 'Implement -15% trailing stop-loss on individual positions',
            'priority': 'HIGH'
        })
    
    if tail_analysis['cvar_95_daily'] > 0.03:
        recommendations.append({
            'category': 'Tail Risk Hedge',
            'issue': f"95% CVaR {tail_analysis['cvar_95_daily']:.2%} indicates significant tail risk",
            'recommendation': 'Consider protective puts or reduce gross exposure during high vol regimes',
            'priority': 'MEDIUM'
        })
    
    if vol_analysis['high_vol_regime_pct'] > 0.3:
        recommendations.append({
            'category': 'Regime Filter',
            'issue': f"Strategy spent {vol_analysis['high_vol_regime_pct']:.1%} time in high vol regime",
            'recommendation': 'Reduce exposure by 50% when 60D vol > 25%',
            'priority': 'MEDIUM'
        })
    
    recommendations.append({
        'category': 'Risk Limit',
        'issue': f"Daily 95% VaR at {tail_analysis['var_95_daily']:.2%}",
        'recommendation': f"Set daily VaR limit at {tail_analysis['var_95_daily'] * 1.5:.2%} (1.5x current)",
        'priority': 'MEDIUM'
    })
    
    return recommendations


def generate_cro_decision(dd_analysis, vol_analysis, tail_analysis, overfit_analysis, recommendations):
    """Generate CRO-style decision framework with risk thresholds assessment."""
    
    high_priority_count = sum(1 for r in recommendations if r['priority'] == 'HIGH')
    
    if high_priority_count >= 3:
        decision = "REJECTED"
        status_color = "RED"
    elif high_priority_count >= 1:
        decision = "CONDITIONAL"
        status_color = "YELLOW"
    else:
        decision = "APPROVED"
        status_color = "GREEN"
    
    # Risk thresholds assessment
    thresholds = {
        'Max Drawdown': {'value': f"{dd_analysis['max_drawdown']:.1%}", 'status': 'RED' if dd_analysis['max_drawdown'] < -0.25 else 'YELLOW' if dd_analysis['max_drawdown'] < -0.15 else 'GREEN'},
        'Annual Volatility': {'value': f"{vol_analysis['annual_volatility']:.1%}", 'status': 'RED' if vol_analysis['annual_volatility'] > 0.25 else 'YELLOW' if vol_analysis['annual_volatility'] > 0.15 else 'GREEN'},
        'CVaR/VaR Ratio': {'value': f"{tail_analysis['cvar_var_ratio']:.2f}x", 'status': 'RED' if tail_analysis['cvar_var_ratio'] > 1.5 else 'YELLOW' if tail_analysis['cvar_var_ratio'] > 1.3 else 'GREEN'},
        'Kurtosis': {'value': f"{tail_analysis['kurtosis']:.1f}", 'status': 'RED' if tail_analysis['kurtosis'] > 10 else 'YELLOW' if tail_analysis['kurtosis'] > 5 else 'GREEN'},
        'OOS Sharpe Degradation': {'value': f"{overfit_analysis['sharpe_degradation']:.2f}", 'status': 'RED' if overfit_analysis['sharpe_degradation'] < -0.5 else 'YELLOW' if overfit_analysis['sharpe_degradation'] < -0.3 else 'GREEN'},
        'Trade Win Rate': {'value': f"{overfit_analysis['trade_win_rate_pct']:.1f}%", 'status': 'RED' if overfit_analysis['trade_win_rate_pct'] < 35 else 'YELLOW' if overfit_analysis['trade_win_rate_pct'] < 45 else 'GREEN'},
    }
    
    return {
        'decision': decision,
        'status_color': status_color,
        'high_priority_issues': high_priority_count,
        'risk_thresholds': thresholds,
        'deployment_prerequisites': [
            'Stop-loss logic implemented' if any(r['category'] == 'Stop-Loss' for r in recommendations) else 'N/A',
            'Position sizing adjusted for target vol' if any(r['category'] == 'Position Sizing' for r in recommendations) else 'N/A',
            'Overfitting concerns addressed' if overfit_analysis['overfitting_risk'] != 'LOW' else 'N/A',
            'Tail hedge mechanism evaluated' if any(r['category'] == 'Tail Risk Hedge' for r in recommendations) else 'Optional',
        ]
    }


def main(run_dir):
    """Run complete risk audit and save results with formatted console output."""
    run_dir = Path(run_dir)
    
    print("=" * 60)
    print("BACKTEST RISK AUDIT")
    print(f"Run: {run_dir.name}")
    print("=" * 60)
    
    # Load data
    print("\n[1/6] Loading data...")
    equity, trades = load_data(run_dir)
    print(f"  - Equity curve: {len(equity)} days ({equity.index[0].date()} to {equity.index[-1].date()})")
    print(f"  - Trades: {len(trades)} records")
    
    # Drawdown analysis
    print("\n[2/6] Analyzing drawdowns...")
    dd_analysis = drawdown_analysis(equity)
    print(f"  - Max drawdown: {dd_analysis['max_drawdown']:.1%}")
    print(f"  - Peak: {dd_analysis['max_dd_peak']} -> Trough: {dd_analysis['max_dd_trough']}")
    print(f"  - Recovery: {dd_analysis['max_dd_recovery']}")
    print(f"  - Time in drawdown (>5%): {dd_analysis['time_in_drawdown_pct']:.1f}%")
    
    # Volatility assessment
    print("\n[3/6] Assessing volatility...")
    vol_analysis = volatility_assessment(equity)
    print(f"  - Annual volatility: {vol_analysis['annual_volatility']:.1%}")
    print(f"  - Downside volatility: {vol_analysis['downside_volatility']:.1%}")
    print(f"  - Vol clustering (AC1): {vol_analysis['vol_clustering_ac1']:.3f} {'(SIGNIFICANT)' if vol_analysis['vol_clustering_significant'] else ''}")
    print(f"  - Kurtosis: {vol_analysis['volatility_kurtosis']:.1f}")
    
    # Tail risk analysis
    print("\n[4/6] Computing tail risk...")
    tail_analysis = tail_risk_analysis(equity)
    print(f"  - 95% VaR (daily): {tail_analysis['var_95_daily']:.2%}")
    print(f"  - 95% CVaR (daily): {tail_analysis['cvar_95_daily']:.2%}")
    print(f"  - CVaR/VaR ratio: {tail_analysis['cvar_var_ratio']:.2f}x")
    print(f"  - Worst day: {tail_analysis['worst_day_return']:.2%}")
    
    # Overfitting checks
    print("\n[5/6] Checking for overfitting...")
    overfit_analysis = overfitting_checks(equity, trades)
    print(f"  - IS return: {overfit_analysis['is_return_pct']:.1f}%, OOS return: {overfit_analysis['oos_return_pct']:.1f}%")
    print(f"  - IS Sharpe: {overfit_analysis['is_sharpe']:.2f}, OOS Sharpe: {overfit_analysis['oos_sharpe']:.2f}")
    print(f"  - Trade win rate: {overfit_analysis['trade_win_rate_pct']:.1f}%")
    print(f"  - Overfitting risk: {overfit_analysis['overfitting_risk']}")
    if overfit_analysis['overfitting_flags']:
        for flag in overfit_analysis['overfitting_flags']:
            print(f"    ⚠ {flag}")
    
    # Risk recommendations
    print("\n[6/6] Generating recommendations...")
    recommendations = risk_recommendations(dd_analysis, vol_analysis, tail_analysis)
    
    # Add overfitting recommendation if needed
    if overfit_analysis['overfitting_risk'] in ['HIGH', 'MEDIUM']:
        recommendations.append({
            'category': 'Overfitting Mitigation',
            'issue': f"Overfitting risk: {overfit_analysis['overfitting_risk']}",
            'recommendation': 'Simplify model, reduce parameters, or expand test period',
            'priority': 'HIGH' if overfit_analysis['overfitting_risk'] == 'HIGH' else 'MEDIUM'
        })
    
    # Add signal quality recommendation if win rate low
    if overfit_analysis['trade_win_rate_pct'] < 45:
        recommendations.append({
            'category': 'Signal Quality',
            'issue': f"Trade win rate {overfit_analysis['trade_win_rate_pct']:.1f}% below 45% threshold",
            'recommendation': 'Improve entry signals with additional filters',
            'priority': 'HIGH' if overfit_analysis['trade_win_rate_pct'] < 35 else 'MEDIUM'
        })
    
    # Sort by priority
    priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
    recommendations.sort(key=lambda x: priority_order.get(x['priority'], 3))
    
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. [{rec['priority']}] {rec['category']}: {rec['recommendation']}")
    
    # CRO decision
    cro_decision = generate_cro_decision(dd_analysis, vol_analysis, tail_analysis, overfit_analysis, recommendations)
    print("\n" + "=" * 60)
    print(f"FINAL CRO RECOMMENDATION: {cro_decision['decision']}")
    print("=" * 60)
    
    # Save results
    results = {
        'drawdown_analysis': dd_analysis,
        'volatility_assessment': vol_analysis,
        'tail_risk': tail_analysis,
        'overfitting_checks': overfit_analysis,
        'recommendations': recommendations,
        'cro_decision': cro_decision
    }
    
    output_path = run_dir / "artifacts" / "risk_audit.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {output_path}")
    
    return results


if __name__ == "__main__":
    import sys
    run_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    main(run_dir)
