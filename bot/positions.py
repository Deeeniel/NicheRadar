from __future__ import annotations

import sqlite3
from contextlib import closing

from bot.domain import PositionRecord, parse_json_mapping
from bot.settlements import Settlement, settlement_close_price, settlement_index


def load_positions(
    db_path: str,
    settlements: list[Settlement] | None = None,
) -> list[PositionRecord]:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        return load_positions_from_connection(connection, settlements)


def load_positions_from_connection(
    connection: sqlite3.Connection,
    settlements: list[Settlement] | None = None,
) -> list[PositionRecord]:
    indexed = settlement_index(settlements or [])
    fills = connection.execute(_shadow_fill_select_query(connection)).fetchall()
    return [_position_from_fill(connection, fill, indexed) for fill in fills]


def open_positions(db_path: str, settlements: list[Settlement] | None = None) -> list[PositionRecord]:
    return [position for position in load_positions(db_path, settlements) if position.status == "open"]


def _position_from_fill(
    connection: sqlite3.Connection,
    fill: sqlite3.Row,
    indexed: dict[tuple[str, str | None], Settlement],
) -> PositionRecord:
    raw = parse_json_mapping(fill["raw_json"])
    slug = str(fill["slug"])
    side = str(fill["side"])
    settlement = indexed.get((slug, side)) or indexed.get((slug, None))
    snapshot = _snapshot_for_fill(connection, slug, fill["snapshot_timestamp_utc"] or raw.get("snapshot_timestamp_utc"))
    latest_mark = connection.execute(
        """
        SELECT timestamp_utc, mark_price, unrealized_pnl, unrealized_pnl_pct
        FROM shadow_marks
        WHERE fill_id = ?
        ORDER BY timestamp_utc DESC, id DESC
        LIMIT 1
        """,
        (fill["id"],),
    ).fetchone()

    persisted_status = str(fill["position_status"] or raw.get("position_status") or "open")
    persisted_close_price = _float_or_none(fill["close_price"])
    persisted_closed_at = _string_or_none(fill["closed_at_utc"])
    persisted_close_source = _string_or_none(fill["close_source"])
    share_quantity = _float_or_none(fill["share_quantity"])
    if share_quantity is None:
        share_quantity = _float_or_none(raw.get("share_quantity"))
    current_price = None
    realized_pnl = None
    close_source = persisted_close_source
    closed_at_utc = persisted_closed_at
    settlement_note = None

    if settlement is not None:
        close_price = settlement_close_price(settlement, side)
        current_price = close_price
        realized_pnl = _scaled_pnl(close_price, float(fill["fill_price"]), share_quantity)
        close_source = "settlement_file"
        closed_at_utc = settlement.timestamp_utc
        settlement_note = settlement.note
        status = settlement.status
    elif persisted_status in {"closed", "settled"}:
        current_price = persisted_close_price
        realized_pnl = _scaled_pnl(persisted_close_price, float(fill["fill_price"]), share_quantity)
        status = persisted_status
    else:
        status = "open"
        if latest_mark is not None:
            current_price = _float_or_none(latest_mark["mark_price"])

    price_pnl = None
    unrealized_pnl = 0.0
    unrealized_pnl_pct = None
    if status == "open" and latest_mark is not None:
        price_pnl = _float_or_none(latest_mark["unrealized_pnl"])
        unrealized_pnl_pct = _float_or_none(latest_mark["unrealized_pnl_pct"])
        if price_pnl is not None:
            if share_quantity is not None:
                unrealized_pnl = round(price_pnl * share_quantity, 4)
            else:
                unrealized_pnl = round(price_pnl, 4)

    risk_amount = _float_or_none(fill["risk_amount"])
    if risk_amount is None:
        risk_amount = _float_or_none(raw.get("risk_amount") or raw.get("portfolio_risk_amount"))
    if risk_amount is None and share_quantity is not None:
        risk_amount = round(share_quantity * float(fill["fill_price"]), 4)

    return PositionRecord(
        fill_id=int(fill["id"]),
        slug=slug,
        side=side,
        event_type=str(fill["event_type"] or raw.get("event_type") or snapshot.get("event_type") or "unknown"),
        platform=str(fill["platform"] or raw.get("platform") or snapshot.get("platform") or "unknown"),
        opened_at_utc=str(fill["timestamp_utc"]),
        fill_price=float(fill["fill_price"]),
        risk_amount=risk_amount or 0.0,
        share_quantity=share_quantity,
        max_entry_price=_float_or_none(fill["max_entry_price"]),
        net_edge=_float_or_none(fill["net_edge"]),
        status=status,
        current_price=current_price,
        price_pnl=price_pnl,
        unrealized_pnl=round(unrealized_pnl, 4),
        unrealized_pnl_pct=unrealized_pnl_pct,
        realized_pnl=realized_pnl,
        closed_at_utc=closed_at_utc,
        close_source=close_source,
        settlement_note=settlement_note,
    )


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
        "label",
        "market_id",
        "event_type",
        "platform",
        "side",
        "fill_price",
        "risk_amount",
        "share_quantity",
        "max_entry_price",
        "net_edge",
        "position_status",
        "closed_at_utc",
        "close_source",
        "close_price",
        "snapshot_timestamp_utc",
        "raw_json",
    ]
    expressions = [name if name in existing else f"NULL AS {name}" for name in columns]
    return "SELECT " + ", ".join(expressions) + " FROM shadow_fills ORDER BY timestamp_utc, id"


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _scaled_pnl(
    close_price: float | None,
    fill_price: float,
    share_quantity: float | None,
) -> float | None:
    if close_price is None:
        return None
    price_delta = close_price - fill_price
    if share_quantity is not None:
        return round(price_delta * share_quantity, 4)
    return round(price_delta, 4)
