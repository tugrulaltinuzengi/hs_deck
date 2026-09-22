from io import BytesIO

import pytest

from hsdeck.varint import read_varint, write_varint


def roundtrip(value: int) -> int:
    buf = BytesIO()
    write_varint(buf, value)
    buf.seek(0)
    return read_varint(buf)


@pytest.mark.parametrize("value", [0, 1, 2, 127, 128, 129, 255, 300, 16383, 16384, 813, 127065, 2**31])
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
        (813, b"\xad\x06"),  # the Priest hero, the "a0G" in AAECAa0G...
    ],
)
def test_known_encodings(value, encoded):
    buf = BytesIO()
    write_varint(buf, value)
    assert buf.getvalue() == encoded


def test_negative_rejected():
    with pytest.raises(ValueError):
        write_varint(BytesIO(), -1)


def test_truncated_stream():
    with pytest.raises(EOFError):
        read_varint(BytesIO(b"\x80"))
