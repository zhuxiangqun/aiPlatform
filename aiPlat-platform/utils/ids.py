import secrets
import time

# Crockford's Base32 alphabet (no I, L, O, U)
_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_crockford32(value: int, length: int) -> str:
    """Encode non-negative int to fixed-length Crockford base32."""
    if value < 0:
        raise ValueError("value must be non-negative")
    out = []
    for _ in range(length):
        out.append(_CROCKFORD32[value & 0x1F])
        value >>= 5
    if value:
        raise ValueError("value too large to encode in requested length")
    return "".join(reversed(out))


def new_ulid() -> str:
    """Generate a ULID (26 chars, uppercase, time-sortable)."""
    ts_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = secrets.randbits(80)
    return _encode_crockford32(ts_ms, 10) + _encode_crockford32(rand, 16)


def new_prefixed_id(prefix: str) -> str:
    """Generate a stable prefixed id like 'req_<ulid>'."""
    prefix = (prefix or "").strip().rstrip("_")
    return f"{prefix}_{new_ulid()}"

