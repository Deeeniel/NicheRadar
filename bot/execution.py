from __future__ import annotations

from bot.models import ParsedMarket, Signal, TradeIdea


def build_trade_idea(parsed: ParsedMarket, signal: Signal) -> TradeIdea:
    return TradeIdea(
        market_id=parsed.market.market_id,
        title=parsed.market.title,
        action="PLACE_MAKER_ORDER",
        side=signal.side,
        target_price=signal.max_entry_price,
        net_edge=signal.net_edge,
        reasons=signal.reasons,
    )


import json
from datetime import datetime, timezone
from pathlib import Path

from bot.config import BotConfig
from bot.domain import ShadowFillRecord, SnapshotRecord


def build_shadow_fills(snapshots: list[dict[str, object]], config: BotConfig | None = None) -> list[dict[str, object]]:
    fills: list[dict[str, object]] = []
    risk_amount = _risk_amount(config)
    for raw_snapshot in snapshots:
        snapshot = SnapshotRecord.from_mapping(raw_snapshot)
        if snapshot.market_ok is not True:
            continue
        if snapshot.signal_ok is not True:
            continue

        side = snapshot.model_side or ""
        if side != snapshot.preferred_side:
            continue
        if snapshot.ask_source_for_side(side) != "book":
            continue
        max_entry_price = snapshot.max_entry_price
        ask_price = snapshot.ask_for_side(side)
        if max_entry_price is None or ask_price is None:
            continue

        if ask_price <= max_entry_price:
            fill = ShadowFillRecord(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                slug=snapshot.slug,
                label=snapshot.label,
                market_id=snapshot.market_id,
                event_type=snapshot.event_type,
                platform=snapshot.platform,
                side=side,
                fill_price=ask_price,
                risk_amount=risk_amount,
                share_quantity=round(risk_amount / ask_price, 4) if ask_price > 0 else None,
                max_entry_price=max_entry_price,
                net_edge=snapshot.net_edge,
                reason="ask_at_or_below_max_entry",
                position_status="open",
                snapshot_timestamp_utc=snapshot.timestamp_utc,
            )
            fills.append(
                {
                    "record_type": "shadow_fill",
                    "timestamp_utc": fill.timestamp_utc,
                    "slug": fill.slug,
                    "label": fill.label,
                    "market_id": fill.market_id,
                    "title": snapshot.title,
                    "event_type": fill.event_type,
                    "platform": fill.platform,
                    "side": fill.side,
                    "fill_price": fill.fill_price,
                    "share_quantity": fill.share_quantity,
                    "risk_amount": fill.risk_amount,
                    "max_entry_price": fill.max_entry_price,
                    "net_edge": fill.net_edge,
                    "reason": fill.reason,
                    "position_status": fill.position_status,
                    "snapshot_timestamp_utc": fill.snapshot_timestamp_utc,
                }
            )
    return fills


def append_shadow_fills(path: str, fills: list[dict[str, object]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for fill in fills:
            handle.write(json.dumps(fill, ensure_ascii=True) + "\n")
def _risk_amount(config: BotConfig | None) -> float:
    if config is None:
        return 20.0
    return round(config.shadow_bankroll * config.shadow_position_risk_pct, 4)
