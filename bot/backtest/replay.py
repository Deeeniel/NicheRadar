from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from bot.domain import PositionRecord
from bot.positions import load_positions
from bot.settlements import Settlement


def replay_shadow_pnl(db_path: str, settlements: list[Settlement] | None = None) -> dict[str, object]:
    return replay_shadow_pnl_from_positions(load_positions(db_path, settlements))


def replay_shadow_pnl_from_positions(positions: list[PositionRecord]) -> dict[str, object]:
    records = []
    for position in positions:
        status = "open_marked" if position.current_price is not None else "open_unmarked"
        pnl = position.unrealized_pnl if position.current_price is not None else None
        pnl_pct = position.unrealized_pnl_pct
        closed_at_utc = None
        current_price = position.current_price
        close_source = "latest_mark" if position.current_price is not None else None
        if position.status in {"closed", "settled"}:
            status = position.status
            pnl = position.realized_pnl
            pnl_pct = (
                round((position.realized_pnl or 0.0) / position.risk_amount, 6)
                if position.risk_amount > 0 and position.realized_pnl is not None
                else None
            )
            closed_at_utc = position.closed_at_utc
            close_source = position.close_source
        records.append(
            {
                "fill_id": position.fill_id,
                "slug": position.slug,
                "label": position.slug,
                "market_id": None,
                "event_type": position.event_type,
                "platform": position.platform,
                "side": position.side,
                "status": status,
                "opened_at_utc": position.opened_at_utc,
                "closed_at_utc": closed_at_utc,
                "fill_price": position.fill_price,
                "current_price": current_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "max_entry_price": position.max_entry_price,
                "net_edge": position.net_edge,
                "close_source": close_source,
                "settlement_note": position.settlement_note,
            }
        )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "records": records,
        "summary_by_event_type": _summarize(records, "event_type"),
        "summary_by_status": _summarize(records, "status"),
        "summary_by_close_source": _summarize(records, "close_source"),
        "diagnostics": _diagnostics(records),
    }


def format_shadow_replay_report(replay: dict[str, object]) -> list[str]:
    records = list(replay.get("records", []))
    lines = [
        "shadow_replay",
        f"record_count={replay.get('record_count', 0)}",
    ]
    for row in replay.get("summary_by_event_type", []):
        assert isinstance(row, dict)
        lines.append(_format_summary_row("event_type", row))
    for row in replay.get("summary_by_status", []):
        assert isinstance(row, dict)
        lines.append(_format_summary_row("status", row))
    for row in replay.get("summary_by_close_source", []):
        assert isinstance(row, dict)
        lines.append(_format_summary_row("close_source", row))
    diagnostics = replay.get("diagnostics")
    if isinstance(diagnostics, dict):
        lines.append(
            "shadow_diagnostics "
            f"open_marked={diagnostics.get('open_marked_count', 0)} "
            f"open_unmarked={diagnostics.get('open_unmarked_count', 0)} "
            f"closed_or_settled={diagnostics.get('closed_or_settled_count', 0)} "
            f"missing_close_source={diagnostics.get('missing_close_source_count', 0)}"
        )
    for record in records:
        assert isinstance(record, dict)
        pnl = record.get("pnl")
        pnl_text = "none" if pnl is None else f"{float(pnl):.4f}"
        price = record.get("current_price")
        price_text = "none" if price is None else f"{float(price):.4f}"
        lines.append(
            "shadow_position "
            f"fill_id={record.get('fill_id')} "
            f"slug={record.get('slug')} "
            f"event_type={record.get('event_type')} "
            f"side={record.get('side')} "
            f"status={record.get('status')} "
            f"fill_price={float(record.get('fill_price', 0)):.4f} "
            f"current_price={price_text} "
            f"pnl={pnl_text}"
        )
    return lines


def write_replay_json(path: str, replay: dict[str, object]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(replay, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _summarize(records: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for record in records:
        groups.setdefault(str(record.get(key) or "unknown"), []).append(record)

    summary: list[dict[str, object]] = []
    for group_key in sorted(groups):
        rows = groups[group_key]
        pnl_values = [float(row["pnl"]) for row in rows if row.get("pnl") is not None]
        closed = [row for row in rows if row.get("status") in {"closed", "settled"}]
        open_rows = [row for row in rows if str(row.get("status", "")).startswith("open_")]
        wins = [pnl for pnl in pnl_values if pnl > 0]
        summary.append(
            {
                key: group_key,
                "count": len(rows),
                "open_count": len(open_rows),
                "closed_count": len(closed),
                "marked_count": len(pnl_values),
                "total_pnl": round(sum(pnl_values), 4),
                "avg_pnl": round(sum(pnl_values) / len(pnl_values), 4) if pnl_values else None,
                "win_rate": round(len(wins) / len(pnl_values), 4) if pnl_values else None,
                "realized_pnl": round(sum(float(row["pnl"]) for row in closed if row.get("pnl") is not None), 4),
                "unrealized_pnl": round(sum(float(row["pnl"]) for row in open_rows if row.get("pnl") is not None), 4),
            }
        )
    return summary


def _diagnostics(records: list[dict[str, object]]) -> dict[str, int]:
    return {
        "open_marked_count": sum(1 for row in records if row.get("status") == "open_marked"),
        "open_unmarked_count": sum(1 for row in records if row.get("status") == "open_unmarked"),
        "closed_or_settled_count": sum(1 for row in records if row.get("status") in {"closed", "settled"}),
        "missing_close_source_count": sum(
            1 for row in records if row.get("status") in {"closed", "settled"} and not row.get("close_source")
        ),
    }


def _format_summary_row(key: str, row: dict[str, object]) -> str:
    avg = row.get("avg_pnl")
    win_rate = row.get("win_rate")
    avg_text = "none" if avg is None else f"{float(avg):.4f}"
    win_text = "none" if win_rate is None else f"{float(win_rate):.2%}"
    return (
        "shadow_summary "
        f"{key}={row.get(key)} "
        f"count={row.get('count')} "
        f"open={row.get('open_count')} "
        f"closed={row.get('closed_count')} "
        f"total_pnl={float(row.get('total_pnl', 0)):.4f} "
        f"realized_pnl={float(row.get('realized_pnl', 0)):.4f} "
        f"unrealized_pnl={float(row.get('unrealized_pnl', 0)):.4f} "
        f"avg_pnl={avg_text} "
        f"win_rate={win_text}"
    )
