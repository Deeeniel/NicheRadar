from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bot.config import BotConfig
from bot.models import Evidence, Market
from bot.positions import load_positions
from bot.reporting import build_dashboard_report
from bot.report_commands import handle_report_command
from bot.risk_manager import load_portfolio_risk_state
from bot.storage import WatchlistStore
from bot.watchlist import WatchlistItem
from bot.watchlist_runner import run_watchlist_loop
from bot.backtest.dataset import load_backtest_samples
from bot.backtest.replay import replay_shadow_pnl


class CommandIntegrationTests(unittest.TestCase):
    def test_handle_report_command_runs_dashboard_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "watchlist.sqlite")
            WatchlistStore(db_path)
            args = argparse.Namespace(
                validate_settlements=False,
                shadow_replay=False,
                calibration_report=False,
                backtest=False,
                dashboard_report=True,
                settlement_file=None,
                db_file=db_path,
                report_limit=5,
                report_file=None,
                report_json=None,
                report_html=None,
            )
            output = StringIO()
            with redirect_stdout(output):
                handled = handle_report_command(args, BotConfig())

        self.assertTrue(handled)
        self.assertIn("dashboard_report", output.getvalue())

    def test_handle_report_command_runs_dashboard_path_on_fresh_db(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "fresh.sqlite")
            args = argparse.Namespace(
                validate_settlements=False,
                shadow_replay=False,
                calibration_report=False,
                backtest=False,
                dashboard_report=True,
                settlement_file=None,
                db_file=db_path,
                report_limit=5,
                report_file=None,
                report_json=None,
                report_html=None,
            )
            output = StringIO()
            with redirect_stdout(output):
                handled = handle_report_command(args, BotConfig())

        self.assertTrue(handled)
        self.assertIn("dashboard_report", output.getvalue())
        self.assertIn("snapshots=0", output.getvalue())

    def test_handle_report_command_runs_shadow_replay_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            db_path = str(base / "watchlist.sqlite")
            settlement_path = str(base / "settlements.json")
            store = WatchlistStore(db_path)
            store.insert_snapshots([_snapshot()])
            store.insert_shadow_fills([_fill()])
            Path(settlement_path).write_text(
                json.dumps(
                    [
                        {
                            "slug": "market",
                            "winning_side": "BUY_NO",
                            "status": "settled",
                            "timestamp_utc": "2026-06-30T00:00:00+00:00",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                validate_settlements=False,
                shadow_replay=True,
                calibration_report=False,
                backtest=False,
                dashboard_report=False,
                settlement_file=settlement_path,
                db_file=db_path,
                replay_json=None,
            )
            output = StringIO()
            with redirect_stdout(output):
                handled = handle_report_command(args, BotConfig())

        self.assertTrue(handled)
        self.assertIn("shadow_replay", output.getvalue())
        self.assertIn("status=settled", output.getvalue())

    def test_handle_report_command_runs_shadow_replay_path_on_fresh_db(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "fresh.sqlite")
            args = argparse.Namespace(
                validate_settlements=False,
                shadow_replay=True,
                calibration_report=False,
                backtest=False,
                dashboard_report=False,
                settlement_file=None,
                db_file=db_path,
                replay_json=None,
            )
            output = StringIO()
            with redirect_stdout(output):
                handled = handle_report_command(args, BotConfig())

        self.assertTrue(handled)
        self.assertIn("shadow_replay", output.getvalue())
        self.assertIn("record_count=0", output.getvalue())

    def test_handle_report_command_runs_backtest_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            db_path = str(base / "watchlist.sqlite")
            store = WatchlistStore(db_path)
            store.insert_snapshots([_snapshot()])
            store.insert_shadow_fills([_fill()])
            store.insert_shadow_marks([_snapshot(no_mid=0.5)])
            args = argparse.Namespace(
                validate_settlements=False,
                shadow_replay=False,
                calibration_report=False,
                backtest=True,
                dashboard_report=False,
                settlement_file=None,
                db_file=db_path,
                backtest_min_net_edge=0.0,
                backtest_max_spread=None,
                backtest_profile=None,
                backtest_event_type=None,
                backtest_target_source=None,
                backtest_from=None,
                backtest_to=None,
                backtest_min_samples=1,
                backtest_report=None,
                backtest_json=None,
            )
            output = StringIO()
            with redirect_stdout(output):
                handled = handle_report_command(args, BotConfig())

        self.assertTrue(handled)
        self.assertIn("backtest_report", output.getvalue())
        self.assertIn("samples=1", output.getvalue())

    def test_handle_report_command_runs_backtest_path_on_fresh_db(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "fresh.sqlite")
            args = argparse.Namespace(
                validate_settlements=False,
                shadow_replay=False,
                calibration_report=False,
                backtest=True,
                dashboard_report=False,
                settlement_file=None,
                db_file=db_path,
                backtest_min_net_edge=0.0,
                backtest_max_spread=None,
                backtest_profile=None,
                backtest_event_type=None,
                backtest_target_source=None,
                backtest_from=None,
                backtest_to=None,
                backtest_min_samples=1,
                backtest_report=None,
                backtest_json=None,
            )
            output = StringIO()
            with redirect_stdout(output):
                handled = handle_report_command(args, BotConfig())

        self.assertTrue(handled)
        self.assertIn("backtest_report", output.getvalue())
        self.assertIn("samples=0", output.getvalue())

    def test_handle_report_command_runs_validate_settlements_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            db_path = str(base / "watchlist.sqlite")
            settlement_path = str(base / "settlements.json")
            store = WatchlistStore(db_path)
            store.insert_shadow_fills([_fill()])
            Path(settlement_path).write_text(
                json.dumps(
                    [
                        {
                            "slug": "market",
                            "side": "BUY_NO",
                            "winning_side": "BUY_NO",
                            "status": "settled",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                validate_settlements=True,
                shadow_replay=False,
                calibration_report=False,
                backtest=False,
                dashboard_report=False,
                settlement_file=settlement_path,
                db_file=db_path,
                settlement_validation_json=None,
            )
            output = StringIO()
            with redirect_stdout(output):
                handled = handle_report_command(args, BotConfig())

        self.assertTrue(handled)
        self.assertIn("settlement_validation", output.getvalue())
        self.assertIn("valid=true", output.getvalue())
        self.assertIn("coverage_by_slug slug=market", output.getvalue())

    def test_handle_report_command_runs_validate_settlements_path_on_fresh_db(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            db_path = str(base / "fresh.sqlite")
            settlement_path = str(base / "settlements.json")
            Path(settlement_path).write_text("[]", encoding="utf-8")
            args = argparse.Namespace(
                validate_settlements=True,
                shadow_replay=False,
                calibration_report=False,
                backtest=False,
                dashboard_report=False,
                settlement_file=settlement_path,
                db_file=db_path,
                settlement_validation_json=None,
            )
            output = StringIO()
            with redirect_stdout(output):
                handled = handle_report_command(args, BotConfig())

        self.assertTrue(handled)
        self.assertIn("settlement_validation", output.getvalue())
        self.assertIn("shadow_fills=0", output.getvalue())

    def test_run_watchlist_loop_writes_snapshot_fill_and_mark(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            args = argparse.Namespace(
                iterations=1,
                poll_seconds=0,
                log_file=str(base / "watchlist_snapshots.jsonl"),
                alert_file=str(base / "watchlist_alerts.jsonl"),
                shadow_file=str(base / "shadow_fills.jsonl"),
                db_file=str(base / "watchlist.sqlite"),
                cache_file=str(base / "http_cache.sqlite"),
                gamma_cache_seconds=30.0,
                book_cache_seconds=10.0,
                api_rate_limit_seconds=0.1,
                alert_evidence_jump=0.15,
            )
            item = WatchlistItem(
                slug="market",
                label="Market",
                preferred_side="BUY_NO",
                entry_band_low=0.44,
                entry_band_high=0.50,
                note="pipeline",
            )
            market = Market(
                market_id="1",
                title="Will Artist release a new album?",
                description="Official streaming release",
                rules="Official release only",
                category="social",
                closes_at=datetime.now(timezone.utc) + timedelta(days=5),
                volume=5000,
                yes_bid=0.54,
                yes_ask=0.56,
                no_bid=0.44,
                no_ask=0.46,
                metadata={
                    "slug": "market",
                    "book_status": "complete",
                    "yes_ask_source": "book",
                    "no_ask_source": "book",
                },
            )
            collector = _FakeCollector()
            output = StringIO()
            signal = _FakeSignal()
            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", return_value=[market]),
                patch("bot.watchlist_runner.build_signal", return_value=signal),
                redirect_stdout(output),
            ):
                run_watchlist_loop(args, BotConfig(), collector, [item], [])

            text = output.getvalue()
            self.assertIn("appended_snapshots=1", text)
            self.assertIn("appended_shadow_fills=1", text)
            self.assertIn("inserted_shadow_marks=1", text)
            self.assertTrue(Path(args.db_file).exists())
            self.assertTrue(Path(args.log_file).exists())
            self.assertTrue(Path(args.shadow_file).exists())

    def test_run_watchlist_loop_emits_alert_when_market_enters_band(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            log_file = base / "watchlist_snapshots.jsonl"
            log_file.write_text(
                json.dumps(
                    {
                        "slug": "market",
                        "timestamp_utc": "2026-04-27T00:00:00+00:00",
                        "label": "Market",
                        "title": "Will Artist release a new album?",
                        "preferred_side": "BUY_NO",
                        "target_band_low": 0.44,
                        "target_band_high": 0.50,
                        "preferred_price": 0.40,
                        "in_target_band": False,
                        "evidence_score": 0.0,
                        "yes_bid": 0.59,
                        "yes_ask": 0.60,
                        "yes_mid": 0.595,
                        "no_bid": 0.39,
                        "no_ask": 0.40,
                        "no_mid": 0.395,
                        "market_ok": True,
                        "signal_ok": False,
                        "note": "prior",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            args = _runner_args(base)
            item = _item()
            market = _market(no_bid=0.44, no_ask=0.46)
            output = StringIO()
            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", return_value=[market]),
                patch("bot.watchlist_runner.build_signal", return_value=_FakeSignal()),
                redirect_stdout(output),
            ):
                run_watchlist_loop(args, BotConfig(), _FakeCollector(), [item], [])

            text = output.getvalue()
            self.assertIn("appended_alerts=1", text)
            self.assertIn("watchlist_alert slug=market reasons=entered_target_band,signal_turned_ok", text)

    def test_run_watchlist_loop_applies_settlements_before_iteration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            args = _runner_args(base)
            store = WatchlistStore(args.db_file)
            store.insert_shadow_fills([_fill()])
            output = StringIO()
            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", return_value=[]),
                redirect_stdout(output),
            ):
                run_watchlist_loop(
                    args,
                    BotConfig(),
                    _FakeCollector(),
                    [_item()],
                    [
                        _settlement(),
                    ],
                )

            self.assertIn("settlements_applied=1", output.getvalue())

    def test_run_watchlist_loop_reports_blocked_fill_when_portfolio_limits_reject_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            args = _runner_args(base)
            item = _item()
            market = _market()
            config = BotConfig(max_open_shadow_positions=0)
            output = StringIO()
            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", return_value=[market]),
                patch("bot.watchlist_runner.build_signal", return_value=_FakeSignal()),
                redirect_stdout(output),
            ):
                run_watchlist_loop(args, config, _FakeCollector(), [item], [])

            text = output.getvalue()
            self.assertIn("portfolio_candidates=1 accepted=0 blocked=1", text)
            self.assertIn("shadow_fill_blocked slug=market side=BUY_NO reasons=max_open_shadow_positions_reached", text)

    def test_run_watchlist_loop_multi_iteration_dedupes_alerts_and_fills(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            args = _runner_args(base)
            args.iterations = 3
            output = StringIO()
            low_edge_signal = _FakeSignal(net_edge=0.0)
            signals = [low_edge_signal, _FakeSignal(), _FakeSignal()]
            markets = [
                [_market(no_bid=0.39, no_ask=0.41)],
                [_market(no_bid=0.44, no_ask=0.46)],
                [_market(no_bid=0.45, no_ask=0.47)],
            ]
            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", side_effect=markets),
                patch("bot.watchlist_runner.build_signal", side_effect=signals),
                redirect_stdout(output),
            ):
                run_watchlist_loop(args, BotConfig(), _FakeCollector(), [_item()], [])

            text = output.getvalue()
            report = build_dashboard_report(args.db_file, limit=5)
            positions = load_positions(args.db_file)
            samples = load_backtest_samples(args.db_file)

        self.assertEqual(text.count("watchlist_iteration="), 3)
        self.assertEqual(text.count("watchlist_alert slug=market"), 1)
        self.assertEqual(text.count("appended_shadow_fills=1"), 1)
        self.assertEqual(text.count("inserted_shadow_marks=1"), 2)
        self.assertEqual(report["counts"]["snapshots"], 3)
        self.assertEqual(report["counts"]["alerts"], 1)
        self.assertEqual(report["counts"]["shadow_fills"], 1)
        self.assertEqual(report["counts"]["shadow_positions"], 1)
        self.assertEqual(positions[0].status, "open")
        self.assertEqual(samples[0].target_source, "latest_mark")

    def test_run_watchlist_loop_across_separate_runs_dedupes_alerts_and_fills(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            args = _runner_args(base)
            first_output = StringIO()
            second_output = StringIO()
            third_output = StringIO()
            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", return_value=[_market(no_bid=0.39, no_ask=0.41)]),
                patch("bot.watchlist_runner.build_signal", return_value=_FakeSignal(net_edge=0.0)),
                redirect_stdout(first_output),
            ):
                run_watchlist_loop(args, BotConfig(), _FakeCollector(), [_item()], [])

            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", return_value=[_market(no_bid=0.44, no_ask=0.46)]),
                patch("bot.watchlist_runner.build_signal", return_value=_FakeSignal()),
                redirect_stdout(second_output),
            ):
                run_watchlist_loop(args, BotConfig(), _FakeCollector(), [_item()], [])

            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", return_value=[_market(no_bid=0.45, no_ask=0.47)]),
                patch("bot.watchlist_runner.build_signal", return_value=_FakeSignal()),
                redirect_stdout(third_output),
            ):
                run_watchlist_loop(args, BotConfig(), _FakeCollector(), [_item()], [])

            report = build_dashboard_report(args.db_file, limit=5)
            samples = load_backtest_samples(args.db_file)
            positions = load_positions(args.db_file)

        self.assertNotIn("watchlist_alert slug=market", first_output.getvalue())
        self.assertIn("watchlist_alert slug=market reasons=entered_target_band,signal_turned_ok", second_output.getvalue())
        self.assertNotIn("watchlist_alert slug=market", third_output.getvalue())
        self.assertIn("appended_shadow_fills=1", second_output.getvalue())
        self.assertNotIn("appended_shadow_fills=1", third_output.getvalue())
        self.assertEqual(report["counts"]["snapshots"], 3)
        self.assertEqual(report["counts"]["alerts"], 1)
        self.assertEqual(report["counts"]["shadow_fills"], 1)
        self.assertEqual(report["counts"]["shadow_positions"], 1)
        self.assertEqual(positions[0].status, "open")
        self.assertEqual(samples[0].target_source, "latest_mark")

    def test_settlement_followed_by_watchlist_run_keeps_cross_command_views_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            args = _runner_args(base)
            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", return_value=[_market()]),
                patch("bot.watchlist_runner.build_signal", return_value=_FakeSignal()),
                redirect_stdout(StringIO()),
            ):
                run_watchlist_loop(args, BotConfig(), _FakeCollector(), [_item()], [])

            followup_output = StringIO()
            settlements = [_settlement()]
            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", return_value=[_market(no_bid=0.45, no_ask=0.47)]),
                patch("bot.watchlist_runner.build_signal", return_value=_FakeSignal()),
                redirect_stdout(followup_output),
            ):
                run_watchlist_loop(args, BotConfig(), _FakeCollector(), [_item()], settlements)

            replay = replay_shadow_pnl(args.db_file, settlements)
            dashboard = build_dashboard_report(args.db_file, limit=5, config=BotConfig(), settlements=settlements)
            samples = load_backtest_samples(args.db_file, settlements)
            portfolio = load_portfolio_risk_state(args.db_file, BotConfig(), settlements)
            positions = load_positions(args.db_file, settlements)

        self.assertIn("settlements_applied=1", followup_output.getvalue())
        self.assertIn("portfolio_risk open_positions=0", followup_output.getvalue())
        self.assertNotIn("appended_shadow_fills=1", followup_output.getvalue())
        self.assertEqual(replay["record_count"], 1)
        self.assertEqual(replay["records"][0]["status"], "settled")
        self.assertEqual(positions[0].status, "settled")
        self.assertEqual(positions[0].close_source, "settlement_file")
        self.assertEqual(dashboard["counts"]["shadow_positions"], 1)
        self.assertEqual(dashboard["backtest_summary"]["settled_samples"], 1)
        self.assertEqual(dashboard["backtest_target_source_counts"]["settlement_file"], 1)
        self.assertEqual(dashboard["portfolio_risk"]["open_positions"], 0)
        self.assertEqual(samples[0].target_source, "settlement_file")
        self.assertEqual(portfolio.open_positions, 0)

    def test_settlement_keeps_workflow_reports_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            args = _runner_args(base)
            with (
                patch("bot.watchlist_runner.load_live_markets_by_slugs", return_value=[_market()]),
                patch("bot.watchlist_runner.build_signal", return_value=_FakeSignal()),
                redirect_stdout(StringIO()),
            ):
                run_watchlist_loop(args, BotConfig(), _FakeCollector(), [_item()], [])

            settlements = [_settlement()]
            replay = replay_shadow_pnl(args.db_file, settlements)
            dashboard = build_dashboard_report(args.db_file, limit=5, config=BotConfig(), settlements=settlements)
            samples = load_backtest_samples(args.db_file, settlements)
            portfolio = load_portfolio_risk_state(args.db_file, BotConfig(), settlements)
            positions = load_positions(args.db_file, settlements)

            settlement_path = base / "settlements.json"
            settlement_path.write_text(
                json.dumps(
                    [
                        {
                            "slug": "market",
                            "winning_side": "BUY_NO",
                            "status": "settled",
                            "timestamp_utc": "2026-06-30T00:00:00+00:00",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            replay_output = StringIO()
            dashboard_output = StringIO()
            backtest_output = StringIO()
            with redirect_stdout(replay_output):
                handled_replay = handle_report_command(
                    argparse.Namespace(
                        validate_settlements=False,
                        shadow_replay=True,
                        calibration_report=False,
                        backtest=False,
                        dashboard_report=False,
                        settlement_file=str(settlement_path),
                        db_file=args.db_file,
                        replay_json=None,
                    ),
                    BotConfig(),
                )
            with redirect_stdout(dashboard_output):
                handled_dashboard = handle_report_command(
                    argparse.Namespace(
                        validate_settlements=False,
                        shadow_replay=False,
                        calibration_report=False,
                        backtest=False,
                        dashboard_report=True,
                        settlement_file=str(settlement_path),
                        db_file=args.db_file,
                        report_limit=5,
                        report_file=None,
                        report_json=None,
                        report_html=None,
                    ),
                    BotConfig(),
                )
            with redirect_stdout(backtest_output):
                handled_backtest = handle_report_command(
                    argparse.Namespace(
                        validate_settlements=False,
                        shadow_replay=False,
                        calibration_report=False,
                        backtest=True,
                        dashboard_report=False,
                        settlement_file=str(settlement_path),
                        db_file=args.db_file,
                        backtest_min_net_edge=0.0,
                        backtest_max_spread=None,
                        backtest_profile=None,
                        backtest_event_type=None,
                        backtest_target_source=None,
                        backtest_from=None,
                        backtest_to=None,
                        backtest_min_samples=1,
                        backtest_report=None,
                        backtest_json=None,
                    ),
                    BotConfig(),
                )

        self.assertTrue(handled_replay)
        self.assertTrue(handled_dashboard)
        self.assertTrue(handled_backtest)
        self.assertEqual(replay["record_count"], 1)
        self.assertEqual(replay["records"][0]["status"], "settled")
        self.assertAlmostEqual(replay["records"][0]["pnl"], 23.4783, places=4)
        self.assertEqual(positions[0].status, "settled")
        self.assertEqual(positions[0].close_source, "settlement_file")
        self.assertEqual(dashboard["counts"]["shadow_positions"], 1)
        self.assertEqual(dashboard["backtest_summary"]["settled_samples"], 1)
        self.assertEqual(dashboard["backtest_target_source_counts"]["settlement_file"], 1)
        self.assertEqual(dashboard["portfolio_risk"]["open_positions"], 0)
        self.assertAlmostEqual(dashboard["shadow_positions"][0]["pnl"], 23.4783, places=4)
        self.assertEqual(samples[0].target_source, "settlement_file")
        self.assertAlmostEqual(samples[0].realized_pnl, 23.4783, places=4)
        self.assertEqual(portfolio.open_positions, 0)
        self.assertEqual(portfolio.total_exposure, 0.0)
        self.assertIn("status=settled", replay_output.getvalue())
        self.assertIn("settled_samples=1", dashboard_output.getvalue())
        self.assertIn("open_positions=0", dashboard_output.getvalue())
        self.assertIn("target_sources=settlement_file:1", backtest_output.getvalue())


class _FakeCollector:
    def collect(self, parsed, now):
        return Evidence(
            score=0.3,
            confidence=0.8,
            reasons=["evidence_source=test"],
            mode="source",
            preheat_score=0.4,
            cadence_score=0.3,
            partner_score=0.2,
        )


class _FakeSignal:
    def __init__(
        self,
        *,
        side: str = "BUY_NO",
        p_model: float = 0.42,
        p_mid: float = 0.55,
        edge: float = 0.12,
        net_edge: float = 0.04,
        max_entry_price: float = 0.48,
        confidence: float = 0.8,
        reasons: list[str] | None = None,
        profile_name: str = "music_release",
    ) -> None:
        self.side = side
        self.p_model = p_model
        self.p_mid = p_mid
        self.edge = edge
        self.net_edge = net_edge
        self.max_entry_price = max_entry_price
        self.confidence = confidence
        self.reasons = reasons or ["model_profile=music_release"]
        self.profile_name = profile_name


def _runner_args(base: Path) -> argparse.Namespace:
    return argparse.Namespace(
        iterations=1,
        poll_seconds=0,
        log_file=str(base / "watchlist_snapshots.jsonl"),
        alert_file=str(base / "watchlist_alerts.jsonl"),
        shadow_file=str(base / "shadow_fills.jsonl"),
        db_file=str(base / "watchlist.sqlite"),
        cache_file=str(base / "http_cache.sqlite"),
        gamma_cache_seconds=30.0,
        book_cache_seconds=10.0,
        api_rate_limit_seconds=0.1,
        alert_evidence_jump=0.15,
    )


def _item() -> WatchlistItem:
    return WatchlistItem(
        slug="market",
        label="Market",
        preferred_side="BUY_NO",
        entry_band_low=0.44,
        entry_band_high=0.50,
        note="pipeline",
    )


def _market(no_bid: float = 0.44, no_ask: float = 0.46) -> Market:
    yes_bid = round(1.0 - no_ask, 4)
    yes_ask = round(1.0 - no_bid, 4)
    return Market(
        market_id="1",
        title="Will Artist release a new album?",
        description="Official streaming release",
        rules="Official release only",
        category="social",
        closes_at=datetime.now(timezone.utc) + timedelta(days=5),
        volume=5000,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=no_bid,
        no_ask=no_ask,
        metadata={
            "slug": "market",
            "book_status": "complete",
            "yes_ask_source": "book",
            "no_ask_source": "book",
        },
    )


def _snapshot(no_mid: float = 0.455) -> dict[str, object]:
    return {
        "timestamp_utc": "2026-04-27T00:01:00+00:00",
        "slug": "market",
        "label": "Market",
        "market_id": "1",
        "title": "Will Artist release a new album?",
        "subject": "Artist",
        "platform": "streaming",
        "event_type": "content_release",
        "preferred_side": "BUY_NO",
        "preferred_price": no_mid,
        "in_target_band": True,
        "yes_bid": round(1 - no_mid - 0.005, 4),
        "yes_ask": round(1 - no_mid + 0.005, 4),
        "yes_mid": round(1 - no_mid, 4),
        "no_bid": round(no_mid - 0.005, 4),
        "no_ask": round(no_mid + 0.005, 4),
        "no_mid": no_mid,
        "no_spread": 0.01,
        "book_status": "complete",
        "yes_ask_source": "book",
        "no_ask_source": "book",
        "evidence_score": 0.3,
        "evidence_confidence": 0.8,
        "evidence_mode": "source",
        "model_side": "BUY_NO",
        "p_model": 0.42,
        "p_mid": round(1 - no_mid, 4),
        "edge": 0.12,
        "net_edge": 0.04,
        "max_entry_price": 0.48,
        "signal_ok": True,
        "market_ok": True,
        "signal_reasons_detail": ["model_profile=music_release"],
    }


def _fill() -> dict[str, object]:
    return {
        "timestamp_utc": "2026-04-27T00:01:30+00:00",
        "slug": "market",
        "label": "Market",
        "market_id": "1",
        "event_type": "content_release",
        "platform": "streaming",
        "side": "BUY_NO",
        "fill_price": 0.46,
        "max_entry_price": 0.48,
        "net_edge": 0.04,
        "reason": "ask_at_or_below_max_entry",
        "snapshot_timestamp_utc": "2026-04-27T00:01:00+00:00",
    }


def _settlement():
    from bot.settlements import Settlement

    return Settlement(
        slug="market",
        side=None,
        status="settled",
        close_price=None,
        winning_side="BUY_NO",
        timestamp_utc="2026-06-30T00:00:00+00:00",
        note="resolved no",
    )


if __name__ == "__main__":
    unittest.main()
