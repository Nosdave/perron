"""Convert an image into Perron push_image parts (RGB565 little endian, base64, 8 KB raw each).

  python tools/rgb565_chunks.py picture.png [192x64]   -> one base64 part per line

Home Assistant: run it via shell_command and send each line with esphome.<board>_push_image
(seq = line index, total = number of lines). Requires Pillow.
"""
import base64
import sys

from PIL import Image

CHUNK = 8192


def parts(path, size=(192, 64)):
    im = Image.open(path).convert("RGB")
    im.thumbnail(size, Image.NEAREST)
    raw = bytearray()
    px = im.tobytes()
    for i in range(0, len(px), 3):
        r, g, b = px[i], px[i + 1], px[i + 2]
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        raw += v.to_bytes(2, "little")
    return im.size, [base64.b64encode(raw[i:i + CHUNK]).decode() for i in range(0, len(raw), CHUNK)]


if __name__ == "__main__":
    size = tuple(int(x) for x in sys.argv[2].split("x")) if len(sys.argv) > 2 else (192, 64)
    (w, h), ps = parts(sys.argv[1], size)
    print(f"# {w}x{h} {len(ps)} parts", file=sys.stderr)
    print("\n".join(ps))
