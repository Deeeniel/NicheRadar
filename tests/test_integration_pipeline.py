from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from bot.backtest.dataset import load_backtest_samples
from bot.config import BotConfig
from bot.execution import build_shadow_fills
from bot.models import Evidence, Market, ParsedMarket, Signal
from bot.reporting import build_dashboard_report
from bot.storage import WatchlistStore
from bot.watchlist import WatchlistItem, build_watchlist_snapshot


class IntegrationPipelineTests(unittest.TestCase):
    def test_watchlist_snapshot_to_fill_to_reports_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "watchlist.sqlite")
            store = WatchlistStore(db_path)
            item = WatchlistItem(
                slug="market",
                label="Market",
                preferred_side="BUY_NO",
                entry_band_low=0.44,
                entry_band_high=0.50,
                note="pipeline",
            )
            market = Market(
                market_id="1",
                title="Will Artist release a new album?",
                description="Official streaming release",
                rules="Official release only",
                category="social",
                closes_at=datetime.now(timezone.utc) + timedelta(days=5),
                volume=5000,
                yes_bid=0.54,
                yes_ask=0.56,
                no_bid=0.44,
                no_ask=0.46,
                metadata={
                    "book_status": "complete",
                    "yes_ask_source": "book",
                    "no_ask_source": "book",
                },
            )
            parsed = ParsedMarket(
                market=market,
                event_type="content_release",
                subject="Artist",
                platform="streaming",
                action="release",
                days_to_expiry=5,
            )
            evidence = Evidence(
                score=0.3,
                confidence=0.8,
                reasons=["evidence_source=test"],
                mode="source",
                preheat_score=0.4,
                cadence_score=0.3,
                partner_score=0.2,
            )
            signal = Signal(
                market_id="1",
                side="BUY_NO",
                p_model=0.42,
                p_mid=0.55,
                edge=0.12,
                net_edge=0.04,
                max_entry_price=0.48,
                confidence=0.8,
                reasons=["model_profile=music_release"],
                profile_name="music_release",
            )

            snapshot = build_watchlist_snapshot(
                item,
                market,
                parsed,
                evidence,
                signal,
                market_ok=True,
                market_reasons=[],
                signal_ok=True,
                signal_reasons=[],
            )
            fills = build_shadow_fills([snapshot], BotConfig())

            self.assertEqual(len(fills), 1)
            store.insert_snapshots([snapshot])
            store.insert_evidence_runs([snapshot])
            store.insert_shadow_fills(fills)
            store.insert_shadow_marks([snapshot])

            report = build_dashboard_report(db_path, limit=5)
            samples = load_backtest_samples(db_path)

        self.assertEqual(report["counts"]["shadow_fills"], 1)
        self.assertEqual(report["health"]["book_complete_rate"], 1.0)
        self.assertEqual(report["health"]["executable_snapshot_rate"], 1.0)
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0].model_profile, "music_release")
        self.assertEqual(samples[0].target_source, "latest_mark")


if __name__ == "__main__":
    unittest.main()
