from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import os
import secrets
import stat
from pathlib import Path

from app.core.settings import get_settings


_PREFIX = "dpapi:v1:"
_FILE_PREFIX = "filekey:v1:"
_FILE_KEY_BYTES = 32
_FILE_NONCE_BYTES = 12
_FILE_AAD = b"FastRead provider secret filekey v1"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _dpapi_protect(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        "FastRead provider secret",
        None,
        None,
        None,
        0,
        ctypes.byref(output),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)
        _ = source_buffer


def _dpapi_unprotect(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)
        _ = source_buffer


def _is_windows_dpapi() -> bool:
    return os.name == "nt"


def _file_key_path() -> Path:
    return get_settings().data_root / "provider-secret.key"


def _restrict_key_permissions(path: Path) -> None:
    if os.name != "nt":
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _load_or_create_file_key() -> bytes:
    """Load the local file key used where no OS credential API is available.

    This is intentionally described as a permission-restricted local key file,
    not as an OS keyring. Keeping it under FASTREAD_DATA_ROOT makes a complete
    product-data backup portable while keeping the SQLite value non-plaintext.
    """
    path = _file_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(_FILE_KEY_BYTES)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)
    except FileExistsError:
        pass
    else:
        try:
            written = os.write(fd, key)
            if written != len(key):
                raise OSError("provider secret key write was incomplete")
            os.fsync(fd)
        finally:
            os.close(fd)
        _restrict_key_permissions(path)

    stored = path.read_bytes()
    if len(stored) != _FILE_KEY_BYTES:
        raise RuntimeError("provider-secret.key 无效；必须是 32 字节本地密钥")
    _restrict_key_permissions(path)
    return stored


def _file_protect(data: bytes) -> bytes:
    from Cryptodome.Cipher import AES

    nonce = secrets.token_bytes(_FILE_NONCE_BYTES)
    cipher = AES.new(_load_or_create_file_key(), AES.MODE_GCM, nonce=nonce, mac_len=16)
    cipher.update(_FILE_AAD)
    encrypted, tag = cipher.encrypt_and_digest(data)
    return nonce + tag + encrypted


def _file_unprotect(data: bytes) -> bytes:
    from Cryptodome.Cipher import AES

    if len(data) < _FILE_NONCE_BYTES + 16:
        raise ValueError("filekey secret payload is truncated")
    nonce = data[:_FILE_NONCE_BYTES]
    tag = data[_FILE_NONCE_BYTES:_FILE_NONCE_BYTES + 16]
    encrypted = data[_FILE_NONCE_BYTES + 16:]
    cipher = AES.new(_load_or_create_file_key(), AES.MODE_GCM, nonce=nonce, mac_len=16)
    cipher.update(_FILE_AAD)
    return cipher.decrypt_and_verify(encrypted, tag)


def protect_secret(value: str) -> str:
    value = str(value or "")
    if not value or value.startswith((_PREFIX, _FILE_PREFIX)):
        return value
    if _is_windows_dpapi():
        encrypted = _dpapi_protect(value.encode("utf-8"))
        return _PREFIX + base64.b64encode(encrypted).decode("ascii")
    encrypted = _file_protect(value.encode("utf-8"))
    return _FILE_PREFIX + base64.b64encode(encrypted).decode("ascii")


def unprotect_secret(value: str) -> str:
    value = str(value or "")
    if value.startswith(_FILE_PREFIX):
        encoded = value[len(_FILE_PREFIX):]
        encrypted = base64.b64decode(encoded, validate=True)
        return _file_unprotect(encrypted).decode("utf-8")
    if not value.startswith(_PREFIX):
        return value
    if not _is_windows_dpapi():
        raise RuntimeError("该 API Key 由 Windows DPAPI 保护，无法在当前系统解密")
    encoded = value[len(_PREFIX):]
    encrypted = base64.b64decode(encoded, validate=True)
    return _dpapi_unprotect(encrypted).decode("utf-8")
