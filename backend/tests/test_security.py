"""
Tests for JWT verification logic in app.core.security.

We test the internal _verify_cognito_jwt() function directly using
jose to generate test tokens.  No live Cognito connection is required.
"""
import time
import uuid

import pytest
from jose import jwt
from fastapi import HTTPException

from app.core.security import _verify_cognito_jwt

# ---------------------------------------------------------------------------
# Key material — RSA key pair generated for testing only
# ---------------------------------------------------------------------------
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from jose import jwk as jose_jwk

TEST_REGION = "ap-southeast-7"
TEST_POOL_ID = "ap-southeast-7_TestPool"
TEST_CLIENT_ID = "testclientid123"
TEST_ISS = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_POOL_ID}"
TEST_KID = "test-key-1"

# Generate an RSA key pair once for the test session
_private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend(),
)
_public_key = _private_key.public_key()

from cryptography.hazmat.primitives import serialization

_private_pem = _private_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption(),
).decode()

_public_pem = _public_key.public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

# Build a fake JWKS entry using the public key
_jwk_key = jose_jwk.construct(_public_pem, algorithm="RS256").to_dict()
_jwk_key["kid"] = TEST_KID
_jwk_key["use"] = "sig"

FAKE_JWKS = {TEST_KID: _jwk_key}


def _make_token(
    sub: str | None = None,
    iss: str = TEST_ISS,
    token_use: str = "access",
    exp_offset: int = 3600,
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub or str(uuid.uuid4()),
        "iss": iss,
        "token_use": token_use,
        "iat": now,
        "exp": now + exp_offset,
    }
    return jwt.encode(payload, _private_pem, algorithm="RS256", headers={"kid": TEST_KID})


# ---------------------------------------------------------------------------
# Monkeypatch settings so verify_cognito_jwt uses our test values
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    import app.core.security as sec_module
    monkeypatch.setattr(sec_module.settings, "aws_region", TEST_REGION)
    monkeypatch.setattr(sec_module.settings, "cognito_user_pool_id", TEST_POOL_ID)
    monkeypatch.setattr(sec_module.settings, "cognito_app_client_id", TEST_CLIENT_ID)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_valid_token_returns_payload():
    sub = str(uuid.uuid4())
    token = _make_token(sub=sub)
    payload = _verify_cognito_jwt(token, FAKE_JWKS)
    assert payload["sub"] == sub
    assert payload["token_use"] == "access"


def test_expired_token_raises_401():
    token = _make_token(exp_offset=-10)  # expired 10 seconds ago
    with pytest.raises(HTTPException) as exc_info:
        _verify_cognito_jwt(token, FAKE_JWKS)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_wrong_issuer_raises_401():
    token = _make_token(iss="https://accounts.google.com")
    with pytest.raises(HTTPException) as exc_info:
        _verify_cognito_jwt(token, FAKE_JWKS)
    assert exc_info.value.status_code == 401
    assert "issuer" in exc_info.value.detail.lower()


def test_wrong_token_use_raises_401():
    token = _make_token(token_use="id")
    with pytest.raises(HTTPException) as exc_info:
        _verify_cognito_jwt(token, FAKE_JWKS)
    assert exc_info.value.status_code == 401


def test_unknown_kid_raises_401():
    token = _make_token()
    with pytest.raises(HTTPException) as exc_info:
        _verify_cognito_jwt(token, {})  # empty JWKS — kid not found
    assert exc_info.value.status_code == 401


def test_malformed_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        _verify_cognito_jwt("not.a.jwt", FAKE_JWKS)
    assert exc_info.value.status_code == 401
