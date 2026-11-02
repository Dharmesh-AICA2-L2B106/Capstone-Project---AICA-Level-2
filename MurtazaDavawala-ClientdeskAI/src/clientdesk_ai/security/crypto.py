"""Security and cryptographic operations for password hashing, masking, authentication, and file integrity."""

import hashlib
import hmac
import re
import secrets
from pathlib import Path
from typing import Optional, Tuple

# OWASP Recommended standards for PBKDF2-HMAC-SHA256
PBKDF2_ITERATIONS = 600_000
PBKDF2_MIN_ITERATIONS = 600_000      # Strict downgrade floor: never accept weaker hashes
PBKDF2_MAX_ITERATIONS = 1_200_000    # DoS ceiling
SALT_BYTES = 16
HASH_BYTES = 32
MAX_PASSWORD_CHARS = 1024
LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Hash a password securely using PBKDF2-HMAC-SHA256 with a unique cryptographic salt."""
    if not password or len(password) > MAX_PASSWORD_CHARS:
        raise ValueError("Password length out of bounds")
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${key.hex()}"


def _parse_hash(hashed: str) -> Optional[Tuple[int, bytes, bytes]]:
    """Parse and validate stored password hash structure."""
    if not hashed:
        return None
    parts = hashed.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return None
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
        if len(salt) < SALT_BYTES or len(expected) != HASH_BYTES:
            return None
        return iterations, salt, expected
    except (ValueError, TypeError):
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored hash in constant time, rejecting iteration downgrades and short salts."""
    if not plain_password or not hashed_password:
        return False
    parsed = _parse_hash(hashed_password)
    if not parsed:
        return False
    iterations, salt, expected_hash = parsed
    if not (PBKDF2_MIN_ITERATIONS <= iterations <= PBKDF2_MAX_ITERATIONS):
        return False
    try:
        computed_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(expected_hash, computed_hash)
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """Check if stored hash is below current security iteration standard."""
    parsed = _parse_hash(hashed)
    if not parsed:
        return True
    iterations, _, _ = parsed
    return iterations < PBKDF2_ITERATIONS


def generate_session_token() -> str:
    """Generate a high-entropy session token."""
    return secrets.token_urlsafe(32)


def compute_file_sha256(file_path: Path) -> str:
    """Compute the lowercase SHA-256 hash of a file for duplicate detection and tamper proofing."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest().lower()


def mask_pan(pan: Optional[str]) -> str:
    """Mask a 10-character Indian PAN for privacy (e.g. ABCDE1234F -> AB*******F). Masks 7 out of 10 chars."""
    if not pan:
        return ""
    clean = pan.strip().upper()
    if len(clean) == 10:
        return f"{clean[:2]}*******{clean[-1]}"
    return "****"


def mask_gstin(gstin: Optional[str]) -> str:
    """Mask a 15-character Indian GSTIN for privacy.
    Shows ONLY the state code (pos 1-2) and the last 3 chars (entity no., 'Z', checksum).
    Positions 3-12 (the embedded PAN) are completely obscured with 10 asterisks.
    Example: 27ABCDE1234F1Z5 -> 27**********1Z5  (total length 15: 2 + 10 + 3)
    """
    if not gstin:
        return ""
    clean = gstin.strip().upper()
    if len(clean) == 15:
        return f"{clean[:2]}{'*' * 10}{clean[-3:]}"
    return "****"


def mask_aadhaar(aadhaar: Optional[str]) -> str:
    """Mask a 12-digit Indian Aadhaar number for statutory privacy compliance (UIDAI standard: masks first 8 digits).
    Example: 123456789012 or 1234 5678 9012 -> ********9012 (or ****-****-9012).
    """
    if not aadhaar:
        return ""
    clean = re.sub(r'[\s\-]', '', aadhaar.strip())
    if len(clean) == 12:
        return f"********{clean[-4:]}"
    elif len(clean) > 4:
        return f"{'*' * (len(clean) - 4)}{clean[-4:]}"
    return "****"
