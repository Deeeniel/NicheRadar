from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from bot.backtest.dataset import load_backtest_samples
from bot.settlements import Settlement
from bot.storage import WatchlistStore


class BacktestDatasetTests(unittest.TestCase):
    def test_settlement_file_has_priority_over_latest_mark(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "watchlist.sqlite")
            store = WatchlistStore(db_path)
            store.insert_snapshots([_snapshot()])
            store.insert_shadow_fills([_fill()])
            store.insert_shadow_marks([_snapshot(no_mid=0.9)])

            samples = load_backtest_samples(
                db_path,
                [
                    Settlement(
                        slug="market",
                        side=None,
                        status="settled",
                        close_price=None,
                        winning_side="BUY_NO",
                        timestamp_utc="2026-06-30T00:00:00+00:00",
                        note=None,
                    )
                ],
            )

        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0].target_source, "settlement_file")
        self.assertEqual(samples[0].target_price, 1.0)
        self.assertEqual(samples[0].target_yes_probability, 0.01)
        self.assertEqual(samples[0].realized_pnl, 0.54)

    def test_buy_no_latest_mark_converts_to_yes_probability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "watchlist.sqlite")
            store = WatchlistStore(db_path)
            store.insert_snapshots([_snapshot(no_mid=0.72)])
            store.insert_shadow_fills([_fill()])
            store.insert_shadow_marks([_snapshot(no_mid=0.72)])

            samples = load_backtest_samples(db_path)

        self.assertEqual(samples[0].target_source, "latest_mark")
        self.assertEqual(samples[0].target_price, 0.72)
        self.assertAlmostEqual(samples[0].target_yes_probability or 0, 0.28)

    def test_multiple_snapshots_for_one_fill_produce_one_trade_sample(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "watchlist.sqlite")
            store = WatchlistStore(db_path)
            store.insert_snapshots([_snapshot(), {**_snapshot(), "timestamp_utc": "2026-04-27T00:05:00+00:00"}])
            store.insert_shadow_fills([_fill()])

            samples = load_backtest_samples(db_path)

        self.assertEqual(len(samples), 1)

    def test_share_quantity_scales_realized_pnl_consistently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "watchlist.sqlite")
            store = WatchlistStore(db_path)
            store.insert_snapshots([_snapshot()])
            store.insert_shadow_fills([_fill(share_quantity=10.0)])

            samples = load_backtest_samples(
                db_path,
                [
                    Settlement(
                        slug="market",
                        side=None,
                        status="settled",
                        close_price=None,
                        winning_side="BUY_NO",
                        timestamp_utc="2026-06-30T00:00:00+00:00",
                        note=None,
                    )
                ],
            )

        self.assertEqual(samples[0].realized_pnl, 5.4)


def _snapshot(no_mid: float = 0.45) -> dict[str, object]:
    yes_mid = round(1 - no_mid, 4)
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
        "preferred_price": no_mid,
        "in_target_band": True,
        "yes_bid": round(yes_mid - 0.005, 4),
        "yes_ask": round(yes_mid + 0.005, 4),
        "yes_mid": yes_mid,
        "no_bid": round(no_mid - 0.005, 4),
        "no_ask": round(no_mid + 0.005, 4),
        "no_mid": no_mid,
        "no_spread": 0.01,
        "evidence_score": 0.1,
        "evidence_confidence": 0.7,
        "evidence_preheat_score": 0.2,
        "evidence_cadence_score": 0.3,
        "evidence_partner_score": 0.1,
        "model_side": "BUY_NO",
        "p_model": yes_mid,
        "p_mid": yes_mid,
        "edge": 0.04,
        "net_edge": 0.02,
        "max_entry_price": 0.48,
        "signal_ok": True,
        "market_ok": True,
        "signal_reasons_detail": ["model_profile=music_release"],
    }


def _fill(share_quantity: float | None = None) -> dict[str, object]:
    payload = {
        "timestamp_utc": "2026-04-27T00:01:00+00:00",
        "slug": "market",
        "label": "Market",
        "market_id": "1",
        "side": "BUY_NO",
        "fill_price": 0.46,
        "max_entry_price": 0.48,
        "net_edge": 0.02,
        "reason": "ask_at_or_below_max_entry",
        "snapshot_timestamp_utc": "2026-04-27T00:00:00+00:00",
    }
    if share_quantity is not None:
        payload["share_quantity"] = share_quantity
    return payload


if __name__ == "__main__":
    unittest.main()
