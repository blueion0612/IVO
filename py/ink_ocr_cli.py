#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
InkOCR CLI - OCR Command Line Interface for Electron

Wrapper script for InkOCR module, providing CLI interface for Electron integration.
Performs text or math OCR on captured images with preprocessing.

Usage:
    python ink_ocr_cli.py text image_path
    python ink_ocr_cli.py math image_path
"""

import sys
import os
from PIL import Image

try:
    from InkOCR import ocr_text_google, ocr_formula_simpletex, nonwhite_crop
except Exception as e:
    print(f"ERROR: Failed to import InkOCR module: {e}", file=sys.stderr)
    sys.exit(1)


def main():
    """Main entry point for OCR CLI."""
    if len(sys.argv) < 3:
        print("Usage: ink_ocr_cli.py [text|math] image_path", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]
    image_path = sys.argv[2]

    if mode not in ("text", "math"):
        print("Mode must be 'text' or 'math'", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    # Load image
    try:
        raw = Image.open(image_path)
    except Exception as e:
        print(f"Failed to open image: {e}", file=sys.stderr)
        sys.exit(1)

    # Convert to RGB with white background
    if raw.mode == "RGBA":
        bg = Image.new("RGB", raw.size, (255, 255, 255))
        bg.paste(raw, mask=raw.split()[3])
        img = bg
    else:
        img = raw.convert("RGB")

    # Crop to ink region and binarize
    try:
        cropped = nonwhite_crop(img)
    except Exception as e:
        print(f"Preprocessing failed, using original: {e}", file=sys.stderr)
        cropped = None

    img_for_ocr = cropped if cropped is not None else img

    # Perform OCR
    try:
        if mode == "text":
            pil_input = img_for_ocr.convert("L")
            result = ocr_text_google(pil_input)
        else:
            pil_input = img_for_ocr
            result = ocr_formula_simpletex(pil_input)
    except Exception as e:
        print(f"OCR error: {e}", file=sys.stderr)
        sys.exit(1)

    if result is None:
        result = ""

    # Output result to stdout for Electron
    out = (str(result) + "\n").encode("utf-8", errors="replace")
    sys.stdout.buffer.write(out)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
