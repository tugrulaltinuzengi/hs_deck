"""Characterisation tests for the vendored varint codec.

hsdeck does not implement LEB128 itself - these pin the behaviour of the
vendored reference implementation that it relies on, so a vendor refresh that
changed the encoding would be caught here rather than in a deckstring nobody
can import.
"""

from io import BytesIO

import pytest

from hsdeck._vendor.hearthstone.deckstrings import _read_varint, _write_varint


def roundtrip(value: int) -> int:
    buf = BytesIO()
    _write_varint(buf, value)
    buf.seek(0)
    return _read_varint(buf)


@pytest.mark.parametrize(
    "value", [0, 1, 2, 127, 128, 129, 255, 300, 16383, 16384, 813, 127065, 2**31]
)
def test_roundtrip(value):
    assert roundtrip(value) == value


@pytest.mark.parametrize(
    "value,encoded",
    [
        (0, b"\x00"),
        (1, b"\x01"),
        (127, b"\x7f"),
        (128, b"\x80\x01"),
        (300, b"\xac\x02"),
        (813, b"\xad\x06"),  # the Priest hero - the "a0G" in AAECAa0G...
    ],
)
def test_known_encodings(value, encoded):
    buf = BytesIO()
    _write_varint(buf, value)
    assert buf.getvalue() == encoded


def test_continuation_bit_marks_every_byte_but_the_last():
    buf = BytesIO()
    _write_varint(buf, 300_000)
    raw = buf.getvalue()
    assert all(byte & 0x80 for byte in raw[:-1])
    assert not raw[-1] & 0x80


def test_truncated_stream_raises():
    """Upstream signals a short buffer by failing to read; the type is its own
    business, which is why hsdeck.deckstring catches broadly."""
    with pytest.raises((EOFError, TypeError)):
        _read_varint(BytesIO(b"\x80"))
