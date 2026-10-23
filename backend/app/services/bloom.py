"""A Bloom filter with pluggable bit storage (in-process bytes, or a Redis string shared by all replicas).

A Bloom filter answers "have I seen this value?" with either *definitely not* or *maybe*: no false
negatives, a tunable rate of false positives, constant memory (~117 KB for 100k values at 1%).
We use it to answer "is this name free?" without touching the database for the common case.

Bit layout is the same in both stores: bit i is the (7 - i % 8)-th bit of byte i // 8, which is
how Redis SETBIT/GETBIT number bits, so a filter built in memory can be uploaded to Redis as-is.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from typing import Protocol


def optimal_size(capacity: int, error_rate: float) -> tuple[int, int]:
    """(bits m, hash count k) for `capacity` items at false-positive probability `error_rate`."""
    m = math.ceil(-capacity * math.log(error_rate) / (math.log(2) ** 2))
    k = max(1, round(m / capacity * math.log(2)))
    return m, k


def _pack(bits: int, positions: Iterable[int]) -> bytearray:
    buf = bytearray((bits + 7) // 8)
    for p in positions:
        buf[p >> 3] |= 0x80 >> (p & 7)
    return buf


class BitStore(Protocol):
    def set_bits(self, positions: list[int]) -> None: ...
    def all_set(self, positions: list[int]) -> bool: ...
    def replace(self, packed: bytes) -> None: ...


class MemoryBits:
    def __init__(self, bits: int):
        self._buf = bytearray((bits + 7) // 8)

    def set_bits(self, positions: list[int]) -> None:
        for p in positions:
            self._buf[p >> 3] |= 0x80 >> (p & 7)

    def all_set(self, positions: list[int]) -> bool:
        return all(self._buf[p >> 3] & (0x80 >> (p & 7)) for p in positions)

    def replace(self, packed: bytes) -> None:
        self._buf = bytearray(packed)


class RedisBits:
    """Bits in one Redis string: every API replica (and worker) sees the same filter."""

    def __init__(self, client_factory, key: str):
        self._client = client_factory
        self.key = key

    def set_bits(self, positions: list[int]) -> None:
        r = self._client()
        try:
            pipe = r.pipeline(transaction=False)
            for p in positions:
                pipe.setbit(self.key, p, 1)
            pipe.execute()
        finally:
            r.close()

    def all_set(self, positions: list[int]) -> bool:
        r = self._client()
        try:
            pipe = r.pipeline(transaction=False)
            for p in positions:
                pipe.getbit(self.key, p)
            return all(pipe.execute())
        finally:
            r.close()

    def replace(self, packed: bytes) -> None:
        # Build under a temporary key, then RENAME (atomic): readers never see a half-built filter.
        r = self._client()
        try:
            tmp = f"{self.key}:rebuild"
            r.set(tmp, bytes(packed))
            r.rename(tmp, self.key)
        finally:
            r.close()


class BloomFilter:
    def __init__(self, store_factory, capacity: int = 100_000, error_rate: float = 0.01):
        self.bits, self.hashes = optimal_size(capacity, error_rate)
        self.capacity, self.error_rate = capacity, error_rate
        self.store: BitStore = store_factory(self.bits)

    def _positions(self, item: str) -> list[int]:
        # Kirsch-Mitzenmacher double hashing: k positions from two 64-bit halves of one digest.
        d = hashlib.blake2b(item.encode(), digest_size=16).digest()
        h1 = int.from_bytes(d[:8], "big")
        h2 = int.from_bytes(d[8:], "big") | 1
        return [(h1 + i * h2) % self.bits for i in range(self.hashes)]

    def add(self, item: str) -> None:
        self.store.set_bits(self._positions(item))

    def might_contain(self, item: str) -> bool:
        return self.store.all_set(self._positions(item))

    def rebuild(self, items: Iterable[str]) -> int:
        """Replace the whole filter with exactly `items` (drops values deleted from the database)."""
        count, positions = 0, []
        for item in items:
            positions.extend(self._positions(item))
            count += 1
        self.store.replace(_pack(self.bits, positions))
        return count
