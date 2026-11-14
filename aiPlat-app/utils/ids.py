"""ids：模块接口。"""

import secrets
import time

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_crockford32(value: int, length: int) -> str:
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
    """new_ulid。
    """
    ts_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = secrets.randbits(80)
    return _encode_crockford32(ts_ms, 10) + _encode_crockford32(rand, 16)


def new_prefixed_id(prefix: str) -> str:
    """new_prefixed_id。

    Args:
        prefix: prefix 参数。
    """
    prefix = (prefix or "").strip().rstrip("_")
    return f"{prefix}_{new_ulid()}"

