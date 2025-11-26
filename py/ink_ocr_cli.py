# py/ink_ocr_cli.py
"""
Electron에서 호출하는 InkOCR 래퍼 (전처리 포함 버전)

- Electron이 캡처한 이미지를 InkOCR에 던져서
  텍스트 / 수식 OCR 수행.
- Tk 버전에서 사용하던 nonwhite_crop 전처리를 추가해서
  흰 배경 + 잉크 부분만 타이트하게 자르고 이진화한 뒤 OCR에 넘긴다.
"""

import sys
import os
from PIL import Image

try:
    # InkOCR.py 안의 OCR 함수 + 전처리 함수 사용
    from InkOCR import ocr_text_google, ocr_formula_simpletex, nonwhite_crop
except Exception as e:
    print(f"ERROR: InkOCR 모듈 import 실패: {e}", file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) < 3:
        print("Usage: ink_ocr_cli.py [text|math] image_path", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]      # "text" or "math"
    image_path = sys.argv[2]

    if mode not in ("text", "math"):
        print("mode must be 'text' or 'math'", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(image_path):
        print(f"image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    # 1) 캡처 이미지 열기
    try:
        raw = Image.open(image_path)
    except Exception as e:
        print(f"이미지 열기 실패: {e}", file=sys.stderr)
        sys.exit(1)

    # 2) 배경을 흰색으로 맞추기 (TkInk와 비슷하게)
    if raw.mode == "RGBA":
        bg = Image.new("RGB", raw.size, (255, 255, 255))
        bg.paste(raw, mask=raw.split()[3])  # 알파 기준 합성
        img = bg
    else:
        img = raw.convert("RGB")

    # 2.5) nonwhite_crop 전처리: 잉크 있는 부분만 타이트하게 자르고 이진화
    try:
        cropped = nonwhite_crop(img)
    except Exception as e:
        # 전처리 실패해도 OCR은 계속 진행
        print(f"nonwhite_crop 실패, 원본으로 진행: {e}", file=sys.stderr)
        cropped = None

    # crop 성공했으면 그 이미지를, 아니면 원본 이미지를 사용
    img_for_ocr = cropped if cropped is not None else img

    # 3) 모드에 따라 각각 OCR 호출
    try:
        if mode == "text":
            # 텍스트는 흑백이미지 넘겨주기
            pil_input = img_for_ocr.convert("L")
            result = ocr_text_google(pil_input)
        else:  # "math"
            # 수식은 nonwhite_crop 결과(또는 원본)를 그대로 넘긴다
            pil_input = img_for_ocr
            result = ocr_formula_simpletex(pil_input)
    except Exception as e:
        print(f"OCR 처리 중 오류: {e}", file=sys.stderr)
        sys.exit(1)

    if result is None:
        result = ""

    # Electron은 stdout을 그대로 읽어간다
    out = (str(result) + "\n").encode("utf-8", errors="replace")
    sys.stdout.buffer.write(out)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
