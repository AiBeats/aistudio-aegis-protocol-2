"""ABV Fortress — SOS Listener.

HTTP/SMS relay listener for remote lock and wipe commands.
Commands are verified using HMAC-SHA256 signatures to prevent
unauthorized triggers.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

from src.public.common.logging_utils import get_logger
from src.public.common.config import get_config

logger = get_logger("fortress.sos")


class SOSCommand(Enum):
    """Supported remote SOS commands."""
    LOCK = "lock"
    WIPE = "wipe"
    LOCATE = "locate"
    STATUS = "status"


@dataclass
class SOSMessage:
    """A verified SOS command message."""
    command: SOSCommand
    timestamp: float
    sender: str
    payload: Dict[str, str] = field(default_factory=dict)
    signature: str = ""

    @property
    def age_seconds(self) -> float:
        """Seconds since the message was created."""
        return time.time() - self.timestamp


class SOSListener:
    """Listens for and processes remote SOS commands.

    Commands arrive via HTTP POST (or SMS relay) and must include
    a valid HMAC-SHA256 signature computed over the JSON payload.

    Replay protection: messages older than ``max_age_seconds`` are rejected.
    """

    MAX_AGE_SECONDS = 60.0  # reject stale commands

    def __init__(self) -> None:
        cfg = get_config()
        self._hmac_secret: str = cfg.sos_hmac_secret
        self._relay_url: str = cfg.sos_relay_url
        self._handlers: Dict[SOSCommand, List[Callable[[SOSMessage], None]]] = {
            cmd: [] for cmd in SOSCommand
        }
        self._command_log: List[SOSMessage] = []

        # BEGIN_PRIVATE
        # Extension hook: private SOS overrides (tactical wipe escalation)
        self._private_override: Optional[Callable[["SOSListener", SOSMessage], None]] = None
        # END_PRIVATE

    def register_handler(self, command: SOSCommand, handler: Callable[[SOSMessage], None]) -> None:
        """Register a handler for a specific SOS command type."""
        self._handlers[command].append(handler)

    def verify_signature(self, payload_bytes: bytes, signature: str) -> bool:
        """Verify HMAC-SHA256 signature over the raw payload bytes."""
        if not self._hmac_secret:
            logger.error("SOS_HMAC_SECRET is not configured — rejecting command")
            return False

        expected = hmac.new(
            self._hmac_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def parse_message(self, raw_payload: bytes, signature: str) -> Optional[SOSMessage]:
        """Parse and verify an incoming SOS message.

        Args:
            raw_payload: Raw JSON bytes from the request body.
            signature: The ``X-SOS-Signature`` header value.

        Returns:
            A verified :class:`SOSMessage`, or ``None`` on failure.
        """
        if not self.verify_signature(raw_payload, signature):
            logger.warning("SOS message failed signature verification")
            return None

        try:
            data = json.loads(raw_payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("SOS message has invalid JSON payload")
            return None

        try:
            msg = SOSMessage(
                command=SOSCommand(data["command"]),
                timestamp=float(data["timestamp"]),
                sender=data.get("sender", "unknown"),
                payload=data.get("payload", {}),
                signature=signature,
            )
        except (KeyError, ValueError) as exc:
            logger.warning("SOS message parse error: %s", exc)
            return None

        if msg.age_seconds > self.MAX_AGE_SECONDS:
            logger.warning(
                "SOS message rejected (too old: %.1fs)", msg.age_seconds
            )
            return None

        return msg

    def process(self, raw_payload: bytes, signature: str) -> bool:
        """End-to-end: verify, parse, and dispatch an SOS command.

        Returns:
            ``True`` if the command was successfully processed.
        """
        msg = self.parse_message(raw_payload, signature)
        if msg is None:
            return False

        logger.info("SOS command received: %s from %s", msg.command.value, msg.sender)
        self._command_log.append(msg)

        # BEGIN_PRIVATE
        # Private SOS override — tactical wipe escalation
        if self._private_override is not None:
            self._private_override(self, msg)
        # END_PRIVATE

        handlers = self._handlers.get(msg.command, [])
        if not handlers:
            logger.warning("No handlers registered for SOS command: %s", msg.command.value)
            return False

        for handler in handlers:
            try:
                handler(msg)
            except Exception:
                logger.exception("SOS handler error for %s", msg.command.value)

        return True

    def create_flask_app(self) -> "flask.Flask":
        """Create a minimal Flask app that exposes the SOS endpoint.

        Returns:
            A Flask application with ``POST /sos`` route.
        """
        import flask

        app = flask.Flask("sos_listener")

        @app.route("/sos", methods=["POST"])
        def sos_endpoint() -> flask.Response:
            signature = flask.request.headers.get("X-SOS-Signature", "")
            raw = flask.request.get_data()
            success = self.process(raw, signature)
            status = 200 if success else 403
            return flask.jsonify({"ok": success}), status

        @app.route("/sos/health", methods=["GET"])
        def health() -> flask.Response:
            return flask.jsonify({"status": "online", "commands_processed": len(self._command_log)})

        return app

    @property
    def command_log(self) -> List[SOSMessage]:
        """Return the log of all processed SOS commands."""
        return list(self._command_log)
