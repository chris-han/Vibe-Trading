# Strategy Generate — Examples

## Example 1: A-share dual MA crossover (tushare)

User: "用000001.SZ做双均线金叉策略，短期5日长期20日，回测2024年"

Tool call sequence:
1. skill_view(name="strategy-generate") → 获得工作流指引
2. setup_backtest_run(config_json=..., signal_engine_py=...) → 一次性创建运行目录并写入配置与策略代码
   ```json
   {
     "config_json": {"source": "tushare", "codes": ["000001.SZ"], "start_date": "2024-01-01", "end_date": "2024-12-31", "initial_cash": 1000000, "commission": 0.001, "extra_fields": null},
     "signal_engine_py": "..."
   }
   ```
3. bash("./.venv/bin/python -m py_compile code/signal_engine.py && echo OK") → AST 语法检查
4. backtest(run_dir=...) → 执行回测（引擎内置）
5. read_file("artifacts/metrics.csv") → 查看结果，按评审标准判断
6. (如需修复) 优先使用新的 setup_backtest_run(...) 生成修正版运行目录；只有明确要更新当前运行时才 edit_file("code/signal_engine.py", ...) → backtest → read_file

## Example 2: US stock RSI strategy (yfinance)

User: "Build RSI strategy on AAPL, buy when RSI<30 sell when RSI>70, backtest 2024"

Tool call sequence:
1. skill_view(name="strategy-generate") → 获得工作流指引
2. setup_backtest_run(config_json=..., signal_engine_py=...) → 创建运行目录与代码
   ```json
   {
     "config_json": {"source": "yfinance", "codes": ["AAPL.US"], "start_date": "2024-01-01", "end_date": "2024-12-31", "initial_cash": 1000000, "commission": 0.001, "extra_fields": null},
     "signal_engine_py": "..."
   }
   ```
3. bash("./.venv/bin/python -m py_compile code/signal_engine.py && echo OK") → AST 检查
4. backtest(run_dir=...) → 执行回测（引擎内置）
5. read_file("artifacts/metrics.csv") → 查看结果
6. (如需修复) 优先重新 setup_backtest_run(...)，必要时再 edit_file → backtest → read_file

## Example 3: Crypto trend strategy (okx)

User: "BTC-USDT趋势跟踪策略，回测2024年"

Tool call sequence:
1. skill_view(name="strategy-generate") → 获得工作流指引
2. setup_backtest_run(config_json=..., signal_engine_py=...) → 创建运行目录与代码
   ```json
   {
     "config_json": {"source": "okx", "codes": ["BTC-USDT"], "start_date": "2024-01-01", "end_date": "2024-12-31", "initial_cash": 1000000, "commission": 0.001, "extra_fields": null},
     "signal_engine_py": "..."
   }
   ```
3. bash("./.venv/bin/python -m py_compile code/signal_engine.py && echo OK") → AST 检查
4. backtest(run_dir=...) → 执行回测（引擎内置）
5. read_file("artifacts/metrics.csv") → 查看结果
6. (如需修复) 优先重新 setup_backtest_run(...)，必要时再 edit_file → backtest → read_file
