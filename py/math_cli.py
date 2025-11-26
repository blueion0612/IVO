# py/math_cli.py
import sys
import os

# 한글 안 깨지게
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

try:
    # InkOCR 안의 공용 함수 재사용
    from InkOCR import (
        calc_from_latex,
        plot_from_latex,
        solve_system_from_latex_list,  # 새로 추가한 함수
    )
except ImportError:
    # 구버전 InkOCR 를 쓰고 있을 수도 있으니, 안전하게 처리
    try:
        from InkOCR import calc_from_latex, plot_from_latex  # type: ignore
        solve_system_from_latex_list = None  # type: ignore
    except Exception as e:
        print(f"ERROR: InkOCR import 실패: {e}", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"ERROR: InkOCR import 실패: {e}", file=sys.stderr)
    sys.exit(1)


def main():
    """
    사용법 (Electron / CLI 공통):

      1) 단일 수식 계산
         py -3.11 math_cli.py calc "<latex_or_expr>"

      2) 그래프
         py -3.11 math_cli.py graph "<latex_or_expr>" "C:\\temp\\graph.png"

      3) 연립방정식 (여러 줄)
         py -3.11 math_cli.py system "x^2 + y = 1\nx - y = 2"

         ※ Electron 쪽에서는 여러 식을 '\n'으로 이어붙여서 하나의 인자로 넘기면 됨.
    """

    if len(sys.argv) < 3:
        print(
            "ERROR: usage: math_cli.py <calc|graph|system> <expr_or_lines> [out_path]",
            file=sys.stderr,
        )
        sys.exit(1)

    mode = sys.argv[1]
    expr_or_lines = sys.argv[2]

    # ------------------------------------------------------------------
    # 1) '=' 계산 (단일 수식)
    # ------------------------------------------------------------------
    if mode == "calc":
        try:
            result = calc_from_latex(expr_or_lines)
        except Exception as e:
            print(f"ERROR: calc_from_latex 실패: {e}", file=sys.stderr)
            sys.exit(1)

        out = (str(result) + "\n").encode("utf-8", errors="replace")
        sys.stdout.buffer.write(out)
        sys.stdout.flush()
        sys.exit(0)

    # ------------------------------------------------------------------
    # 2) 그래프
    # ------------------------------------------------------------------
    if mode == "graph":
        if len(sys.argv) >= 4:
            out_path = sys.argv[3]
        else:
            # 기본 경로 (필요하면 Electron 쪽에서 항상 3번째 인자를 주도록 해도 됨)
            out_path = os.path.join(os.getcwd(), "graph.png")

        try:
            # InkOCR 의 plot_from_latex 이용 (LaTeX/ASCII 모두 지원)
            pil_img, err = plot_from_latex(expr_or_lines, x_range=(-10, 10))
        except Exception as e:
            print(f"ERROR: plot_from_latex 실패: {e}", file=sys.stderr)
            sys.exit(1)

        if pil_img is None:
            print(f"ERROR: {err or '알 수 없는 오류'}", file=sys.stderr)
            sys.exit(1)

        # PNG로 저장
        try:
            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            pil_img.save(out_path, format="PNG")
        except Exception as e:
            print(f"ERROR: 그래프 이미지 저장 실패: {e}", file=sys.stderr)
            sys.exit(1)

        # stdout 으로 경로 전달
        out = (out_path + "\n").encode("utf-8", errors="replace")
        sys.stdout.buffer.write(out)
        sys.stdout.flush()
        sys.exit(0)

    # ------------------------------------------------------------------
    # 3) 연립 방정식 (여러 줄) - "메모리"에 쌓인 수식들을 한 번에
    # ------------------------------------------------------------------
    if mode == "system":
        if solve_system_from_latex_list is None:
            print(
                "ERROR: solve_system_from_latex_list 가 InkOCR에 없습니다. "
                "InkOCR.py 를 먼저 업데이트 해주세요.",
                file=sys.stderr,
            )
            sys.exit(1)

        # expr_or_lines 안에 여러 줄이 '\n' 으로 들어온다고 가정
        lines = [line for line in expr_or_lines.splitlines() if line.strip()]

        if not lines:
            print("ERROR: 비어 있는 식 목록입니다.", file=sys.stderr)
            sys.exit(1)

        try:
            text = solve_system_from_latex_list(lines)  # type: ignore
        except Exception as e:
            print(f"ERROR: 연립방정식 계산 중 오류: {e}", file=sys.stderr)
            sys.exit(1)

        out = (str(text) + "\n").encode("utf-8", errors="replace")
        sys.stdout.buffer.write(out)
        sys.stdout.flush()
        sys.exit(0)

    # ------------------------------------------------------------------
    # 잘못된 mode
    # ------------------------------------------------------------------
    print("ERROR: mode must be 'calc' or 'graph' or 'system'", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
