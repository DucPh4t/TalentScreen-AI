"""Security primitives: Argon2id password hashing, secure tokens, and hashing utilities."""
from __future__ import annotations

import hashlib
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Argon2id password hasher with parameters balanced for security and latency
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against Argon2id hash."""
    try:
        return _hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def generate_secure_token(nbytes: int = 32) -> str:
    """Generate cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> bytes:
    """Compute SHA-256 byte digest of token for database lookup."""
    return hashlib.sha256(token.encode("utf-8")).digest()
