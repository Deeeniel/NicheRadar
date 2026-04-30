from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SnapshotRecord:
    timestamp_utc: str | None
    slug: str
    label: str | None
    market_id: str | None
    title: str | None
    subject: str | None
    platform: str | None
    event_type: str | None
    preferred_side: str | None
    model_side: str | None
    yes_bid: float | None
    yes_ask: float | None
    yes_mid: float | None
    no_bid: float | None
    no_ask: float | None
    no_mid: float | None
    yes_spread: float | None
    no_spread: float | None
    net_edge: float | None
    p_model: float | None
    p_mid: float | None
    evidence_score: float | None
    evidence_mode: str | None
    signal_ok: bool | None
    market_ok: bool | None
    book_status: str | None
    yes_ask_source: str | None
    no_ask_source: str | None
    max_entry_price: float | None
    signal_reasons_detail: list[str]

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> "SnapshotRecord":
        return cls(
            timestamp_utc=_string_or_none(raw.get("timestamp_utc")),
            slug=_required_string(raw.get("slug")),
            label=_string_or_none(raw.get("label")),
            market_id=_string_or_none(raw.get("market_id")),
            title=_string_or_none(raw.get("title")),
            subject=_string_or_none(raw.get("subject")),
            platform=_string_or_none(raw.get("platform")),
            event_type=_string_or_none(raw.get("event_type")),
            preferred_side=_side_or_none(raw.get("preferred_side")),
            model_side=_side_or_none(raw.get("model_side")),
            yes_bid=_float_or_none(raw.get("yes_bid")),
            yes_ask=_float_or_none(raw.get("yes_ask")),
            yes_mid=_float_or_none(raw.get("yes_mid")),
            no_bid=_float_or_none(raw.get("no_bid")),
            no_ask=_float_or_none(raw.get("no_ask")),
            no_mid=_float_or_none(raw.get("no_mid")),
            yes_spread=_float_or_none(raw.get("yes_spread")),
            no_spread=_float_or_none(raw.get("no_spread")),
            net_edge=_float_or_none(raw.get("net_edge")),
            p_model=_float_or_none(raw.get("p_model")),
            p_mid=_float_or_none(raw.get("p_mid")),
            evidence_score=_float_or_none(raw.get("evidence_score")),
            evidence_mode=_string_or_none(raw.get("evidence_mode")),
            signal_ok=_bool_or_none(raw.get("signal_ok")),
            market_ok=_bool_or_none(raw.get("market_ok")),
            book_status=_string_or_none(raw.get("book_status")),
            yes_ask_source=_string_or_none(raw.get("yes_ask_source")),
            no_ask_source=_string_or_none(raw.get("no_ask_source")),
            max_entry_price=_float_or_none(raw.get("max_entry_price")),
            signal_reasons_detail=_string_list(raw.get("signal_reasons_detail")),
        )

    def side_mid(self, side: str | None) -> float | None:
        if side == "BUY_YES":
            return self.yes_mid
        if side == "BUY_NO":
            return self.no_mid
        return None

    def side_spread(self, side: str | None) -> float | None:
        if side == "BUY_YES":
            return self.yes_spread
        if side == "BUY_NO":
            return self.no_spread
        return None

    def ask_for_side(self, side: str | None) -> float | None:
        if side == "BUY_YES":
            return self.yes_ask
        if side == "BUY_NO":
            return self.no_ask
        return None

    def ask_source_for_side(self, side: str | None) -> str | None:
        if side == "BUY_YES":
            return self.yes_ask_source
        if side == "BUY_NO":
            return self.no_ask_source
        return None


@dataclass(frozen=True)
class ShadowFillRecord:
    timestamp_utc: str | None
    slug: str
    label: str | None
    market_id: str | None
    event_type: str | None
    platform: str | None
    side: str
    fill_price: float
    risk_amount: float | None
    share_quantity: float | None
    max_entry_price: float | None
    net_edge: float | None
    reason: str | None
    position_status: str | None
    snapshot_timestamp_utc: str | None

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> "ShadowFillRecord":
        return cls(
            timestamp_utc=_string_or_none(raw.get("timestamp_utc")),
            slug=_required_string(raw.get("slug")),
            label=_string_or_none(raw.get("label")),
            market_id=_string_or_none(raw.get("market_id")),
            event_type=_string_or_none(raw.get("event_type")),
            platform=_string_or_none(raw.get("platform")),
            side=_required_side(raw.get("side")),
            fill_price=_required_float(raw.get("fill_price")),
            risk_amount=_float_or_none(raw.get("risk_amount") or raw.get("portfolio_risk_amount")),
            share_quantity=_float_or_none(raw.get("share_quantity")),
            max_entry_price=_float_or_none(raw.get("max_entry_price")),
            net_edge=_float_or_none(raw.get("net_edge")),
            reason=_string_or_none(raw.get("reason")),
            position_status=_string_or_none(raw.get("position_status")),
            snapshot_timestamp_utc=_string_or_none(raw.get("snapshot_timestamp_utc")),
        )


@dataclass(frozen=True)
class PositionRecord:
    fill_id: int
    slug: str
    side: str
    event_type: str
    platform: str
    opened_at_utc: str
    fill_price: float
    risk_amount: float
    share_quantity: float | None
    max_entry_price: float | None
    net_edge: float | None
    status: str
    current_price: float | None
    price_pnl: float | None
    unrealized_pnl: float
    unrealized_pnl_pct: float | None
    realized_pnl: float | None
    closed_at_utc: str | None
    close_source: str | None
    settlement_note: str | None


@dataclass(frozen=True)
class WatchlistSnapshotRecord:
    timestamp_utc: str
    slug: str
    label: str
    market_id: str | None
    title: str
    preferred_side: str
    target_band_low: float
    target_band_high: float
    preferred_price: float
    in_target_band: bool
    yes_bid: float
    yes_ask: float
    yes_mid: float
    no_bid: float
    no_ask: float
    no_mid: float
    yes_spread: float | None
    no_spread: float | None
    spread: float | None
    book_status: str | None
    yes_ask_source: str | None
    no_ask_source: str | None
    volume: float | None
    note: str
    market_ok: bool
    market_reasons: list[str]
    signal_ok: bool
    signal_reasons: list[str]
    subject: str | None = None
    platform: str | None = None
    event_type: str | None = None
    days_to_expiry: float | None = None
    evidence_score: float | None = None
    evidence_confidence: float | None = None
    evidence_reasons: list[str] | None = None
    evidence_mode: str | None = None
    evidence_source_url: str | None = None
    evidence_source_type: str | None = None
    evidence_recent_entries_30d: int | None = None
    evidence_keyword_hits_30d: int | None = None
    evidence_latest_entry_age_days: float | None = None
    evidence_preheat_score: float | None = None
    evidence_cadence_score: float | None = None
    evidence_partner_score: float | None = None
    evidence_source_reliability: float | None = None
    evidence_matched_items: list[object] | None = None
    model_side: str | None = None
    p_model: float | None = None
    p_mid: float | None = None
    edge: float | None = None
    net_edge: float | None = None
    max_entry_price: float | None = None
    model_confidence: float | None = None
    signal_reasons_detail: list[str] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "timestamp_utc": self.timestamp_utc,
            "slug": self.slug,
            "label": self.label,
            "market_id": self.market_id,
            "title": self.title,
            "preferred_side": self.preferred_side,
            "target_band_low": self.target_band_low,
            "target_band_high": self.target_band_high,
            "preferred_price": self.preferred_price,
            "in_target_band": self.in_target_band,
            "yes_bid": self.yes_bid,
            "yes_ask": self.yes_ask,
            "yes_mid": self.yes_mid,
            "no_bid": self.no_bid,
            "no_ask": self.no_ask,
            "no_mid": self.no_mid,
            "yes_spread": self.yes_spread,
            "no_spread": self.no_spread,
            "spread": self.spread,
            "book_status": self.book_status,
            "yes_ask_source": self.yes_ask_source,
            "no_ask_source": self.no_ask_source,
            "volume": self.volume,
            "note": self.note,
            "market_ok": self.market_ok,
            "market_reasons": list(self.market_reasons),
            "signal_ok": self.signal_ok,
            "signal_reasons": list(self.signal_reasons),
        }
        _put_if_not_none(payload, "subject", self.subject)
        _put_if_not_none(payload, "platform", self.platform)
        _put_if_not_none(payload, "event_type", self.event_type)
        _put_if_not_none(payload, "days_to_expiry", self.days_to_expiry)
        _put_if_not_none(payload, "evidence_score", self.evidence_score)
        _put_if_not_none(payload, "evidence_confidence", self.evidence_confidence)
        _put_if_not_none(payload, "evidence_reasons", list(self.evidence_reasons or []))
        _put_if_not_none(payload, "evidence_mode", self.evidence_mode)
        _put_if_not_none(payload, "evidence_source_url", self.evidence_source_url)
        _put_if_not_none(payload, "evidence_source_type", self.evidence_source_type)
        _put_if_not_none(payload, "evidence_recent_entries_30d", self.evidence_recent_entries_30d)
        _put_if_not_none(payload, "evidence_keyword_hits_30d", self.evidence_keyword_hits_30d)
        _put_if_not_none(payload, "evidence_latest_entry_age_days", self.evidence_latest_entry_age_days)
        _put_if_not_none(payload, "evidence_preheat_score", self.evidence_preheat_score)
        _put_if_not_none(payload, "evidence_cadence_score", self.evidence_cadence_score)
        _put_if_not_none(payload, "evidence_partner_score", self.evidence_partner_score)
        _put_if_not_none(payload, "evidence_source_reliability", self.evidence_source_reliability)
        _put_if_not_none(payload, "evidence_matched_items", list(self.evidence_matched_items or []))
        _put_if_not_none(payload, "model_side", self.model_side)
        _put_if_not_none(payload, "p_model", self.p_model)
        _put_if_not_none(payload, "p_mid", self.p_mid)
        _put_if_not_none(payload, "edge", self.edge)
        _put_if_not_none(payload, "net_edge", self.net_edge)
        _put_if_not_none(payload, "max_entry_price", self.max_entry_price)
        _put_if_not_none(payload, "model_confidence", self.model_confidence)
        _put_if_not_none(payload, "signal_reasons_detail", list(self.signal_reasons_detail or []))
        return payload

    def alert_summary(self) -> dict[str, object]:
        return {
            "preferred_price": self.preferred_price,
            "in_target_band": self.in_target_band,
            "evidence_score": self.evidence_score,
            "signal_ok": self.signal_ok,
            "model_side": self.model_side,
            "net_edge": self.net_edge,
            "yes_mid": self.yes_mid,
        }

    def to_snapshot_record(self) -> SnapshotRecord:
        return SnapshotRecord.from_mapping(self.to_dict())


def parse_json_mapping(raw: object) -> dict[str, object]:
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def storage_row_payload(row: dict[str, object]) -> dict[str, object]:
    payload = parse_json_mapping(row.get("raw_json"))
    return payload or row


def reason_value(reasons: list[str], key: str) -> str | None:
    prefix = f"{key}="
    for reason in reasons:
        if reason.startswith(prefix):
            return reason[len(prefix) :]
    return None


def reason_float(reasons: list[str], key: str) -> float | None:
    value = reason_value(reasons, key)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def profile_name_from_snapshot(snapshot: SnapshotRecord) -> str:
    profile = reason_value(snapshot.signal_reasons_detail, "model_profile")
    if profile:
        return profile
    event_type = str(snapshot.event_type or "")
    platform = str(snapshot.platform or "")
    title = str(snapshot.title or "").lower()
    if event_type == "ipo_event":
        return "ipo_event"
    if event_type == "content_release" and (
        platform in {"apple", "tesla"} or any(word in title for word in ("macbook", "optimus", "hardware", "device"))
    ):
        return "product_release"
    if event_type == "content_release" and (
        platform == "streaming" or any(word in title for word in ("album", "song", "single", "music", "spotify", "apple music"))
    ):
        return "music_release"
    return "default_content"


def _required_string(value: object) -> str:
    text = _string_or_none(value)
    if text is None:
        raise ValueError("Expected non-empty string")
    return text


def _required_float(value: object) -> float:
    number = _float_or_none(value)
    if number is None:
        raise ValueError("Expected numeric value")
    return number


def _required_side(value: object) -> str:
    side = _side_or_none(value)
    if side is None:
        raise ValueError("Expected BUY_YES or BUY_NO")
    return side


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return None


def _side_or_none(value: object) -> str | None:
    if value in {"BUY_YES", "BUY_NO"}:
        return str(value)
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _put_if_not_none(payload: dict[str, object], key: str, value: object) -> None:
    if value is not None:
        payload[key] = value
