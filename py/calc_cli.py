# py/calc_cli.py
# ------------------------------------------------------------------
# 간단한 수식 계산 CLI 스크립트.
#
# Electron 쪽에서는:
#   - 첫 번째 인자: SymPy가 해석 가능한 문자열 수식
#     (예: "2+3*4", "x^2 + 1" → "x**2 + 1" 형태 등)
#   - 결과는 stdout으로 숫자 형태로 출력된다.
# ------------------------------------------------------------------

import sys
import sympy as sp

def main():
  if len(sys.argv) < 2:
    print("No expression", file=sys.stderr)
    sys.exit(1)

  expr_str = sys.argv[1]

  try:
    # x가 들어간 식이면 x=0 대입, 아니면 그냥 평가
    x = sp.symbols("x")
    expr = sp.sympify(expr_str)
    free = list(expr.free_symbols)

    if len(free) == 0:
      val = expr.evalf()
    else:
      subs = {s: 0 for s in free}  # 단순하게 0 대입
      val = expr.subs(subs).evalf()

    print(val)
  except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
  main()
