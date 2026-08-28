import os
import stat

import pytest

from app.services import secret_store
from app.services.secret_store import protect_secret, unprotect_secret


def test_empty_secret_stays_empty():
    assert protect_secret("") == ""
    assert unprotect_secret("") == ""


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI product path")
def test_windows_secret_is_encrypted_and_round_trips():
    secret = "fastread-test-secret-not-a-real-key"

    protected = protect_secret(secret)

    assert protected.startswith("dpapi:v1:")
    assert secret not in protected
    assert unprotect_secret(protected) == secret


def test_legacy_plaintext_secret_remains_readable_for_migration():
    assert unprotect_secret("legacy-key") == "legacy-key"


def test_non_windows_file_key_encryption_round_trips(monkeypatch, tmp_path):
    key_path = tmp_path / "provider-secret.key"
    secret = "portable-test-secret-not-a-real-key"
    monkeypatch.setattr(secret_store, "_is_windows_dpapi", lambda: False)
    monkeypatch.setattr(secret_store, "_file_key_path", lambda: key_path)

    protected = protect_secret(secret)

    assert protected.startswith("filekey:v1:")
    assert secret not in protected
    assert key_path.read_bytes() != secret.encode("utf-8")
    assert len(key_path.read_bytes()) == 32
    assert unprotect_secret(protected) == secret


def test_non_windows_file_key_encryption_rejects_tampering(monkeypatch, tmp_path):
    monkeypatch.setattr(secret_store, "_is_windows_dpapi", lambda: False)
    monkeypatch.setattr(
        secret_store,
        "_file_key_path",
        lambda: tmp_path / "provider-secret.key",
    )
    protected = protect_secret("tamper-test-secret")
    tamper_at = len("filekey:v1:") + 8
    replacement = "A" if protected[tamper_at] != "A" else "B"
    tampered = protected[:tamper_at] + replacement + protected[tamper_at + 1:]

    with pytest.raises(ValueError):
        unprotect_secret(tampered)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_non_windows_file_key_permissions_are_owner_only(monkeypatch, tmp_path):
    key_path = tmp_path / "provider-secret.key"
    monkeypatch.setattr(secret_store, "_is_windows_dpapi", lambda: False)
    monkeypatch.setattr(secret_store, "_file_key_path", lambda: key_path)

    protect_secret("permission-test-secret")

    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
