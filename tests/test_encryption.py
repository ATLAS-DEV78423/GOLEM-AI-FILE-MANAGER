"""Tests for secret encryption and decryption.

Covers:
  - Fernet protect/unprotect roundtrip (macOS/Linux)
  - Legacy base64 fallback when cryptography is unavailable
  - Prefix detection and re-encryption avoidance
  - Empty value handling
  - get_settings/save_settings roundtrip through the DB
  - Machine secret stability
"""

from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class EncryptionTests(unittest.TestCase):
    """Tests for the Fernet-based cross-platform encryption."""

    def setUp(self) -> None:
        # Import from indexer — the module-level initialization makes
        # it safe to call multiple times.
        from golem import indexer as idx

        self.mod = idx

    # ------------------------------------------------------------------
    # Fernet roundtrip
    # ------------------------------------------------------------------

    def test_fernet_protect_unprotect_roundtrip(self) -> None:
        """A value protected with Fernet must be recoverable."""
        if not self.mod._check_fernet():
            self.skipTest("cryptography package not available")
        original = "sk-test-api-key-1234567890"
        protected = self.mod._protect_fernet(original)
        self.assertTrue(protected.startswith("nekrypt:"), f"Bad prefix: {protected[:20]}")
        unprotected = self.mod._unprotect_fernet(protected)
        self.assertEqual(unprotected, original)

    def test_fernet_different_values_produce_different_tokens(self) -> None:
        """Two calls with the same input must produce different ciphertexts
        (Fernet uses random IVs)."""
        if not self.mod._check_fernet():
            self.skipTest("cryptography package not available")
        v1 = self.mod._protect_fernet("same-value")
        v2 = self.mod._protect_fernet("same-value")
        self.assertNotEqual(v1, v2, "Fernet tokens should differ due to random IV")

    def test_fernet_rejects_tampered_ciphertext(self) -> None:
        """Tampering with the ciphertext after protection must raise."""
        if not self.mod._check_fernet():
            self.skipTest("cryptography package not available")
        protected = self.mod._protect_fernet("secret-value")
        payload = protected[len("nekrypt:") :]
        # Corrupt the last few characters
        corrupted = payload[:-1] + ("X" if payload[-1:] != "X" else "Y")
        corrupted_value = "nekrypt:" + corrupted
        with self.assertRaises(RuntimeError):
            self.mod._unprotect_fernet(corrupted_value)

    def test_fernet_handles_empty_string(self) -> None:
        """Empty input must produce an empty output for protect/unprotect."""
        self.assertEqual(self.mod._protect_secret(""), "")
        self.assertEqual(self.mod._unprotect_secret(""), "")

    # ------------------------------------------------------------------
    # Legacy base64 fallback (when cryptography is unavailable)
    # ------------------------------------------------------------------

    def test_fernet_fallback_to_base64(self) -> None:
        """When cryptography is missing, protect must use base64."""
        original = "fallback-key-12345"
        with patch.object(self.mod, "_check_fernet", return_value=False):
            protected = self.mod._protect_fernet(original)
        self.assertTrue(protected.startswith("nekrypt:b64:"))
        # The base64 path must still decode correctly
        unprotected = self.mod._unprotect_fernet(protected)
        self.assertEqual(unprotected, original)

    def test_unprotect_legacy_b64_format(self) -> None:
        """Old base64-encoded secrets under nekrypt:b64: must decode."""
        original = "legacy-key-data"
        b64_part = base64.b64encode(original.encode("utf-8")).decode("ascii")
        protected = "nekrypt:b64:" + b64_part
        unprotected = self.mod._unprotect_fernet(protected)
        self.assertEqual(unprotected, original)

    # ------------------------------------------------------------------
    # _protect_secret / _unprotect_secret integration
    # ------------------------------------------------------------------

    def test_protect_secret_skip_already_protected(self) -> None:
        """Already-encrypted values must pass through unchanged."""
        encrypted = "nekrypt:abc123"
        result = self.mod._protect_secret(encrypted)
        self.assertEqual(result, encrypted)

    def test_protect_secret_skip_dpapi_format(self) -> None:
        """Legacy dpapi: values must pass through unchanged."""
        result = self.mod._protect_secret("dpapi:somedata")
        self.assertEqual(result, "dpapi:somedata")

    def test_unprotect_returns_plaintext_passthrough(self) -> None:
        """Plaintext (unencrypted) values must pass through unchanged."""
        result = self.mod._unprotect_secret("plaintext-key")
        self.assertEqual(result, "plaintext-key")

    # ------------------------------------------------------------------
    # Machine secret stability
    # ------------------------------------------------------------------

    def test_machine_secret_is_deterministic(self) -> None:
        """Repeated calls to _machine_secret must return the same bytes."""
        m1 = self.mod._machine_secret()
        m2 = self.mod._machine_secret()
        self.assertEqual(m1, m2)

    def test_machine_secret_is_256_bits(self) -> None:
        """The machine secret must be 32 bytes (256 bits)."""
        secret = self.mod._machine_secret()
        self.assertEqual(len(secret), 32)

    # ------------------------------------------------------------------
    # Fernet key stability
    # ------------------------------------------------------------------

    def test_fernet_key_is_valid_base64(self) -> None:
        """The Fernet key must be a valid base64-encoded 32-byte value."""
        key = self.mod._get_fernet_key()
        # Fernet keys are base64-encoded 32-byte values (44 chars + padding = 44)
        decoded = base64.urlsafe_b64decode(key)
        self.assertEqual(len(decoded), 32)

    # ------------------------------------------------------------------
    # Full DB roundtrip via encode/decode setting values
    # ------------------------------------------------------------------

    def test_setting_roundtrip_via_db(self) -> None:
        """Encoding a secret, writing it to the DB, and reading it back
        must recover the original value."""
        from golem.indexer import (
            _encode_setting_value,
            get_settings,
            initialize,
        )

        db = Path(tempfile.mkdtemp()) / "test.db"
        conn = initialize(db)
        try:
            original_key = "llm_api_key"
            original_value = "sk-very-secret-value-9876543210"

            # Simulate what save_settings does
            encoded = _encode_setting_value(original_key, original_value)
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?)",
                (original_key, encoded),
            )
            conn.commit()

            # Read back — get_settings must decode
            settings = get_settings(conn)
            self.assertEqual(settings[original_key], original_value)

            # The raw value in the DB must not be plaintext
            raw = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (original_key,)
            ).fetchone()[0]
            self.assertNotEqual(raw, original_value, "Secret stored in plaintext!")
            self.assertTrue(
                raw.startswith("nekrypt:") or raw.startswith("dpapi:"),
                f"Unexpected prefix in stored value: {raw[:20]}",
            )
        finally:
            conn.close()

    def test_save_settings_encrypts_secrets(self) -> None:
        """save_settings must encrypt SECRET_SETTINGS before writing."""
        from golem.indexer import (
            get_settings,
            initialize,
            save_settings,
        )

        db = Path(tempfile.mkdtemp()) / "test2.db"
        conn = initialize(db)
        try:
            settings_dict = {
                "llm_api_key": "my-very-secret-api-key",
                "watched_folder": "C:/watched",
                "terms_accepted": "1",
            }
            save_settings(conn, settings_dict)
            conn.commit()

            # Non-secret fields should be plaintext
            raw = conn.execute(
                "SELECT value FROM settings WHERE key = 'watched_folder'"
            ).fetchone()[0]
            self.assertEqual(raw, "C:/watched")

            # Secret fields must be encrypted
            raw_secret = conn.execute(
                "SELECT value FROM settings WHERE key = 'llm_api_key'"
            ).fetchone()[0]
            self.assertNotEqual(raw_secret, "my-very-secret-api-key")
            self.assertTrue(
                raw_secret.startswith("nekrypt:") or raw_secret.startswith("dpapi:"),
                f"Secret not encrypted: {raw_secret[:30]}",
            )

            # get_settings must decode
            loaded = get_settings(conn)
            self.assertEqual(loaded["llm_api_key"], "my-very-secret-api-key")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
