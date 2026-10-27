#!/usr/bin/env python3
"""Measure the synthetic panels in an unmodified workspace screenshot."""

import argparse
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screenshot")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--expect-foreign", choices=("visible", "missing"), default="visible")
    args = parser.parse_args()
    pixels = subprocess.check_output(
        [args.ffmpeg, "-v", "error", "-i", args.screenshot,
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    )
    if len(pixels) % 3:
        raise RuntimeError("incomplete RGB frame")
    green = blue = 0
    for pixel in zip(pixels[0::3], pixels[1::3], pixels[2::3]):
        green += pixel == (30, 180, 70)
        blue += pixel == (40, 100, 220)
    # Each opaque panel is 270x180 before any compositor scaling. Leave room
    # for text and window clipping, but reject small unrelated coloured icons.
    print(f"same-process green pixels: {green}; foreign-process blue pixels: {blue}")
    return 0 if green >= 40000 and (blue >= 40000) == (args.expect_foreign == "visible") else 1


if __name__ == "__main__":
    raise SystemExit(main())
