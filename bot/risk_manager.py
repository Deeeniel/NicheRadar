from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bot.config import BotConfig
from bot.domain import PositionRecord
from bot.positions import open_positions
from bot.settlements import Settlement


@dataclass(frozen=True)
class PortfolioRiskState:
    bankroll: float
    open_positions: int
    remaining_position_slots: int
    total_exposure: float
    total_exposure_pct: float
    remaining_total_risk_capacity: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    loss_limit_headroom: float
    circuit_breaker_active: bool
    circuit_breaker_reasons: list[str]
    state_load_error: str | None
    exposure_by_event_type: dict[str, float]
    exposure_by_platform: dict[str, float]
    exposure_by_slug: dict[str, float]


def filter_shadow_fills_for_portfolio(
    db_path: str | None,
    candidate_fills: list[dict[str, object]],
    config: BotConfig,
    settlements: list[Settlement] | None = None,
) -> tuple[list[dict[str, object]], PortfolioRiskState]:
    state = load_portfolio_risk_state(db_path, config, settlements)
    accepted: list[dict[str, object]] = []
    working_total = state.total_exposure
    working_open_positions = state.open_positions
    working_by_event_type = dict(state.exposure_by_event_type)
    working_by_slug = dict(state.exposure_by_slug)

    for fill in candidate_fills:
        reasons = list(state.circuit_breaker_reasons)
        slug = str(fill.get("slug") or "unknown")
        event_type = str(fill.get("event_type") or "unknown")
        risk_amount = _fill_risk_amount(fill, config)

        if working_open_positions >= config.max_open_shadow_positions:
            reasons.append("max_open_shadow_positions_reached")
        if working_total + risk_amount > config.shadow_bankroll * config.max_total_risk_pct:
            reasons.append("total_exposure_limit")
        if working_by_slug.get(slug, 0.0) + risk_amount > config.shadow_bankroll * config.max_market_risk_pct:
            reasons.append("market_exposure_limit")
        if working_by_event_type.get(event_type, 0.0) + risk_amount > config.shadow_bankroll * config.max_event_type_risk_pct:
            reasons.append("event_type_exposure_limit")

        fill["portfolio_risk_amount"] = risk_amount
        fill["portfolio_total_exposure_before"] = round(working_total, 4)
        fill["portfolio_event_type_exposure_before"] = round(working_by_event_type.get(event_type, 0.0), 4)
        fill["portfolio_slug_exposure_before"] = round(working_by_slug.get(slug, 0.0), 4)

        if reasons:
            fill["portfolio_risk_ok"] = False
            fill["portfolio_risk_reasons"] = reasons
            continue

        fill["portfolio_risk_ok"] = True
        fill["portfolio_risk_reasons"] = []
        accepted.append(fill)
        working_total = round(working_total + risk_amount, 4)
        working_open_positions += 1
        working_by_event_type[event_type] = round(working_by_event_type.get(event_type, 0.0) + risk_amount, 4)
        working_by_slug[slug] = round(working_by_slug.get(slug, 0.0) + risk_amount, 4)

    return accepted, state


def load_portfolio_risk_state(
    db_path: str | None,
    config: BotConfig,
    settlements: list[Settlement] | None = None,
) -> PortfolioRiskState:
    positions, state_load_error = _load_open_positions(db_path, settlements)
    return portfolio_risk_state_from_positions(positions, config, state_load_error)


def portfolio_risk_state_from_positions(
    positions: list[dict[str, object]] | list[PositionRecord],
    config: BotConfig,
    state_load_error: str | None = None,
) -> PortfolioRiskState:
    normalized = [_position_row(position) for position in positions]
    total_exposure = round(sum(position["risk_amount"] for position in normalized), 4)
    unrealized_pnl = round(sum(position["unrealized_pnl"] for position in normalized), 4)
    by_event_type: dict[str, float] = defaultdict(float)
    by_platform: dict[str, float] = defaultdict(float)
    by_slug: dict[str, float] = defaultdict(float)
    for position in normalized:
        by_event_type[str(position["event_type"])] += float(position["risk_amount"])
        by_platform[str(position["platform"])] += float(position["risk_amount"])
        by_slug[str(position["slug"])] += float(position["risk_amount"])

    reasons: list[str] = []
    if state_load_error is not None:
        reasons.append("portfolio_state_unavailable")
    if len(normalized) >= config.max_open_shadow_positions:
        reasons.append("max_open_shadow_positions_reached")
    if unrealized_pnl <= -config.shadow_bankroll * config.circuit_breaker_loss_pct:
        reasons.append("portfolio_loss_limit")

    max_total_capacity = max(0.0, config.shadow_bankroll * config.max_total_risk_pct)
    remaining_total_capacity = round(max(0.0, max_total_capacity - total_exposure), 4)
    loss_limit = config.shadow_bankroll * config.circuit_breaker_loss_pct
    loss_limit_headroom = round(max(0.0, loss_limit + unrealized_pnl), 4)

    return PortfolioRiskState(
        bankroll=config.shadow_bankroll,
        open_positions=len(normalized),
        remaining_position_slots=max(0, config.max_open_shadow_positions - len(normalized)),
        total_exposure=total_exposure,
        total_exposure_pct=round(total_exposure / config.shadow_bankroll, 6) if config.shadow_bankroll > 0 else 0.0,
        remaining_total_risk_capacity=remaining_total_capacity,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=round(unrealized_pnl / config.shadow_bankroll, 6) if config.shadow_bankroll > 0 else 0.0,
        loss_limit_headroom=loss_limit_headroom,
        circuit_breaker_active=bool(reasons),
        circuit_breaker_reasons=reasons,
        state_load_error=state_load_error,
        exposure_by_event_type={key: round(value, 4) for key, value in sorted(by_event_type.items())},
        exposure_by_platform={key: round(value, 4) for key, value in sorted(by_platform.items())},
        exposure_by_slug={key: round(value, 4) for key, value in sorted(by_slug.items())},
    )


def state_to_dict(state: PortfolioRiskState) -> dict[str, object]:
    return {
        "bankroll": state.bankroll,
        "open_positions": state.open_positions,
        "remaining_position_slots": state.remaining_position_slots,
        "total_exposure": state.total_exposure,
        "total_exposure_pct": state.total_exposure_pct,
        "remaining_total_risk_capacity": state.remaining_total_risk_capacity,
        "unrealized_pnl": state.unrealized_pnl,
        "unrealized_pnl_pct": state.unrealized_pnl_pct,
        "loss_limit_headroom": state.loss_limit_headroom,
        "circuit_breaker_active": state.circuit_breaker_active,
        "circuit_breaker_reasons": state.circuit_breaker_reasons,
        "state_load_error": state.state_load_error,
        "exposure_by_event_type": state.exposure_by_event_type,
        "exposure_by_platform": state.exposure_by_platform,
        "exposure_by_slug": state.exposure_by_slug,
    }


def _load_open_positions(
    db_path: str | None,
    settlements: list[Settlement] | None = None,
) -> tuple[list[dict[str, object]], str | None]:
    if not db_path:
        return [], None
    try:
        records = open_positions(db_path, settlements)
    except Exception as exc:
        return [], exc.__class__.__name__
    return [
        {
            "fill_id": record.fill_id,
            "slug": record.slug,
            "side": record.side,
            "event_type": record.event_type,
            "platform": record.platform,
            "risk_amount": round(record.risk_amount, 4),
            "unrealized_pnl": round(record.unrealized_pnl, 4),
        }
        for record in records
    ], None


def _position_row(position: dict[str, object] | PositionRecord) -> dict[str, object]:
    if isinstance(position, dict):
        return position
    return {
        "fill_id": position.fill_id,
        "slug": position.slug,
        "side": position.side,
        "event_type": position.event_type,
        "platform": position.platform,
        "risk_amount": round(position.risk_amount, 4),
        "unrealized_pnl": round(position.unrealized_pnl, 4),
    }


def _fill_risk_amount(fill: dict[str, object], config: BotConfig) -> float:
    value = fill.get("risk_amount") or fill.get("portfolio_risk_amount")
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    return round(config.shadow_bankroll * config.shadow_position_risk_pct, 4)


from bot.config import BotConfig
from bot.models import ParsedMarket, Signal


def allow_market(parsed: ParsedMarket, config: BotConfig) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    market = parsed.market

    if parsed.days_to_expiry < config.min_days_to_expiry or parsed.days_to_expiry > config.max_days_to_expiry:
        reasons.append("expiry_out_of_range")
    if market.volume < config.min_volume:
        reasons.append("volume_too_low")
    if max(market.spread, market.no_spread) > config.max_spread:
        reasons.append("spread_too_wide")
    if parsed.platform == "unknown":
        reasons.append("unsupported_platform")

    return (len(reasons) == 0, reasons)


from bot.signal_engine import MODEL_PROFILES

def allow_signal(signal: Signal, config: BotConfig) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if signal.net_edge < config.min_net_edge:
        reasons.append("net_edge_too_small")
        
    profile = MODEL_PROFILES.get(signal.profile_name)
    min_confidence = profile.min_confidence if profile else 0.55
    if signal.confidence < min_confidence:
        reasons.append(f"confidence_too_low_for_profile_{signal.profile_name}")
    if signal.max_entry_price <= 0.01:
        reasons.append("invalid_entry_price")
    return (len(reasons) == 0, reasons)
