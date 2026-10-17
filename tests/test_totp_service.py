from app.services.totp_service import current_otp, normalize_secret


def test_totp_rfc6238_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert current_otp(secret, 59) == ("287082", 1)


def test_otpauth_uri_is_supported():
    uri = "otpauth://totp/demo?secret=gezd%20gnbv%20gy3t%20qojq"
    assert normalize_secret(uri) == "GEZDGNBVGY3TQOJQ"
