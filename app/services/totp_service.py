import base64
import binascii
import hashlib
import hmac
import time
from urllib.parse import parse_qs, urlparse


def normalize_secret(value: str) -> str:
    value = value.strip()
    if value.lower().startswith("otpauth://"):
        value = parse_qs(urlparse(value).query).get("secret", [""])[0]
    return "".join(value.upper().split()).rstrip("=")


def validate_secret(value: str) -> str:
    secret = normalize_secret(value)
    if not secret:
        raise ValueError("Vui lòng nhập 2FA Secret.")
    try:
        base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    except (binascii.Error, ValueError):
        raise ValueError("2FA Secret không hợp lệ. Hãy nhập secret Base32 hoặc otpauth URI.")
    return secret


def current_otp(secret: str, timestamp: float | None = None) -> tuple[str, int]:
    secret = validate_secret(secret)
    now = time.time() if timestamp is None else timestamp
    counter = int(now // 30)
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}", 30 - int(now % 30)
