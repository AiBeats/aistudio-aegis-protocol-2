"""Tests for the ABV Fortress SOS Listener."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("ABV_LOG_LEVEL", "WARNING")
os.environ["SOS_HMAC_SECRET"] = "test-secret-key-for-sos"

from src.public.fortress.sos_listener import SOSCommand, SOSListener, SOSMessage


class TestSignatureVerification(unittest.TestCase):
    """Test HMAC signature verification."""

    def setUp(self) -> None:
        self.listener = SOSListener()
        self.secret = "test-secret-key-for-sos"

    def _sign(self, payload: bytes) -> str:
        return hmac.new(
            self.secret.encode(), payload, hashlib.sha256
        ).hexdigest()

    def test_valid_signature(self) -> None:
        payload = b'{"command":"lock","timestamp":0}'
        sig = self._sign(payload)
        self.assertTrue(self.listener.verify_signature(payload, sig))

    def test_invalid_signature(self) -> None:
        payload = b'{"command":"lock","timestamp":0}'
        self.assertFalse(self.listener.verify_signature(payload, "invalid"))

    def test_tampered_payload(self) -> None:
        payload = b'{"command":"lock","timestamp":0}'
        sig = self._sign(payload)
        tampered = b'{"command":"wipe","timestamp":0}'
        self.assertFalse(self.listener.verify_signature(tampered, sig))


class TestMessageParsing(unittest.TestCase):
    """Test SOS message parsing and validation."""

    def setUp(self) -> None:
        self.listener = SOSListener()
        self.secret = "test-secret-key-for-sos"

    def _make_signed_message(self, command: str, ts: float = None) -> tuple[bytes, str]:
        if ts is None:
            ts = time.time()
        payload = json.dumps({
            "command": command,
            "timestamp": ts,
            "sender": "test",
        }).encode()
        sig = hmac.new(
            self.secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return payload, sig

    def test_valid_lock_message(self) -> None:
        payload, sig = self._make_signed_message("lock")
        msg = self.listener.parse_message(payload, sig)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.command, SOSCommand.LOCK)

    def test_valid_wipe_message(self) -> None:
        payload, sig = self._make_signed_message("wipe")
        msg = self.listener.parse_message(payload, sig)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.command, SOSCommand.WIPE)

    def test_stale_message_rejected(self) -> None:
        old_ts = time.time() - 120  # 2 minutes ago
        payload, sig = self._make_signed_message("lock", ts=old_ts)
        msg = self.listener.parse_message(payload, sig)
        self.assertIsNone(msg)

    def test_invalid_json_rejected(self) -> None:
        payload = b"not json"
        sig = hmac.new(
            self.secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        msg = self.listener.parse_message(payload, sig)
        self.assertIsNone(msg)

    def test_invalid_command_rejected(self) -> None:
        payload = json.dumps({
            "command": "explode",
            "timestamp": time.time(),
        }).encode()
        sig = hmac.new(
            self.secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        msg = self.listener.parse_message(payload, sig)
        self.assertIsNone(msg)


class TestCommandProcessing(unittest.TestCase):
    """Test end-to-end command processing."""

    def setUp(self) -> None:
        self.listener = SOSListener()
        self.secret = "test-secret-key-for-sos"
        self.handled_commands: list[SOSMessage] = []

    def _handler(self, msg: SOSMessage) -> None:
        self.handled_commands.append(msg)

    def test_process_with_handler(self) -> None:
        self.listener.register_handler(SOSCommand.LOCK, self._handler)

        payload = json.dumps({
            "command": "lock",
            "timestamp": time.time(),
            "sender": "test",
        }).encode()
        sig = hmac.new(
            self.secret.encode(), payload, hashlib.sha256
        ).hexdigest()

        result = self.listener.process(payload, sig)
        self.assertTrue(result)
        self.assertEqual(len(self.handled_commands), 1)

    def test_process_without_handler(self) -> None:
        payload = json.dumps({
            "command": "locate",
            "timestamp": time.time(),
            "sender": "test",
        }).encode()
        sig = hmac.new(
            self.secret.encode(), payload, hashlib.sha256
        ).hexdigest()

        result = self.listener.process(payload, sig)
        self.assertFalse(result)  # No handler registered


if __name__ == "__main__":
    unittest.main()
