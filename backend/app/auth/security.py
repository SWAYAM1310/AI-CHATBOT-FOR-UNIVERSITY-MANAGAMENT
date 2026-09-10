"""Password hashing compatible with the synthetic dataset.

The generator stores Django-style `pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>`
(see scripts/generate_synthetic_data.py). New hashes use a random salt.
"""
from __future__ import annotations

import hashlib
import hmac
import os

_ALGO = "pbkdf2_sha256"
_ITERS = 100_000


def hash_password(password: str, *, iterations: int = _ITERS) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{_ALGO}${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
    except ValueError:
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)
