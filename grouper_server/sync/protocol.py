"""
protocol.py — Wire format for sync messages.

Messages are newline-delimited JSON (NDJSON) over raw TCP.
Each line is a complete JSON object with a "type" field.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

# ── Message types ───────────────────────────────────────────────────────


@dataclass
class Hello:
    """Handshake: identifies the sender."""

    type: str = "hello"
    device_id: str = ""
    device_name: str = ""
    protocol_version: int = 2


@dataclass
class SyncRequest:
    """Ask the peer for changes since a known high-water mark."""

    type: str = "sync_request"
    since_id: int = 0  # last changelog ID we received from this peer


@dataclass
class ChangeEntry:
    """A single CDC changelog row, ready for transit."""

    id: int = 0
    device_id: str = ""
    table_name: str = ""
    row_uuid: str = ""
    operation: str = ""  # INSERT | UPDATE | DELETE
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class SyncResponse:
    """Batch of changes sent in reply to a SyncRequest."""

    type: str = "sync_response"
    changes: list[dict[str, Any]] = field(default_factory=list)
    has_more: bool = False
    next_since_id: int = 0


@dataclass
class SyncAck:
    """Confirm we applied changes up to a given ID."""

    type: str = "sync_ack"
    last_applied_id: int = 0


@dataclass
class Error:
    """Report an error to the peer."""

    type: str = "error"
    message: str = ""


# ── Serialization ───────────────────────────────────────────────────────

_MAX_CHANGES_PER_RESPONSE = 10_000

_MSG_TYPES: dict[str, type] = {
    "hello": Hello,
    "sync_request": SyncRequest,
    "sync_response": SyncResponse,
    "sync_ack": SyncAck,
    "error": Error,
}


def encode(msg: Hello | SyncRequest | SyncResponse | SyncAck | Error) -> bytes:
    """Serialize a message to a newline-terminated JSON bytes line."""
    return json.dumps(asdict(msg), separators=(",", ":")).encode() + b"\n"


def decode(line: bytes) -> Hello | SyncRequest | SyncResponse | SyncAck | Error:
    """Deserialize a JSON line into a typed message object.

    Raises :class:`ValueError` on malformed JSON or unknown message types,
    so callers only need a single exception type for wire-format errors.
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed NDJSON: {exc}") from exc

    msg_type = data.get("type", "")
    cls = _MSG_TYPES.get(msg_type)
    if cls is None:
        raise ValueError(f"Unknown message type: {msg_type!r}")

    if cls is SyncResponse:
        changes = data.get("changes", [])
        if len(changes) > _MAX_CHANGES_PER_RESPONSE:
            raise ValueError(
                f"SyncResponse too large: {len(changes)} changes (max {_MAX_CHANGES_PER_RESPONSE})"
            )
        has_more = data.get("has_more", False)
        next_since_id = data.get("next_since_id", 0)
        return SyncResponse(
            changes=changes,
            has_more=bool(has_more),
            next_since_id=int(next_since_id),
        )
    return cls(**{k: v for k, v in data.items() if k != "type"})
