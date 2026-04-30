from __future__ import annotations

import argparse

from bot.backtest.calibration import (
    build_calibration_report,
    format_calibration_report,
    write_calibration_json,
    write_calibration_markdown,
)
from bot.backtest.dataset import load_backtest_samples
from bot.backtest.engine import BacktestStrategyParams
from bot.backtest.reporting import (
    build_backtest_report,
    format_backtest_report,
    write_backtest_json,
    write_backtest_markdown,
)
from bot.backtest.replay import format_shadow_replay_report, replay_shadow_pnl, write_replay_json
from bot.backtest.validation import (
    format_settlement_validation,
    validate_settlements,
    write_settlement_validation_json,
)
from bot.config import BotConfig
from bot.reporting import (
    build_dashboard_report,
    format_dashboard_report,
    write_dashboard_html,
    write_dashboard_json,
    write_dashboard_markdown,
)
from bot.settlements import load_settlements
from bot.storage import WatchlistStore


def handle_report_command(args: argparse.Namespace, config: BotConfig | None = None) -> bool:
    if args.validate_settlements:
        if not args.settlement_file:
            raise ValueError("--validate-settlements requires --settlement-file.")
        _ensure_store(args.db_file)
        settlements = load_settlements(args.settlement_file)
        report = validate_settlements(args.db_file, settlements)
        for line in format_settlement_validation(report):
            print(line)
        if args.settlement_validation_json:
            write_settlement_validation_json(args.settlement_validation_json, report)
            print(f"wrote_settlement_validation_json={args.settlement_validation_json}")
        return True

    if args.shadow_replay:
        _ensure_store(args.db_file)
        settlements = load_settlements(args.settlement_file)
        replay = replay_shadow_pnl(args.db_file, settlements)
        for line in format_shadow_replay_report(replay):
            print(line)
        if args.replay_json:
            write_replay_json(args.replay_json, replay)
            print(f"wrote_replay_json={args.replay_json}")
        return True

    if args.calibration_report:
        _ensure_store(args.db_file)
        settlements = load_settlements(args.settlement_file)
        report = build_calibration_report(args.db_file, settlements, args.calibration_min_samples)
        for line in format_calibration_report(report):
            print(line)
        if args.calibration_file:
            write_calibration_markdown(args.calibration_file, report)
            print(f"wrote_calibration_file={args.calibration_file}")
        if args.calibration_json:
            write_calibration_json(args.calibration_json, report)
            print(f"wrote_calibration_json={args.calibration_json}")
        return True

    if args.backtest:
        _ensure_store(args.db_file)
        settlements = load_settlements(args.settlement_file)
        params = BacktestStrategyParams(
            min_net_edge=args.backtest_min_net_edge,
            max_spread=args.backtest_max_spread,
            model_profile=args.backtest_profile,
            event_type=args.backtest_event_type,
        )
        samples = load_backtest_samples(
            args.db_file,
            settlements,
            params,
            target_source=args.backtest_target_source,
            start_date=args.backtest_from,
            end_date=args.backtest_to,
        )
        report = build_backtest_report(samples, args.db_file, args.backtest_min_samples)
        for line in format_backtest_report(report):
            print(line)
        if args.backtest_report:
            write_backtest_markdown(args.backtest_report, report)
            print(f"wrote_backtest_report={args.backtest_report}")
        if args.backtest_json:
            write_backtest_json(args.backtest_json, report)
            print(f"wrote_backtest_json={args.backtest_json}")
        return True

    if args.dashboard_report:
        _ensure_store(args.db_file)
        settlements = load_settlements(args.settlement_file)
        report = build_dashboard_report(args.db_file, args.report_limit, config or BotConfig(), settlements)
        for line in format_dashboard_report(report):
            print(line)
        if args.report_file:
            write_dashboard_markdown(args.report_file, report)
            print(f"wrote_report_file={args.report_file}")
        if args.report_json:
            write_dashboard_json(args.report_json, report)
            print(f"wrote_report_json={args.report_json}")
        if args.report_html:
            write_dashboard_html(args.report_html, report)
            print(f"wrote_report_html={args.report_html}")
        return True

    return False


def _ensure_store(db_path: str | None) -> None:
    if db_path:
        WatchlistStore(db_path)
