"""Unsigned LEB128 varints - the integer encoding used by deckstrings."""

from __future__ import annotations

from typing import BinaryIO


def write_varint(stream: BinaryIO, value: int) -> int:
    if value < 0:
        raise ValueError("varints are unsigned")
    buf = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value:
            buf.append(chunk | 0x80)
        else:
            buf.append(chunk)
            break
    return stream.write(bytes(buf))


def read_varint(stream: BinaryIO) -> int:
    shift = 0
    result = 0
    while True:
        byte = stream.read(1)
        if not byte:
            raise EOFError("unexpected end of stream while reading a varint")
        value = byte[0]
        result |= (value & 0x7F) << shift
        shift += 7
        if not value & 0x80:
            return result
