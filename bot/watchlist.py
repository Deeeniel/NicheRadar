from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.domain import WatchlistSnapshotRecord
from bot.models import Evidence, Market, ParsedMarket, Signal


@dataclass(frozen=True)
class WatchlistItem:
    slug: str
    label: str
    preferred_side: str
    entry_band_low: float
    entry_band_high: float
    note: str


def load_watchlist(path: str) -> list[WatchlistItem]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    items: list[WatchlistItem] = []
    for item in payload:
        preferred_side = str(item["preferred_side"])
        if preferred_side not in {"BUY_YES", "BUY_NO"}:
            raise ValueError(f"Unsupported preferred_side={preferred_side}")
        entry_band_low = float(item["entry_band_low"])
        entry_band_high = float(item["entry_band_high"])
        if entry_band_low > entry_band_high:
            raise ValueError(f"Invalid entry band for slug={item['slug']}")
        items.append(
            WatchlistItem(
                slug=str(item["slug"]),
                label=str(item["label"]),
                preferred_side=preferred_side,
                entry_band_low=entry_band_low,
                entry_band_high=entry_band_high,
                note=str(item["note"]),
            )
        )
    return items


def build_watchlist_report(
    item: WatchlistItem,
    market: Market,
    parsed: ParsedMarket | None,
    signal: Signal | None,
    market_ok: bool,
    market_reasons: list[str],
    signal_ok: bool,
    signal_reasons: list[str],
) -> list[str]:
    yes_mid = market.mid_probability
    no_mid = market.no_mid_probability
    preferred_price = yes_mid if item.preferred_side == "BUY_YES" else no_mid
    in_band = item.entry_band_low <= preferred_price <= item.entry_band_high
    lines = [
        f"watchlist_market slug={item.slug} label={item.label}",
        f"  title={market.title}",
        f"  preferred_side={item.preferred_side}",
        f"  yes_bid={market.yes_bid:.4f} yes_ask={market.yes_ask:.4f} yes_mid={yes_mid:.4f}",
        f"  no_bid={market.no_bid:.4f} no_ask={market.no_ask:.4f} no_mid={no_mid:.4f}",
        f"  preferred_price={preferred_price:.4f} target_band={item.entry_band_low:.4f}-{item.entry_band_high:.4f}",
        f"  in_target_band={str(in_band).lower()}",
        f"  note={item.note}",
    ]

    if parsed is not None:
        lines.append(
            f"  parsed subject={parsed.subject} platform={parsed.platform} event_type={parsed.event_type} days_to_expiry={parsed.days_to_expiry:.2f}"
        )

    if signal is not None:
        lines.append(
            f"  model side={signal.side} p_model={signal.p_model:.4f} p_mid={signal.p_mid:.4f} net_edge={signal.net_edge:.4f} confidence={signal.confidence:.4f}"
        )
        for reason in signal.reasons:
            lines.append(f"  reason={reason}")

    if not market_ok:
        lines.append(f"  market_filter={','.join(market_reasons)}")
    if not signal_ok:
        lines.append(f"  signal_filter={','.join(signal_reasons)}")
    return lines


def build_watchlist_snapshot(
    item: WatchlistItem,
    market: Market,
    parsed: ParsedMarket | None,
    evidence: Evidence | None,
    signal: Signal | None,
    market_ok: bool,
    market_reasons: list[str],
    signal_ok: bool,
    signal_reasons: list[str],
) -> dict[str, object]:
    return build_watchlist_snapshot_record(
        item,
        market,
        parsed,
        evidence,
        signal,
        market_ok,
        market_reasons,
        signal_ok,
        signal_reasons,
    ).to_dict()


def build_watchlist_snapshot_record(
    item: WatchlistItem,
    market: Market,
    parsed: ParsedMarket | None,
    evidence: Evidence | None,
    signal: Signal | None,
    market_ok: bool,
    market_reasons: list[str],
    signal_ok: bool,
    signal_reasons: list[str],
) -> WatchlistSnapshotRecord:
    yes_mid = market.mid_probability
    no_mid = market.no_mid_probability
    preferred_price = yes_mid if item.preferred_side == "BUY_YES" else no_mid
    return WatchlistSnapshotRecord(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        slug=item.slug,
        label=item.label,
        market_id=market.market_id,
        title=market.title,
        preferred_side=item.preferred_side,
        target_band_low=item.entry_band_low,
        target_band_high=item.entry_band_high,
        preferred_price=preferred_price,
        in_target_band=item.entry_band_low <= preferred_price <= item.entry_band_high,
        yes_bid=market.yes_bid,
        yes_ask=market.yes_ask,
        yes_mid=yes_mid,
        no_bid=market.no_bid,
        no_ask=market.no_ask,
        no_mid=no_mid,
        yes_spread=market.spread,
        no_spread=market.no_spread,
        spread=market.spread_for_side(item.preferred_side),
        book_status=_string_or_none(market.metadata.get("book_status")),
        yes_ask_source=_string_or_none(market.metadata.get("yes_ask_source")),
        no_ask_source=_string_or_none(market.metadata.get("no_ask_source")),
        volume=market.volume,
        note=item.note,
        market_ok=market_ok,
        market_reasons=list(market_reasons),
        signal_ok=signal_ok,
        signal_reasons=list(signal_reasons),
        subject=parsed.subject if parsed is not None else None,
        platform=parsed.platform if parsed is not None else None,
        event_type=parsed.event_type if parsed is not None else None,
        days_to_expiry=parsed.days_to_expiry if parsed is not None else None,
        evidence_score=evidence.score if evidence is not None else None,
        evidence_confidence=evidence.confidence if evidence is not None else None,
        evidence_reasons=list(evidence.reasons) if evidence is not None else None,
        evidence_mode=evidence.mode if evidence is not None else None,
        evidence_source_url=evidence.source_url if evidence is not None else None,
        evidence_source_type=evidence.source_type if evidence is not None else None,
        evidence_recent_entries_30d=evidence.recent_entries_30d if evidence is not None else None,
        evidence_keyword_hits_30d=evidence.keyword_hits_30d if evidence is not None else None,
        evidence_latest_entry_age_days=evidence.latest_entry_age_days if evidence is not None else None,
        evidence_preheat_score=evidence.preheat_score if evidence is not None else None,
        evidence_cadence_score=evidence.cadence_score if evidence is not None else None,
        evidence_partner_score=evidence.partner_score if evidence is not None else None,
        evidence_source_reliability=evidence.source_reliability if evidence is not None else None,
        evidence_matched_items=list(evidence.matched_items) if evidence is not None else None,
        model_side=signal.side if signal is not None else None,
        p_model=signal.p_model if signal is not None else None,
        p_mid=signal.p_mid if signal is not None else None,
        edge=signal.edge if signal is not None else None,
        net_edge=signal.net_edge if signal is not None else None,
        max_entry_price=signal.max_entry_price if signal is not None else None,
        model_confidence=signal.confidence if signal is not None else None,
        signal_reasons_detail=list(signal.reasons) if signal is not None else None,
    )


def append_watchlist_snapshots(path: str, snapshots: list[dict[str, object]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for snapshot in snapshots:
            handle.write(json.dumps(snapshot, ensure_ascii=True) + "\n")


def load_latest_watchlist_snapshots(path: str) -> dict[str, dict[str, object]]:
    target = Path(path)
    if not target.exists():
        return {}

    latest: dict[str, dict[str, object]] = {}
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                snapshot = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(snapshot, dict):
                continue
            slug = snapshot.get("slug")
            if isinstance(slug, str) and slug:
                latest[slug] = snapshot
    return latest


def build_watchlist_alerts(
    previous_by_slug: dict[str, dict[str, object]],
    snapshots: list[dict[str, object]],
    evidence_jump_threshold: float,
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    for snapshot in snapshots:
        current = _snapshot_record(snapshot)
        slug = current.slug
        previous = previous_by_slug.get(slug)
        if not slug or previous is None:
            continue
        prior = _snapshot_record(previous)

        reasons: list[str] = []
        if prior.in_target_band is False and current.in_target_band is True:
            reasons.append("entered_target_band")

        if prior.signal_ok is False and current.signal_ok is True:
            reasons.append("signal_turned_ok")

        previous_score = prior.evidence_score
        current_score = current.evidence_score
        if (
            previous_score is not None
            and current_score is not None
            and current_score - previous_score >= evidence_jump_threshold
        ):
            reasons.append("evidence_score_jump")

        if not reasons:
            continue

        alerts.append(
            {
                "record_type": "alert",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "slug": slug,
                "label": current.label,
                "market_id": current.market_id,
                "title": current.title,
                "alert_reasons": reasons,
                "previous_timestamp_utc": prior.timestamp_utc,
                "current_timestamp_utc": current.timestamp_utc,
                "previous": prior.alert_summary(),
                "current": current.alert_summary(),
            }
        )
    return alerts


def append_watchlist_alerts(path: str, alerts: list[dict[str, object]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for alert in alerts:
            handle.write(json.dumps(alert, ensure_ascii=True) + "\n")


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return None


def _float_value(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _snapshot_record(snapshot: dict[str, object]) -> WatchlistSnapshotRecord:
    return WatchlistSnapshotRecord(
        timestamp_utc=str(snapshot.get("timestamp_utc") or ""),
        slug=str(snapshot.get("slug") or ""),
        label=str(snapshot.get("label") or ""),
        market_id=_string_or_none(snapshot.get("market_id")),
        title=str(snapshot.get("title") or ""),
        preferred_side=str(snapshot.get("preferred_side") or ""),
        target_band_low=_float_value(snapshot.get("target_band_low")) or 0.0,
        target_band_high=_float_value(snapshot.get("target_band_high")) or 0.0,
        preferred_price=_float_value(snapshot.get("preferred_price")) or 0.0,
        in_target_band=_bool_value(snapshot.get("in_target_band")) is True,
        yes_bid=_float_value(snapshot.get("yes_bid")) or 0.0,
        yes_ask=_float_value(snapshot.get("yes_ask")) or 0.0,
        yes_mid=_float_value(snapshot.get("yes_mid")) or 0.0,
        no_bid=_float_value(snapshot.get("no_bid")) or 0.0,
        no_ask=_float_value(snapshot.get("no_ask")) or 0.0,
        no_mid=_float_value(snapshot.get("no_mid")) or 0.0,
        yes_spread=_float_value(snapshot.get("yes_spread")),
        no_spread=_float_value(snapshot.get("no_spread")),
        spread=_float_value(snapshot.get("spread")),
        book_status=_string_or_none(snapshot.get("book_status")),
        yes_ask_source=_string_or_none(snapshot.get("yes_ask_source")),
        no_ask_source=_string_or_none(snapshot.get("no_ask_source")),
        volume=_float_value(snapshot.get("volume")),
        note=str(snapshot.get("note") or ""),
        market_ok=_bool_value(snapshot.get("market_ok")) is True,
        market_reasons=_string_list(snapshot.get("market_reasons")),
        signal_ok=_bool_value(snapshot.get("signal_ok")) is True,
        signal_reasons=_string_list(snapshot.get("signal_reasons")),
        subject=_string_or_none(snapshot.get("subject")),
        platform=_string_or_none(snapshot.get("platform")),
        event_type=_string_or_none(snapshot.get("event_type")),
        days_to_expiry=_float_value(snapshot.get("days_to_expiry")),
        evidence_score=_float_value(snapshot.get("evidence_score")),
        evidence_confidence=_float_value(snapshot.get("evidence_confidence")),
        evidence_reasons=_string_list(snapshot.get("evidence_reasons")),
        evidence_mode=_string_or_none(snapshot.get("evidence_mode")),
        evidence_source_url=_string_or_none(snapshot.get("evidence_source_url")),
        evidence_source_type=_string_or_none(snapshot.get("evidence_source_type")),
        evidence_recent_entries_30d=_int_value(snapshot.get("evidence_recent_entries_30d")),
        evidence_keyword_hits_30d=_int_value(snapshot.get("evidence_keyword_hits_30d")),
        evidence_latest_entry_age_days=_float_value(snapshot.get("evidence_latest_entry_age_days")),
        evidence_preheat_score=_float_value(snapshot.get("evidence_preheat_score")),
        evidence_cadence_score=_float_value(snapshot.get("evidence_cadence_score")),
        evidence_partner_score=_float_value(snapshot.get("evidence_partner_score")),
        evidence_source_reliability=_float_value(snapshot.get("evidence_source_reliability")),
        evidence_matched_items=_list_value(snapshot.get("evidence_matched_items")),
        model_side=_string_or_none(snapshot.get("model_side")),
        p_model=_float_value(snapshot.get("p_model")),
        p_mid=_float_value(snapshot.get("p_mid")),
        edge=_float_value(snapshot.get("edge")),
        net_edge=_float_value(snapshot.get("net_edge")),
        max_entry_price=_float_value(snapshot.get("max_entry_price")),
        model_confidence=_float_value(snapshot.get("model_confidence")),
        signal_reasons_detail=_string_list(snapshot.get("signal_reasons_detail")),
    )


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _list_value(value: object) -> list[object]:
    if isinstance(value, list):
        return list(value)
    return []


def _int_value(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None
