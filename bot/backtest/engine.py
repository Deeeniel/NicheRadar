from __future__ import annotations

from dataclasses import dataclass

from bot.domain import SnapshotRecord, profile_name_from_snapshot


@dataclass(frozen=True)
class BacktestStrategyParams:
    min_net_edge: float = 0.0
    max_spread: float | None = None
    entry_price_mode: str = "ask"
    model_profile: str | None = None
    event_type: str | None = None


@dataclass(frozen=True)
class BacktestEntry:
    eligible: bool
    fill_price: float | None
    reason: str


def evaluate_shadow_entry(snapshot: dict[str, object], params: BacktestStrategyParams | None = None) -> BacktestEntry:
    strategy = params or BacktestStrategyParams()
    snapshot_record = SnapshotRecord.from_mapping(snapshot)
    if strategy.entry_price_mode != "ask":
        raise ValueError("Only entry_price_mode='ask' is supported.")

    if strategy.model_profile and profile_name_from_snapshot(snapshot_record) != strategy.model_profile:
        return BacktestEntry(False, None, "profile_filter")
    if strategy.event_type and str(snapshot_record.event_type or "unknown") != strategy.event_type:
        return BacktestEntry(False, None, "event_type_filter")
    if snapshot_record.market_ok is not True:
        return BacktestEntry(False, None, "market_not_ok")
    if snapshot_record.signal_ok is not True:
        return BacktestEntry(False, None, "signal_not_ok")

    side = str(snapshot_record.model_side or "")
    if side not in {"BUY_YES", "BUY_NO"}:
        return BacktestEntry(False, None, "unsupported_side")
    if side != snapshot_record.preferred_side:
        return BacktestEntry(False, None, "model_side_not_preferred")

    net_edge = snapshot_record.net_edge
    if net_edge is None or net_edge < strategy.min_net_edge:
        return BacktestEntry(False, None, "net_edge_below_min")

    spread = snapshot_record.side_spread(side)
    if strategy.max_spread is not None and (spread is None or spread > strategy.max_spread):
        return BacktestEntry(False, None, "spread_above_max")

    max_entry_price = snapshot_record.max_entry_price
    ask_price = snapshot_record.ask_for_side(side)
    if max_entry_price is None or ask_price is None:
        return BacktestEntry(False, None, "missing_entry_price")
    if ask_price > max_entry_price:
        return BacktestEntry(False, None, "ask_above_max_entry")

    return BacktestEntry(True, ask_price, "ask_at_or_below_max_entry")
