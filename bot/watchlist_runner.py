from __future__ import annotations

import argparse
from datetime import datetime, timezone
import time

from bot.config import BotConfig
from bot.evidence_collector import EvidenceCollector
from bot.execution import append_shadow_fills, build_shadow_fills
from bot.market_parser import parse_market, utc_now
from bot.market_scanner import load_live_markets_by_slugs
from bot.risk_manager import allow_market, allow_signal, filter_shadow_fills_for_portfolio, load_portfolio_risk_state
from bot.settlements import Settlement
from bot.signal_engine import build_signal
from bot.storage import WatchlistStore
from bot.watchlist import (
    append_watchlist_alerts,
    append_watchlist_snapshots,
    build_watchlist_alerts,
    build_watchlist_report,
    build_watchlist_snapshot,
    load_latest_watchlist_snapshots,
)


def run_watchlist_loop(
    args: argparse.Namespace,
    config: BotConfig,
    collector: EvidenceCollector,
    watchlist_items,
    settlements: list[Settlement],
) -> None:
    iterations = max(1, args.iterations)
    poll_seconds = max(0, args.poll_seconds)
    slugs = [item.slug for item in watchlist_items]
    previous_by_slug = load_latest_watchlist_snapshots(args.log_file)
    store = WatchlistStore(args.db_file) if args.db_file else None
    if store is not None and settlements:
        updated_positions = store.apply_settlements(settlements)
        if updated_positions:
            print(f"settlements_applied={updated_positions}")

    for iteration in range(1, iterations + 1):
        now = utc_now().astimezone(timezone.utc)
        markets = load_live_markets_by_slugs(
            slugs,
            cache_path=args.cache_file,
            gamma_cache_seconds=args.gamma_cache_seconds,
            book_cache_seconds=args.book_cache_seconds,
            rate_limit_seconds=args.api_rate_limit_seconds,
        )
        market_by_slug = {str(market.metadata.get("slug", "")): market for market in markets}
        snapshots: list[dict[str, object]] = []

        print("PolyMarket shadow bot")
        print(f"watchlist_iteration={iteration}/{iterations} timestamp_utc={datetime.now(timezone.utc).isoformat()}")
        print(f"loaded_markets={len(markets)}")

        if not market_by_slug:
            print("no_watchlist_markets")
        for item in watchlist_items:
            market = market_by_slug.get(item.slug)
            if market is None:
                print(f"missing_watchlist_market slug={item.slug}")
                continue

            parsed = parse_market(market, now)
            if parsed is None:
                print(f"unparsed_watchlist_market slug={item.slug}")
                continue

            allowed_market, market_reasons = allow_market(parsed, config)
            evidence = collector.collect(parsed, now)
            signal = build_signal(parsed, evidence, config)
            allowed_signal, signal_reasons = allow_signal(signal, config)

            snapshots.append(
                build_watchlist_snapshot(
                    item,
                    market,
                    parsed,
                    evidence,
                    signal,
                    allowed_market,
                    market_reasons,
                    allowed_signal,
                    signal_reasons,
                )
            )
            for line in build_watchlist_report(
                item,
                market,
                parsed,
                signal,
                allowed_market,
                market_reasons,
                allowed_signal,
                signal_reasons,
            ):
                print(line)

        if snapshots:
            alerts = build_watchlist_alerts(previous_by_slug, snapshots, args.alert_evidence_jump)
            shadow_fills = build_shadow_fills(snapshots, config)
            blocked_shadow_fills: list[dict[str, object]] = []
            settled_slugs = {settlement.slug for settlement in settlements}
            if settled_slugs:
                candidate_fills = shadow_fills
                shadow_fills = [fill for fill in shadow_fills if str(fill.get("slug")) not in settled_slugs]
                for fill in candidate_fills:
                    if str(fill.get("slug")) in settled_slugs:
                        fill["portfolio_risk_ok"] = False
                        fill["portfolio_risk_reasons"] = ["settlement_market_closed"]
                        blocked_shadow_fills.append(fill)
            if store is not None:
                shadow_fills = store.filter_new_shadow_fills(shadow_fills)
            portfolio_state = load_portfolio_risk_state(args.db_file if store is not None else None, config, settlements)
            print(
                "portfolio_risk "
                f"open_positions={portfolio_state.open_positions} "
                f"total_exposure={portfolio_state.total_exposure:.4f} "
                f"total_exposure_pct={portfolio_state.total_exposure_pct:.2%} "
                f"unrealized_pnl={portfolio_state.unrealized_pnl:.4f} "
                f"circuit_breaker={str(portfolio_state.circuit_breaker_active).lower()} "
                f"state_error={portfolio_state.state_load_error or 'none'}"
            )
            if shadow_fills:
                candidate_fills = shadow_fills
                candidate_count = len(shadow_fills)
                shadow_fills, _ = filter_shadow_fills_for_portfolio(
                    args.db_file if store is not None else None,
                    candidate_fills,
                    config,
                    settlements,
                )
                blocked_shadow_fills.extend(fill for fill in candidate_fills if fill.get("portfolio_risk_ok") is False)
                print(f"portfolio_candidates={candidate_count} accepted={len(shadow_fills)} blocked={candidate_count - len(shadow_fills)}")
            append_watchlist_snapshots(args.log_file, snapshots)
            print(f"appended_snapshots={len(snapshots)} log_file={args.log_file}")
            if store is not None:
                store.insert_snapshots(snapshots)
                store.insert_evidence_runs(snapshots)
            previous_by_slug.update({str(snapshot["slug"]): snapshot for snapshot in snapshots})
            if alerts:
                append_watchlist_alerts(args.alert_file, alerts)
                print(f"appended_alerts={len(alerts)} alert_file={args.alert_file}")
                if store is not None:
                    store.insert_alerts(alerts)
                for alert in alerts:
                    print(f"watchlist_alert slug={alert['slug']} reasons={','.join(alert['alert_reasons'])}")
            if shadow_fills:
                append_shadow_fills(args.shadow_file, shadow_fills)
                print(f"appended_shadow_fills={len(shadow_fills)} shadow_file={args.shadow_file}")
                if store is not None:
                    store.insert_shadow_fills(shadow_fills)
                for fill in shadow_fills:
                    print(
                        "shadow_fill "
                        f"slug={fill['slug']} side={fill['side']} "
                        f"fill_price={float(fill['fill_price']):.4f} "
                        f"risk_amount={float(fill.get('portfolio_risk_amount') or fill.get('risk_amount') or 0):.4f} "
                        f"max_entry_price={float(fill['max_entry_price']):.4f}"
                    )
            for fill in blocked_shadow_fills:
                print(
                    "shadow_fill_blocked "
                    f"slug={fill.get('slug')} side={fill.get('side')} "
                    f"reasons={','.join(str(reason) for reason in fill.get('portfolio_risk_reasons', []))}"
                )
            if store is not None:
                inserted_marks = store.insert_shadow_marks(snapshots)
                if inserted_marks:
                    print(f"inserted_shadow_marks={inserted_marks} db_file={args.db_file}")

        if iteration < iterations and poll_seconds > 0:
            time.sleep(poll_seconds)
