from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Settlement:
    slug: str
    side: str | None
    status: str
    close_price: float | None
    winning_side: str | None
    timestamp_utc: str | None
    note: str | None


def load_settlements(path: str | None) -> list[Settlement]:
    if not path:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Settlement file must contain a JSON list.")

    settlements: list[Settlement] = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("Each settlement row must be an object.")
        slug = str(row.get("slug", "")).strip()
        if not slug:
            raise ValueError("Settlement row missing slug.")
        side = optional_side(row.get("side"))
        winning_side = optional_side(row.get("winning_side"))
        close_price = float_or_none(row.get("close_price"))
        if winning_side is None and close_price is None:
            raise ValueError(f"Settlement row for slug={slug} needs winning_side or close_price.")
        status = str(row.get("status") or ("settled" if winning_side else "closed"))
        if status not in {"closed", "settled"}:
            raise ValueError(f"Unsupported settlement status={status}")
        settlements.append(
            Settlement(
                slug=slug,
                side=side,
                status=status,
                close_price=close_price,
                winning_side=winning_side,
                timestamp_utc=str(
                    row.get("timestamp_utc")
                    or row.get("closed_at_utc")
                    or row.get("settled_at_utc")
                    or ""
                )
                or None,
                note=str(row.get("note") or "") or None,
            )
        )
    return settlements


def settlement_index(settlements: list[Settlement]) -> dict[tuple[str, str | None], Settlement]:
    return {(settlement.slug, settlement.side): settlement for settlement in settlements}


def settlement_close_price(settlement: Settlement, side: str) -> float | None:
    if settlement.close_price is not None:
        return settlement.close_price
    if settlement.winning_side is None:
        return None
    return 1.0 if settlement.winning_side == side else 0.0


def optional_side(value: object) -> str | None:
    if value is None or value == "":
        return None
    side = str(value)
    if side not in {"BUY_YES", "BUY_NO"}:
        raise ValueError(f"Unsupported side={side}")
    return side


def float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
