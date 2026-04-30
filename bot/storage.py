from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from bot.settlements import Settlement, settlement_close_price


class WatchlistStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def insert_snapshots(self, snapshots: list[dict[str, object]]) -> None:
        if not snapshots:
            return
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT INTO watchlist_snapshots (
                    timestamp_utc, slug, label, market_id, title, preferred_side,
                    preferred_price, in_target_band, yes_bid, yes_ask, yes_mid,
                    no_bid, no_ask, no_mid, subject, platform, event_type,
                    yes_spread, no_spread, book_status, yes_ask_source, no_ask_source,
                    evidence_score, evidence_confidence, evidence_mode,
                    model_side, p_model, p_mid, edge, net_edge, signal_ok,
                    market_ok, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_snapshot_row(snapshot) for snapshot in snapshots],
            )
            connection.commit()

    def insert_evidence_runs(self, snapshots: list[dict[str, object]]) -> None:
        rows = [_evidence_row(snapshot) for snapshot in snapshots if snapshot.get("evidence_score") is not None]
        if not rows:
            return
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT INTO evidence_runs (
                    timestamp_utc, slug, market_id, subject, platform, event_type,
                    mode, source_url, source_type, score, confidence,
                    recent_entries_30d, keyword_hits_30d, latest_entry_age_days,
                    preheat_score, cadence_score, partner_score, source_reliability,
                    matched_items_json, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.commit()

    def insert_alerts(self, alerts: list[dict[str, object]]) -> None:
        if not alerts:
            return
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT INTO watchlist_alerts (
                    timestamp_utc, slug, label, market_id, title,
                    alert_reasons, previous_timestamp_utc, current_timestamp_utc, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_alert_row(alert) for alert in alerts],
            )
            connection.commit()

    def insert_shadow_fills(self, fills: list[dict[str, object]]) -> None:
        if not fills:
            return
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO shadow_fills (
                    timestamp_utc, slug, label, market_id, event_type, platform, side,
                    fill_price, risk_amount, share_quantity, max_entry_price, net_edge, reason,
                    snapshot_timestamp_utc,
                    position_status, closed_at_utc, close_source, close_price, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_shadow_fill_row(fill) for fill in fills],
            )
            connection.commit()

    def apply_settlements(self, settlements: list[Settlement]) -> int:
        if not settlements:
            return 0
        updated = 0
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, slug, side
                FROM shadow_fills
                WHERE COALESCE(position_status, 'open') = 'open'
                ORDER BY id
                """
            ).fetchall()
            for fill_id, slug, side in rows:
                for settlement in settlements:
                    if settlement.slug != slug:
                        continue
                    if settlement.side is not None and settlement.side != side:
                        continue
                    close_price = settlement_close_price(settlement, str(side))
                    connection.execute(
                        """
                        UPDATE shadow_fills
                        SET position_status = ?, closed_at_utc = ?, close_source = ?, close_price = ?
                        WHERE id = ?
                        """,
                        (
                            settlement.status,
                            settlement.timestamp_utc,
                            "settlement_file",
                            close_price,
                            fill_id,
                        ),
                    )
                    updated += 1
                    break
            connection.commit()
        return updated

    def filter_new_shadow_fills(self, fills: list[dict[str, object]]) -> list[dict[str, object]]:
        if not fills:
            return []
        new_fills: list[dict[str, object]] = []
        with closing(self._connect()) as connection:
            for fill in fills:
                slug = fill.get("slug")
                side = fill.get("side")
                exists = connection.execute(
                    """
                    SELECT 1
                    FROM shadow_fills
                    WHERE slug = ? AND side = ? AND COALESCE(position_status, 'open') = 'open'
                    LIMIT 1
                    """,
                    (slug, side),
                ).fetchone()
                if exists is None:
                    new_fills.append(fill)
        return new_fills

    def insert_shadow_marks(self, snapshots: list[dict[str, object]]) -> int:
        if not snapshots:
            return 0
        inserted = 0
        with closing(self._connect()) as connection:
            for snapshot in snapshots:
                slug = snapshot.get("slug")
                if not isinstance(slug, str):
                    continue
                fills = connection.execute(
                    "SELECT id, side, fill_price FROM shadow_fills WHERE slug = ?",
                    (slug,),
                ).fetchall()
                for fill_id, side, fill_price in fills:
                    mark_price = _mark_price(snapshot, side)
                    if mark_price is None or fill_price is None:
                        continue
                    pnl = round(mark_price - float(fill_price), 4)
                    pnl_pct = round(pnl / float(fill_price), 6) if float(fill_price) > 0 else None
                    mark = {
                        "timestamp_utc": snapshot.get("timestamp_utc"),
                        "slug": slug,
                        "market_id": snapshot.get("market_id"),
                        "side": side,
                        "fill_price": fill_price,
                        "mark_price": mark_price,
                        "unrealized_pnl": pnl,
                        "unrealized_pnl_pct": pnl_pct,
                        "snapshot_timestamp_utc": snapshot.get("timestamp_utc"),
                    }
                    cursor = connection.execute(
                        """
                        INSERT OR IGNORE INTO shadow_marks (
                            fill_id, timestamp_utc, slug, market_id, side, fill_price,
                            mark_price, unrealized_pnl, unrealized_pnl_pct,
                            snapshot_timestamp_utc, raw_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fill_id,
                            mark["timestamp_utc"],
                            mark["slug"],
                            mark["market_id"],
                            mark["side"],
                            mark["fill_price"],
                            mark["mark_price"],
                            mark["unrealized_pnl"],
                            mark["unrealized_pnl_pct"],
                            mark["snapshot_timestamp_utc"],
                            json.dumps(mark, ensure_ascii=True),
                        ),
                    )
                    inserted += cursor.rowcount
            connection.commit()
        return inserted

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS watchlist_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    label TEXT,
                    market_id TEXT,
                    title TEXT,
                    preferred_side TEXT,
                    preferred_price REAL,
                    in_target_band INTEGER,
                    yes_bid REAL,
                    yes_ask REAL,
                    yes_mid REAL,
                    no_bid REAL,
                    no_ask REAL,
                    no_mid REAL,
                    subject TEXT,
                    platform TEXT,
                    event_type TEXT,
                    yes_spread REAL,
                    no_spread REAL,
                    book_status TEXT,
                    yes_ask_source TEXT,
                    no_ask_source TEXT,
                    evidence_score REAL,
                    evidence_confidence REAL,
                    evidence_mode TEXT,
                    model_side TEXT,
                    p_model REAL,
                    p_mid REAL,
                    edge REAL,
                    net_edge REAL,
                    signal_ok INTEGER,
                    market_ok INTEGER,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_watchlist_snapshots_slug_time
                ON watchlist_snapshots(slug, timestamp_utc);

                CREATE TABLE IF NOT EXISTS watchlist_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    label TEXT,
                    market_id TEXT,
                    title TEXT,
                    alert_reasons TEXT NOT NULL,
                    previous_timestamp_utc TEXT,
                    current_timestamp_utc TEXT,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_slug_time
                ON watchlist_alerts(slug, timestamp_utc);

                CREATE TABLE IF NOT EXISTS shadow_fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    label TEXT,
                    market_id TEXT,
                    event_type TEXT,
                    platform TEXT,
                    side TEXT NOT NULL,
                    fill_price REAL NOT NULL,
                    risk_amount REAL,
                    share_quantity REAL,
                    max_entry_price REAL NOT NULL,
                    net_edge REAL,
                    reason TEXT NOT NULL,
                    snapshot_timestamp_utc TEXT,
                    position_status TEXT,
                    closed_at_utc TEXT,
                    close_source TEXT,
                    close_price REAL,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_shadow_fills_slug_time
                ON shadow_fills(slug, timestamp_utc);

                CREATE TABLE IF NOT EXISTS evidence_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    market_id TEXT,
                    subject TEXT,
                    platform TEXT,
                    event_type TEXT,
                    mode TEXT,
                    source_url TEXT,
                    source_type TEXT,
                    score REAL,
                    confidence REAL,
                    recent_entries_30d INTEGER,
                    keyword_hits_30d INTEGER,
                    latest_entry_age_days REAL,
                    preheat_score REAL,
                    cadence_score REAL,
                    partner_score REAL,
                    source_reliability REAL,
                    matched_items_json TEXT,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_runs_slug_time
                ON evidence_runs(slug, timestamp_utc);

                CREATE TABLE IF NOT EXISTS shadow_marks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fill_id INTEGER NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    market_id TEXT,
                    side TEXT NOT NULL,
                    fill_price REAL NOT NULL,
                    mark_price REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    unrealized_pnl_pct REAL,
                    snapshot_timestamp_utc TEXT,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_shadow_marks_fill_time
                ON shadow_marks(fill_id, timestamp_utc);

                """
            )
            self._ensure_columns(
                connection,
                "watchlist_snapshots",
                {
                    "subject": "TEXT",
                    "platform": "TEXT",
                    "event_type": "TEXT",
                    "yes_spread": "REAL",
                    "no_spread": "REAL",
                    "book_status": "TEXT",
                    "yes_ask_source": "TEXT",
                    "no_ask_source": "TEXT",
                    "evidence_mode": "TEXT",
                },
            )
            self._ensure_columns(
                connection,
                "evidence_runs",
                {
                    "preheat_score": "REAL",
                    "cadence_score": "REAL",
                    "partner_score": "REAL",
                    "source_reliability": "REAL",
                    "matched_items_json": "TEXT",
                },
            )
            self._ensure_columns(
                connection,
                "shadow_fills",
                {
                    "event_type": "TEXT",
                    "platform": "TEXT",
                    "risk_amount": "REAL",
                    "share_quantity": "REAL",
                    "snapshot_timestamp_utc": "TEXT",
                    "position_status": "TEXT",
                    "closed_at_utc": "TEXT",
                    "close_source": "TEXT",
                    "close_price": "REAL",
                },
            )
            self._create_unique_index_if_possible(
                connection,
                "uq_shadow_fills_open_slug_side",
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_shadow_fills_open_slug_side
                ON shadow_fills(slug, side)
                WHERE position_status = 'open' OR position_status IS NULL
                """,
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_shadow_fills_open_positions
                ON shadow_fills(position_status, slug, side, timestamp_utc)
                """
            )
            self._create_unique_index_if_possible(
                connection,
                "uq_shadow_marks_fill_snapshot",
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_shadow_marks_fill_snapshot
                ON shadow_marks(fill_id, snapshot_timestamp_utc)
                WHERE snapshot_timestamp_utc IS NOT NULL
                """,
            )
            connection.commit()

    def _ensure_columns(self, connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def _create_unique_index_if_possible(
        self,
        connection: sqlite3.Connection,
        index_name: str,
        statement: str,
    ) -> None:
        try:
            connection.execute(statement)
        except sqlite3.IntegrityError:
            connection.execute(f"DROP INDEX IF EXISTS {index_name}")


def _snapshot_row(snapshot: dict[str, object]) -> tuple[Any, ...]:
    return (
        snapshot.get("timestamp_utc"),
        snapshot.get("slug"),
        snapshot.get("label"),
        snapshot.get("market_id"),
        snapshot.get("title"),
        snapshot.get("preferred_side"),
        _float_or_none(snapshot.get("preferred_price")),
        _bool_int(snapshot.get("in_target_band")),
        _float_or_none(snapshot.get("yes_bid")),
        _float_or_none(snapshot.get("yes_ask")),
        _float_or_none(snapshot.get("yes_mid")),
        _float_or_none(snapshot.get("no_bid")),
        _float_or_none(snapshot.get("no_ask")),
        _float_or_none(snapshot.get("no_mid")),
        snapshot.get("subject"),
        snapshot.get("platform"),
        snapshot.get("event_type"),
        _float_or_none(snapshot.get("yes_spread")),
        _float_or_none(snapshot.get("no_spread")),
        snapshot.get("book_status"),
        snapshot.get("yes_ask_source"),
        snapshot.get("no_ask_source"),
        _float_or_none(snapshot.get("evidence_score")),
        _float_or_none(snapshot.get("evidence_confidence")),
        snapshot.get("evidence_mode"),
        snapshot.get("model_side"),
        _float_or_none(snapshot.get("p_model")),
        _float_or_none(snapshot.get("p_mid")),
        _float_or_none(snapshot.get("edge")),
        _float_or_none(snapshot.get("net_edge")),
        _bool_int(snapshot.get("signal_ok")),
        _bool_int(snapshot.get("market_ok")),
        json.dumps(snapshot, ensure_ascii=True),
    )


def _alert_row(alert: dict[str, object]) -> tuple[Any, ...]:
    return (
        alert.get("timestamp_utc"),
        alert.get("slug"),
        alert.get("label"),
        alert.get("market_id"),
        alert.get("title"),
        ",".join(str(reason) for reason in alert.get("alert_reasons", [])),
        alert.get("previous_timestamp_utc"),
        alert.get("current_timestamp_utc"),
        json.dumps(alert, ensure_ascii=True),
    )


def _evidence_row(snapshot: dict[str, object]) -> tuple[Any, ...]:
    return (
        snapshot.get("timestamp_utc"),
        snapshot.get("slug"),
        snapshot.get("market_id"),
        snapshot.get("subject"),
        snapshot.get("platform"),
        snapshot.get("event_type"),
        snapshot.get("evidence_mode"),
        snapshot.get("evidence_source_url"),
        snapshot.get("evidence_source_type"),
        _float_or_none(snapshot.get("evidence_score")),
        _float_or_none(snapshot.get("evidence_confidence")),
        _int_or_none(snapshot.get("evidence_recent_entries_30d")),
        _int_or_none(snapshot.get("evidence_keyword_hits_30d")),
        _float_or_none(snapshot.get("evidence_latest_entry_age_days")),
        _float_or_none(snapshot.get("evidence_preheat_score")),
        _float_or_none(snapshot.get("evidence_cadence_score")),
        _float_or_none(snapshot.get("evidence_partner_score")),
        _float_or_none(snapshot.get("evidence_source_reliability")),
        json.dumps(snapshot.get("evidence_matched_items", []), ensure_ascii=True),
        json.dumps(
            {
                "reasons": snapshot.get("evidence_reasons", []),
                "score": snapshot.get("evidence_score"),
                "confidence": snapshot.get("evidence_confidence"),
                "preheat_score": snapshot.get("evidence_preheat_score"),
                "cadence_score": snapshot.get("evidence_cadence_score"),
                "partner_score": snapshot.get("evidence_partner_score"),
                "source_reliability": snapshot.get("evidence_source_reliability"),
                "matched_items": snapshot.get("evidence_matched_items", []),
            },
            ensure_ascii=True,
        ),
    )


def _shadow_fill_row(fill: dict[str, object]) -> tuple[Any, ...]:
    return (
        fill.get("timestamp_utc"),
        fill.get("slug"),
        fill.get("label"),
        fill.get("market_id"),
        fill.get("event_type"),
        fill.get("platform"),
        fill.get("side"),
        _float_or_none(fill.get("fill_price")),
        _float_or_none(fill.get("risk_amount") or fill.get("portfolio_risk_amount")),
        _float_or_none(fill.get("share_quantity")),
        _float_or_none(fill.get("max_entry_price")),
        _float_or_none(fill.get("net_edge")),
        fill.get("reason"),
        fill.get("snapshot_timestamp_utc"),
        fill.get("position_status") or "open",
        fill.get("closed_at_utc"),
        fill.get("close_source"),
        _float_or_none(fill.get("close_price")),
        json.dumps(fill, ensure_ascii=True),
    )


def _bool_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _mark_price(snapshot: dict[str, object], side: str) -> float | None:
    if side == "BUY_YES":
        return _float_or_none(snapshot.get("yes_mid"))
    if side == "BUY_NO":
        return _float_or_none(snapshot.get("no_mid"))
    return None
