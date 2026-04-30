from __future__ import annotations

from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest

from bot.backtest.dataset import load_backtest_samples
from bot.backtest.replay import replay_shadow_pnl
from bot.reporting import build_dashboard_report
from bot.storage import WatchlistStore


class StorageTests(unittest.TestCase):
    def test_stores_evidence_runs_and_shadow_marks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "watchlist.sqlite")
            store = WatchlistStore(db_path)
            snapshot = {
                "timestamp_utc": "2026-04-27T00:00:00+00:00",
                "slug": "market",
                "market_id": "1",
                "subject": "Subject",
                "platform": "streaming",
                "event_type": "content_release",
                "preferred_side": "BUY_NO",
                "preferred_price": 0.45,
                "in_target_band": True,
                "yes_bid": 0.54,
                "yes_ask": 0.55,
                "yes_mid": 0.545,
                "no_bid": 0.45,
                "no_ask": 0.46,
                "no_mid": 0.455,
                "yes_spread": 0.01,
                "no_spread": 0.01,
                "book_status": "complete",
                "yes_ask_source": "book",
                "no_ask_source": "book",
                "evidence_score": 0.1,
                "evidence_confidence": 0.7,
                "evidence_mode": "source",
                "evidence_source_url": "https://example.com/feed.xml",
                "evidence_source_type": "rss",
                "evidence_recent_entries_30d": 3,
                "evidence_keyword_hits_30d": 1,
                "evidence_latest_entry_age_days": 2.0,
                "evidence_preheat_score": 0.4,
                "evidence_cadence_score": 0.3,
                "evidence_partner_score": 0.2,
                "evidence_source_reliability": 0.7,
                "model_side": "BUY_NO",
                "p_model": 0.48,
                "p_mid": 0.545,
                "edge": 0.065,
                "net_edge": 0.015,
                "signal_ok": True,
                "market_ok": True,
            }
            fill = {
                "timestamp_utc": "2026-04-27T00:01:00+00:00",
                "slug": "market",
                "label": "Market",
                "market_id": "1",
                "side": "BUY_NO",
                "fill_price": 0.46,
                "max_entry_price": 0.47,
                "net_edge": 0.015,
                "reason": "ask_at_or_below_max_entry",
            }

            store.insert_snapshots([snapshot])
            store.insert_evidence_runs([snapshot])
            store.insert_shadow_fills([fill])
            self.assertEqual(store.filter_new_shadow_fills([fill]), [])
            marks = store.insert_shadow_marks([snapshot])

            self.assertEqual(marks, 1)
            with closing(sqlite3.connect(db_path)) as connection:
                evidence_count = connection.execute("SELECT COUNT(*) FROM evidence_runs").fetchone()[0]
                evidence_components = connection.execute(
                    "SELECT preheat_score, cadence_score, partner_score, source_reliability FROM evidence_runs"
                ).fetchone()
                snapshot_meta = connection.execute(
                    "SELECT platform, event_type, book_status, yes_ask_source, no_ask_source, evidence_mode FROM watchlist_snapshots"
                ).fetchone()
                mark = connection.execute(
                    "SELECT side, fill_price, mark_price, unrealized_pnl FROM shadow_marks"
                ).fetchone()

            self.assertEqual(evidence_count, 1)
            self.assertEqual(evidence_components, (0.4, 0.3, 0.2, 0.7))
            self.assertEqual(snapshot_meta, ("streaming", "content_release", "complete", "book", "book", "source"))
            self.assertEqual(mark, ("BUY_NO", 0.46, 0.455, -0.005))

    def test_reads_legacy_schema_rows_via_raw_json_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "legacy.sqlite")
            with closing(sqlite3.connect(db_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE watchlist_snapshots (
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
                        evidence_score REAL,
                        evidence_confidence REAL,
                        model_side TEXT,
                        p_model REAL,
                        p_mid REAL,
                        edge REAL,
                        net_edge REAL,
                        signal_ok INTEGER,
                        market_ok INTEGER,
                        raw_json TEXT NOT NULL
                    );

                    CREATE TABLE shadow_fills (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp_utc TEXT NOT NULL,
                        slug TEXT NOT NULL,
                        label TEXT,
                        market_id TEXT,
                        side TEXT NOT NULL,
                        fill_price REAL NOT NULL,
                        max_entry_price REAL NOT NULL,
                        net_edge REAL,
                        reason TEXT NOT NULL,
                        raw_json TEXT NOT NULL
                    );

                    CREATE TABLE watchlist_alerts (
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

                    CREATE TABLE shadow_marks (
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
                    """
                )
                snapshot = _legacy_snapshot()
                fill = _legacy_fill()
                connection.execute(
                    """
                    INSERT INTO watchlist_snapshots (
                        timestamp_utc, slug, label, market_id, title, preferred_side,
                        preferred_price, in_target_band, yes_bid, yes_ask, yes_mid,
                        no_bid, no_ask, no_mid, evidence_score, evidence_confidence,
                        model_side, p_model, p_mid, edge, net_edge, signal_ok, market_ok, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot["timestamp_utc"],
                        snapshot["slug"],
                        snapshot["label"],
                        snapshot["market_id"],
                        snapshot["title"],
                        snapshot["preferred_side"],
                        snapshot["preferred_price"],
                        1,
                        snapshot["yes_bid"],
                        snapshot["yes_ask"],
                        snapshot["yes_mid"],
                        snapshot["no_bid"],
                        snapshot["no_ask"],
                        snapshot["no_mid"],
                        snapshot["evidence_score"],
                        snapshot["evidence_confidence"],
                        snapshot["model_side"],
                        snapshot["p_model"],
                        snapshot["p_mid"],
                        snapshot["edge"],
                        snapshot["net_edge"],
                        1,
                        1,
                        json_dumps(snapshot),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO shadow_fills (
                        timestamp_utc, slug, label, market_id, side, fill_price,
                        max_entry_price, net_edge, reason, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fill["timestamp_utc"],
                        fill["slug"],
                        fill["label"],
                        fill["market_id"],
                        fill["side"],
                        fill["fill_price"],
                        fill["max_entry_price"],
                        fill["net_edge"],
                        fill["reason"],
                        json_dumps(fill),
                    ),
                )
                connection.commit()

            report = build_dashboard_report(db_path, limit=5)
            samples = load_backtest_samples(db_path)
            replay = replay_shadow_pnl(db_path)

            self.assertEqual(report["counts"]["shadow_fills"], 1)
            self.assertEqual(report["latest_markets"][0]["event_type"], "content_release")
            self.assertEqual(report["latest_markets"][0]["platform"], "streaming")
            self.assertEqual(report["health"]["book_complete_rate"], 1.0)
            self.assertEqual(len(samples), 1)
            self.assertEqual(samples[0].event_type, "content_release")
            self.assertEqual(samples[0].platform, "streaming")
            self.assertEqual(samples[0].target_source, "snapshot_mid")
            self.assertEqual(replay["records"][0]["event_type"], "content_release")
            self.assertEqual(replay["records"][0]["platform"], "streaming")

    def test_store_initialization_adds_missing_columns_to_legacy_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "legacy.sqlite")
            with closing(sqlite3.connect(db_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE watchlist_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp_utc TEXT NOT NULL,
                        slug TEXT NOT NULL,
                        raw_json TEXT NOT NULL
                    );
                    CREATE TABLE shadow_fills (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp_utc TEXT NOT NULL,
                        slug TEXT NOT NULL,
                        side TEXT NOT NULL,
                        fill_price REAL NOT NULL,
                        max_entry_price REAL NOT NULL,
                        reason TEXT NOT NULL,
                        raw_json TEXT NOT NULL
                    );
                    CREATE TABLE evidence_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp_utc TEXT NOT NULL,
                        slug TEXT NOT NULL,
                        raw_json TEXT NOT NULL
                    );
                    """
                )
                connection.commit()

            WatchlistStore(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                snapshot_columns = {row[1] for row in connection.execute("PRAGMA table_info(watchlist_snapshots)").fetchall()}
                fill_columns = {row[1] for row in connection.execute("PRAGMA table_info(shadow_fills)").fetchall()}
                evidence_columns = {row[1] for row in connection.execute("PRAGMA table_info(evidence_runs)").fetchall()}

            self.assertIn("book_status", snapshot_columns)
            self.assertIn("event_type", snapshot_columns)
            self.assertIn("close_source", fill_columns)
            self.assertIn("snapshot_timestamp_utc", fill_columns)
            self.assertIn("matched_items_json", evidence_columns)
            self.assertIn("source_reliability", evidence_columns)

    def test_shadow_fill_and_mark_inserts_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "watchlist.sqlite")
            store = WatchlistStore(db_path)
            snapshot = _legacy_snapshot()
            fill = _legacy_fill()

            store.insert_snapshots([snapshot])
            store.insert_shadow_fills([fill, dict(fill)])
            first_marks = store.insert_shadow_marks([snapshot])
            second_marks = store.insert_shadow_marks([snapshot])

            with closing(sqlite3.connect(db_path)) as connection:
                fill_count = connection.execute("SELECT COUNT(*) FROM shadow_fills").fetchone()[0]
                mark_count = connection.execute("SELECT COUNT(*) FROM shadow_marks").fetchone()[0]

            self.assertEqual(fill_count, 1)
            self.assertEqual(first_marks, 1)
            self.assertEqual(second_marks, 0)
            self.assertEqual(mark_count, 1)

    def test_closed_shadow_fill_does_not_block_reentry_filter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "watchlist.sqlite")
            store = WatchlistStore(db_path)
            fill = {**_legacy_fill(), "position_status": "closed"}

            store.insert_shadow_fills([fill])
            new_fills = store.filter_new_shadow_fills([_legacy_fill()])

        self.assertEqual(len(new_fills), 1)

    def test_store_initialization_skips_unique_indexes_when_legacy_duplicates_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "legacy.sqlite")
            with closing(sqlite3.connect(db_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE shadow_fills (
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
                    CREATE TABLE shadow_marks (
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
                    """
                )
                fill = _legacy_fill()
                row = (
                    fill["timestamp_utc"],
                    fill["slug"],
                    fill["label"],
                    fill["market_id"],
                    fill["event_type"],
                    fill["platform"],
                    fill["side"],
                    fill["fill_price"],
                    fill["risk_amount"],
                    fill["share_quantity"],
                    fill["max_entry_price"],
                    fill["net_edge"],
                    fill["reason"],
                    fill["snapshot_timestamp_utc"],
                    "open",
                    None,
                    None,
                    None,
                    json_dumps(fill),
                )
                connection.execute(
                    """
                    INSERT INTO shadow_fills (
                        timestamp_utc, slug, label, market_id, event_type, platform, side,
                        fill_price, risk_amount, share_quantity, max_entry_price, net_edge, reason,
                        snapshot_timestamp_utc, position_status, closed_at_utc, close_source, close_price, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
                connection.execute(
                    """
                    INSERT INTO shadow_fills (
                        timestamp_utc, slug, label, market_id, event_type, platform, side,
                        fill_price, risk_amount, share_quantity, max_entry_price, net_edge, reason,
                        snapshot_timestamp_utc, position_status, closed_at_utc, close_source, close_price, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
                connection.execute(
                    """
                    INSERT INTO shadow_marks (
                        fill_id, timestamp_utc, slug, market_id, side, fill_price,
                        mark_price, unrealized_pnl, unrealized_pnl_pct, snapshot_timestamp_utc, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (1, snapshot_timestamp := fill["snapshot_timestamp_utc"], fill["slug"], fill["market_id"], fill["side"], fill["fill_price"], 0.455, -0.005, -0.01087, snapshot_timestamp, "{}"),
                )
                connection.execute(
                    """
                    INSERT INTO shadow_marks (
                        fill_id, timestamp_utc, slug, market_id, side, fill_price,
                        mark_price, unrealized_pnl, unrealized_pnl_pct, snapshot_timestamp_utc, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (1, snapshot_timestamp, fill["slug"], fill["market_id"], fill["side"], fill["fill_price"], 0.455, -0.005, -0.01087, snapshot_timestamp, "{}"),
                )
                connection.commit()

            WatchlistStore(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                indexes = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list(shadow_fills)").fetchall()
                }
                mark_indexes = {
                    row[1]
                    for row in connection.execute("PRAGMA index_list(shadow_marks)").fetchall()
                }

            self.assertNotIn("uq_shadow_fills_open_slug_side", indexes)
            self.assertNotIn("uq_shadow_marks_fill_snapshot", mark_indexes)


def _legacy_snapshot() -> dict[str, object]:
    return {
        "timestamp_utc": "2026-04-27T00:00:00+00:00",
        "slug": "market",
        "label": "Market",
        "market_id": "1",
        "title": "Will Artist release a new album?",
        "subject": "Artist",
        "platform": "streaming",
        "event_type": "content_release",
        "preferred_side": "BUY_NO",
        "preferred_price": 0.45,
        "in_target_band": True,
        "yes_bid": 0.54,
        "yes_ask": 0.55,
        "yes_mid": 0.545,
        "no_bid": 0.45,
        "no_ask": 0.46,
        "no_mid": 0.455,
        "book_status": "complete",
        "yes_ask_source": "book",
        "no_ask_source": "book",
        "evidence_score": 0.1,
        "evidence_confidence": 0.7,
        "evidence_mode": "source",
        "model_side": "BUY_NO",
        "p_model": 0.48,
        "p_mid": 0.545,
        "edge": 0.065,
        "net_edge": 0.015,
        "signal_ok": True,
        "market_ok": True,
        "signal_reasons_detail": ["model_profile=music_release"],
    }


def _legacy_fill() -> dict[str, object]:
    return {
        "timestamp_utc": "2026-04-27T00:01:00+00:00",
        "slug": "market",
        "label": "Market",
        "market_id": "1",
        "event_type": "content_release",
        "platform": "streaming",
        "side": "BUY_NO",
        "fill_price": 0.46,
        "risk_amount": 20.0,
        "share_quantity": 43.4783,
        "max_entry_price": 0.47,
        "net_edge": 0.015,
        "reason": "ask_at_or_below_max_entry",
        "position_status": "open",
        "snapshot_timestamp_utc": "2026-04-27T00:00:00+00:00",
    }


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=True)


if __name__ == "__main__":
    unittest.main()
