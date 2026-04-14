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
    """Analyze historical drawdowns - depth, duration, recovery."""
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    
    dd_events = []
    in_drawdown = False
    start_idx = None
    
    for idx, dd in drawdown.items():
        if dd < -0.05 and not in_drawdown:
            in_drawdown = True
            start_idx = idx
        elif in_drawdown and dd >= -0.01:
            in_drawdown = False
            trough_idx = drawdown.loc[start_idx:idx].idxmin()
            recovery_mask = equity.loc[trough_idx:] >= equity.loc[start_idx]
            recovery_idx = recovery_mask[recovery_mask].index[0] if recovery_mask.any() else None
            
            dd_events.append({
                'start': str(start_idx),
                'trough': str(trough_idx),
                'end': str(idx),
                'recovery': str(recovery_idx) if recovery_idx else None,
                'depth': float(drawdown.loc[trough_idx]),
                'duration_days': (idx - start_idx).days,
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
        'top_drawdowns': dd_events,
        'avg_drawdown': float(drawdown[drawdown < -0.05].mean()) if (drawdown < -0.05).any() else 0,
        'time_in_drawdown': float((drawdown < -0.05).sum() / len(drawdown))
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
    """Check IS vs OOS performance and trade-level metrics."""
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
    
    if len(trades) > 0 and 'pnl' in trades.columns and 'cost' in trades.columns:
        trade_returns = trades['pnl'] / trades['cost']
        trade_win_rate = (trade_returns > 0).mean()
        profit_factor = trade_returns[trade_returns > 0].sum() / abs(trade_returns[trade_returns < 0].sum()) if trade_returns[trade_returns < 0].sum() != 0 else 0
    else:
        trade_win_rate = 0
        profit_factor = 0
    
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
        'is_return': float(is_return),
        'oos_return': float(oos_return),
        'return_degradation': float(oos_return - is_return),
        'is_sharpe': float(is_sharpe),
        'oos_sharpe': float(oos_sharpe),
        'sharpe_degradation': float(oos_sharpe - is_sharpe),
        'monthly_win_rate': float(monthly_win_rate),
        'trade_win_rate': float(trade_win_rate),
        'trade_profit_factor': float(profit_factor),
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


def main(run_dir):
    """Run complete risk audit and save results."""
    run_dir = Path(run_dir)
    
    print("=" * 80)
    print("RISK AUDIT REPORT")
    print("=" * 80)
    
    equity, trades = load_data(run_dir)
    print(f"\nData loaded: {len(equity)} days, {len(trades)} trades")
    
    dd_analysis = drawdown_analysis(equity)
    vol_analysis = volatility_assessment(equity)
    tail_analysis = tail_risk_analysis(equity)
    overfit_analysis = overfitting_checks(equity, trades)
    recommendations = risk_recommendations(dd_analysis, vol_analysis, tail_analysis)
    
    results = {
        'drawdown_analysis': dd_analysis,
        'volatility_assessment': vol_analysis,
        'tail_risk': tail_analysis,
        'overfitting_checks': overfit_analysis,
        'recommendations': recommendations
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
