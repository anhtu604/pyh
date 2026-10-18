"""Small valid PNGs built without imaging dependencies."""
import struct
import zlib


def png_bytes(width=768, height=768, color_type=6):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    channels = 4 if color_type == 6 else 3
    pixels = (b"\0" + b"\0" * width * channels) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))
