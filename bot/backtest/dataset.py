from __future__ import annotations

from dataclasses import asdict, dataclass
import sqlite3
from contextlib import closing

from bot.backtest.engine import BacktestStrategyParams
from bot.domain import SnapshotRecord, parse_json_mapping, profile_name_from_snapshot
from bot.positions import load_positions_from_connection
from bot.settlements import Settlement


@dataclass(frozen=True)
class BacktestSample:
    timestamp_utc: str
    slug: str
    market_id: str | None
    event_type: str
    platform: str
    model_profile: str
    preferred_side: str | None
    model_side: str | None
    p_model: float | None
    p_mid: float | None
    net_edge: float | None
    evidence_score: float | None
    preheat_score: float | None
    cadence_score: float | None
    partner_score: float | None
    market_price: float | None
    fill_eligible: bool
    fill_price: float | None
    target_price: float | None
    target_yes_probability: float | None
    target_source: str
    realized_pnl: float | None


def load_backtest_samples(
    db_path: str,
    settlements: list[Settlement] | None = None,
    params: BacktestStrategyParams | None = None,
    target_source: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[BacktestSample]:
    strategy = params or BacktestStrategyParams()
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        samples = load_backtest_samples_from_connection(
            connection,
            settlements,
            params=strategy,
            target_source=target_source,
            start_date=start_date,
            end_date=end_date,
        )
    return samples


def load_backtest_samples_from_connection(
    connection: sqlite3.Connection,
    settlements: list[Settlement] | None = None,
    params: BacktestStrategyParams | None = None,
    target_source: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    positions_by_fill_id: dict[int, object] | None = None,
) -> list[BacktestSample]:
    strategy = params or BacktestStrategyParams()
    if positions_by_fill_id is None:
        positions_by_fill_id = {
            position.fill_id: position for position in load_positions_from_connection(connection, settlements)
        }
    fills = connection.execute(_shadow_fill_select_query(connection)).fetchall()
    samples = [
        sample
        for fill in fills
        if _date_in_range(str(fill["timestamp_utc"]), start_date, end_date)
        if (sample := _sample_from_fill(connection, fill, positions_by_fill_id.get(int(fill["id"])), strategy)) is not None
    ]
    if target_source:
        samples = [sample for sample in samples if sample.target_source == target_source]
    return samples


def samples_to_dicts(samples: list[BacktestSample]) -> list[dict[str, object]]:
    return [asdict(sample) for sample in samples]


def _sample_from_fill(
    connection: sqlite3.Connection,
    fill: sqlite3.Row,
    position,
    strategy: BacktestStrategyParams,
) -> BacktestSample | None:
    raw = parse_json_mapping(fill["raw_json"])
    snapshot_data = _snapshot_for_fill(connection, str(fill["slug"]), fill["snapshot_timestamp_utc"] or raw.get("snapshot_timestamp_utc"))
    if not snapshot_data:
        return None
    snapshot = SnapshotRecord.from_mapping(snapshot_data)
    if not _matches_strategy(snapshot, strategy):
        return None

    side = _optional_side(fill["side"])
    share_quantity = _share_quantity(fill, raw)
    target_price, target_yes_probability, target_source = _target_for_sample(snapshot, position, side)
    fill_price = _float(fill["fill_price"])
    realized_pnl = _scaled_pnl(target_price, fill_price, share_quantity)
    return BacktestSample(
        timestamp_utc=str(fill["timestamp_utc"]),
        slug=str(fill["slug"]),
        market_id=_optional_string(fill["market_id"] or snapshot.market_id),
        event_type=str(snapshot.event_type or "unknown"),
        platform=str(snapshot.platform or "unknown"),
        model_profile=profile_name_from_snapshot(snapshot),
        preferred_side=snapshot.preferred_side,
        model_side=snapshot.model_side,
        p_model=_clip_probability(snapshot.p_model),
        p_mid=_clip_probability(snapshot.p_mid),
        net_edge=snapshot.net_edge,
        evidence_score=snapshot.evidence_score,
        preheat_score=_float(snapshot_data.get("evidence_preheat_score")),
        cadence_score=_float(snapshot_data.get("evidence_cadence_score")),
        partner_score=_float(snapshot_data.get("evidence_partner_score")),
        market_price=_side_mid(snapshot, side),
        fill_eligible=True,
        fill_price=fill_price,
        target_price=target_price,
        target_yes_probability=target_yes_probability,
        target_source=target_source,
        realized_pnl=realized_pnl,
    )


def _matches_strategy(snapshot: SnapshotRecord, strategy: BacktestStrategyParams) -> bool:
    if strategy.model_profile and profile_name_from_snapshot(snapshot) != strategy.model_profile:
        return False
    if strategy.event_type and str(snapshot.event_type or "") != strategy.event_type:
        return False
    if snapshot.net_edge is None or snapshot.net_edge < strategy.min_net_edge:
        return False
    if strategy.max_spread is not None:
        side = snapshot.model_side or snapshot.preferred_side
        spread = _side_spread(snapshot, side)
        if spread is None or spread > strategy.max_spread:
            return False
    return True


def _target_for_sample(
    snapshot: SnapshotRecord,
    position,
    side: str | None,
) -> tuple[float | None, float | None, str]:
    if side is None:
        return None, _clip_probability(snapshot.yes_mid), "snapshot_mid"
    if position is not None and position.status in {"closed", "settled"} and position.current_price is not None:
        return position.current_price, _side_price_to_yes_probability(side, position.current_price), position.close_source or "settlement_file"
    if position is not None and position.current_price is not None:
        return position.current_price, _side_price_to_yes_probability(side, position.current_price), "latest_mark"
    side_mid = _side_mid(snapshot, side)
    return side_mid, _side_price_to_yes_probability(side, side_mid), "snapshot_mid"


def _snapshot_for_fill(connection: sqlite3.Connection, slug: str, snapshot_timestamp: object) -> dict[str, object]:
    if isinstance(snapshot_timestamp, str) and snapshot_timestamp:
        row = connection.execute(
            """
            SELECT raw_json FROM watchlist_snapshots
            WHERE slug = ? AND timestamp_utc = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (slug, snapshot_timestamp),
        ).fetchone()
        if row is not None:
            return parse_json_mapping(row["raw_json"])
    row = connection.execute(
        """
        SELECT raw_json FROM watchlist_snapshots
        WHERE slug = ?
        ORDER BY timestamp_utc DESC, id DESC
        LIMIT 1
        """,
        (slug,),
    ).fetchone()
    return parse_json_mapping(row["raw_json"]) if row is not None else {}


def _shadow_fill_select_query(connection: sqlite3.Connection) -> str:
    existing = {str(row[1]) for row in connection.execute("PRAGMA table_info(shadow_fills)").fetchall()}
    columns = [
        "id",
        "timestamp_utc",
        "slug",
        "market_id",
        "side",
        "snapshot_timestamp_utc",
        "share_quantity",
        "fill_price",
        "raw_json",
    ]
    expressions = [name if name in existing else f"NULL AS {name}" for name in columns]
    return "SELECT " + ", ".join(expressions) + " FROM shadow_fills ORDER BY timestamp_utc, id"


def _side_price_to_yes_probability(side: str, side_price: float | None) -> float | None:
    if side_price is None:
        return None
    if side == "BUY_YES":
        return _clip_probability(side_price)
    if side == "BUY_NO":
        return _clip_probability(1.0 - side_price)
    return None


def _side_mid(snapshot: dict[str, object], side: str | None) -> float | None:
    return snapshot.side_mid(side)


def _side_spread(snapshot: SnapshotRecord, side: str | None) -> float | None:
    return snapshot.side_spread(side)


def _date_in_range(timestamp: str, start_date: str | None, end_date: str | None) -> bool:
    day = timestamp[:10]
    if start_date and day < start_date:
        return False
    if end_date and day > end_date:
        return False
    return True


def _optional_side(value: object) -> str | None:
    if value in {"BUY_YES", "BUY_NO"}:
        return str(value)
    return None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _share_quantity(fill: sqlite3.Row, raw: dict[str, object]) -> float | None:
    quantity = _float(fill["share_quantity"])
    if quantity is not None:
        return quantity
    return _float(raw.get("share_quantity"))


def _scaled_pnl(
    target_price: float | None,
    fill_price: float | None,
    share_quantity: float | None,
) -> float | None:
    if target_price is None or fill_price is None:
        return None
    price_delta = target_price - fill_price
    if share_quantity is not None:
        return round(price_delta * share_quantity, 4)
    return round(price_delta, 4)


def _clip_probability(value: float | None) -> float | None:
    if value is None:
        return None
    return min(0.99, max(0.01, float(value)))
