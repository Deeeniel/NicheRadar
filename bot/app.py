from __future__ import annotations

import argparse
from datetime import timezone

from bot.config import BotConfig
from bot.evidence_collector import EvidenceCollector
from bot.execution import build_trade_idea
from bot.market_parser import parse_market, utc_now
from bot.market_scanner import load_live_markets, load_sample_markets
from bot.report_commands import handle_report_command
from bot.risk_manager import allow_market, allow_signal
from bot.settlements import load_settlements
from bot.signal_engine import build_signal
from bot.watchlist import load_watchlist
from bot.watchlist_runner import run_watchlist_loop


def run_cli(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    config = build_config(args)

    try:
        if handle_report_command(args, config):
            return
    except ValueError as exc:
        parser.error(str(exc))

    collector = build_evidence_collector(args)
    watchlist_items = load_watchlist(args.watchlist) if args.watchlist else []
    settlements = load_settlements(args.settlement_file)
    if watchlist_items:
        watchlist_config = build_config(args, max_days_to_expiry=args.watchlist_max_days)
        run_watchlist_loop(args, watchlist_config, collector, watchlist_items, settlements)
        return

    _run_scan_mode(args, parser, config, collector)


def build_config(args: argparse.Namespace, max_days_to_expiry: float | None = None) -> BotConfig:
    return BotConfig(
        max_days_to_expiry=max_days_to_expiry if max_days_to_expiry is not None else BotConfig.max_days_to_expiry,
        shadow_bankroll=args.shadow_bankroll,
        shadow_position_risk_pct=args.shadow_position_risk_pct,
        max_total_risk_pct=args.max_total_risk_pct,
        max_market_risk_pct=args.max_market_risk_pct,
        max_event_type_risk_pct=args.max_event_type_risk_pct,
        circuit_breaker_loss_pct=args.circuit_breaker_loss_pct,
        max_open_shadow_positions=args.max_open_shadow_positions,
    )


def build_evidence_collector(args: argparse.Namespace) -> EvidenceCollector:
    return EvidenceCollector(
        args.evidence_sources,
        cache_path=args.cache_file,
        cache_seconds=args.rss_cache_seconds,
        rate_limit_seconds=args.rss_rate_limit_seconds,
    )


def load_scan_markets(args: argparse.Namespace, parser: argparse.ArgumentParser):
    if args.live:
        return load_live_markets(
            limit=args.limit,
            cache_path=args.cache_file,
            gamma_cache_seconds=args.gamma_cache_seconds,
            book_cache_seconds=args.book_cache_seconds,
            rate_limit_seconds=args.api_rate_limit_seconds,
        )
    if args.sample_data:
        return load_sample_markets(args.sample_data)
    parser.error("Provide --watchlist, or either --live or --sample-data.")


def _run_scan_mode(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    config: BotConfig,
    collector: EvidenceCollector,
) -> None:
    markets = load_scan_markets(args, parser)
    now = utc_now().astimezone(timezone.utc)

    print("PolyMarket shadow bot")
    print(f"loaded_markets={len(markets)}")

    ideas = []
    for market in markets:
        parsed = parse_market(market, now)
        if parsed is None:
            continue

        allowed_market, market_reasons = allow_market(parsed, config)
        evidence = collector.collect(parsed, now)
        signal = build_signal(parsed, evidence, config)
        allowed_signal, signal_reasons = allow_signal(signal, config)

        if not allowed_market:
            print(f"skip_market={market.market_id} reasons={','.join(market_reasons)}")
            continue
        if not allowed_signal:
            print(f"skip_signal={market.market_id} reasons={','.join(signal_reasons)}")
            continue

        ideas.append(build_trade_idea(parsed, signal))

    if not ideas:
        print("no_trade_ideas")
        return

    for idea in ideas:
        print(
            "trade_idea "
            f"market_id={idea.market_id} "
            f"side={idea.side} "
            f"price={idea.target_price:.4f} "
            f"net_edge={idea.net_edge:.4f} "
            f"title={idea.title}"
        )
        for reason in idea.reasons:
            print(f"  reason={reason}")
