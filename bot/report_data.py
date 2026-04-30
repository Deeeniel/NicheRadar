from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from contextlib import closing

from bot.backtest.dataset import BacktestSample, load_backtest_samples_from_connection
from bot.domain import PositionRecord
from bot.positions import load_positions_from_connection
from bot.settlements import Settlement


@dataclass(frozen=True)
class DashboardData:
    snapshots: list[dict[str, object]]
    alerts: list[dict[str, object]]
    fills: list[dict[str, object]]
    positions: list[PositionRecord]
    backtest_samples: list[BacktestSample]


def load_dashboard_data(
    db_path: str,
    settlements: list[Settlement] | None = None,
) -> DashboardData:
    settlements = settlements or []
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        snapshots = [_row_dict(row) for row in connection.execute("SELECT * FROM watchlist_snapshots ORDER BY id").fetchall()]
        alerts = [_row_dict(row) for row in connection.execute("SELECT * FROM watchlist_alerts ORDER BY id").fetchall()]
        fills = [_row_dict(row) for row in connection.execute("SELECT * FROM shadow_fills ORDER BY id").fetchall()]
        positions = load_positions_from_connection(connection, settlements)
        positions_by_fill_id = {position.fill_id: position for position in positions}
        backtest_samples = load_backtest_samples_from_connection(
            connection,
            settlements,
            positions_by_fill_id=positions_by_fill_id,
        )
    return DashboardData(
        snapshots=snapshots,
        alerts=alerts,
        fills=fills,
        positions=positions,
        backtest_samples=backtest_samples,
    )


def _row_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}
