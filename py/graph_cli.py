# py/graph_cli.py
# ------------------------------------------------------------------
# 손으로 입력한 수식(expr_str)을 이용해 y = f(x) 그래프를 그린 뒤
# PNG 파일로 저장하는 간단한 CLI 스크립트.
#
# 사용 예:
#   py -3.11 graph_cli.py "x**2 + 1" "C:\\temp\\graph.png"
#
# Electron 쪽에서는:
#   - 첫 번째 인자: 문자열 수식 (SymPy가 해석 가능한 Python 표현식)
#   - 두 번째 인자: 출력 이미지 경로
# ------------------------------------------------------------------

import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

def main():
    if len(sys.argv) != 3:
        print("ERROR: usage: graph_cli.py <expr> <out_path>", file=sys.stderr)
        sys.exit(1)

    expr = sys.argv[1]
    out_path = sys.argv[2]

    # math_cli.py 의 main을 호출해서 실제 작업 위임
    try:
        # py 폴더 안에서 실행된다고 가정
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, base_dir)

        from math_cli import main as math_main
    except Exception as e:
        print(f"ERROR: math_cli import 실패: {e}", file=sys.stderr)
        sys.exit(1)

    # math_cli 의 CLI 형식에 맞게 argv 재구성:
    #   math_cli.py graph "<expr>" "<out_path>"
    sys.argv = [sys.argv[0], "graph", expr, out_path]
    math_main()

if __name__ == "__main__":
    main()