from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from bot.app import run_cli


class AppTests(unittest.TestCase):
    def test_run_cli_returns_immediately_when_report_command_handles_request(self) -> None:
        args = _args(dashboard_report=True)
        parser = argparse.ArgumentParser()

        with (
            patch("bot.app.handle_report_command", return_value=True) as handle_report,
            patch("bot.app.run_watchlist_loop") as run_watchlist_loop,
        ):
            run_cli(args, parser)

        handle_report.assert_called_once()
        run_watchlist_loop.assert_not_called()

    def test_run_cli_uses_watchlist_specific_max_days_override(self) -> None:
        args = _args(watchlist="watchlist.json", watchlist_max_days=45.0)
        parser = argparse.ArgumentParser()

        with (
            patch("bot.app.handle_report_command", return_value=False),
            patch("bot.app.build_evidence_collector", return_value=object()),
            patch("bot.app.load_watchlist", return_value=["item"]),
            patch("bot.app.load_settlements", return_value=[]),
            patch("bot.app.run_watchlist_loop") as run_watchlist_loop,
        ):
            run_cli(args, parser)

        config = run_watchlist_loop.call_args.args[1]
        self.assertEqual(config.max_days_to_expiry, 45.0)

    def test_run_cli_scan_mode_prints_no_trade_ideas_when_market_list_is_empty(self) -> None:
        args = _args(sample_data="markets.json")
        parser = argparse.ArgumentParser()
        output = StringIO()

        with (
            patch("bot.app.handle_report_command", return_value=False),
            patch("bot.app.build_evidence_collector", return_value=object()),
            patch("bot.app.load_watchlist", return_value=[]),
            patch("bot.app.load_settlements", return_value=[]),
            patch("bot.app.load_sample_markets", return_value=[]),
            redirect_stdout(output),
        ):
            run_cli(args, parser)

        text = output.getvalue()
        self.assertIn("loaded_markets=0", text)
        self.assertIn("no_trade_ideas", text)


def _args(**overrides):
    values = {
        "sample_data": None,
        "live": False,
        "limit": 20,
        "watchlist": None,
        "poll_seconds": 0,
        "iterations": 1,
        "log_file": "logs/watchlist_snapshots.jsonl",
        "alert_file": "logs/watchlist_alerts.jsonl",
        "shadow_file": "logs/shadow_fills.jsonl",
        "db_file": "logs/watchlist.sqlite",
        "shadow_replay": False,
        "settlement_file": None,
        "validate_settlements": False,
        "settlement_validation_json": None,
        "replay_json": None,
        "dashboard_report": False,
        "report_file": None,
        "report_json": None,
        "report_html": None,
        "report_limit": 10,
        "calibration_report": False,
        "calibration_file": None,
        "calibration_json": None,
        "calibration_min_samples": 5,
        "backtest": False,
        "backtest_report": None,
        "backtest_json": None,
        "backtest_min_samples": 20,
        "backtest_target_source": None,
        "backtest_profile": None,
        "backtest_event_type": None,
        "backtest_from": None,
        "backtest_to": None,
        "backtest_min_net_edge": 0.0,
        "backtest_max_spread": None,
        "shadow_bankroll": 1000.0,
        "shadow_position_risk_pct": 0.02,
        "max_total_risk_pct": 0.2,
        "max_market_risk_pct": 0.02,
        "max_event_type_risk_pct": 0.08,
        "circuit_breaker_loss_pct": 0.05,
        "max_open_shadow_positions": 10,
        "cache_file": "logs/http_cache.sqlite",
        "gamma_cache_seconds": 30.0,
        "book_cache_seconds": 10.0,
        "rss_cache_seconds": 900.0,
        "api_rate_limit_seconds": 0.1,
        "rss_rate_limit_seconds": 0.25,
        "watchlist_max_days": 120.0,
        "alert_evidence_jump": 0.15,
        "evidence_sources": "data/evidence_sources.json",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


if __name__ == "__main__":
    unittest.main()
