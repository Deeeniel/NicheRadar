import os
from pathlib import Path

MAPPINGS = {
    "bot.backtest_dataset": "bot.backtest.dataset",
    "bot.backtest_engine": "bot.backtest.engine",
    "bot.backtest_metrics": "bot.backtest.metrics",
    "bot.backtest_reporting": "bot.backtest.reporting",
    "bot.calibration": "bot.backtest.calibration",
    "bot.settlement_validation": "bot.backtest.validation",
    "bot.shadow_replay": "bot.backtest.replay",
    "bot.portfolio_risk": "bot.risk_manager",
    "bot.risk_engine": "bot.risk_manager",
    "bot.execution_engine": "bot.execution",
    "bot.shadow": "bot.execution"
}

def refactor(directory):
    for root, dirs, files in os.walk(directory):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            path = Path(root) / filename
            content = path.read_text(encoding="utf-8")
            original = content
            for old, new in MAPPINGS.items():
                content = content.replace("from " + old, "from " + new)
                content = content.replace("import " + old, "import " + new)
            if content != original:
                path.write_text(content, encoding="utf-8")
                print(f"Updated {path}")

refactor("bot")
refactor("tests")
