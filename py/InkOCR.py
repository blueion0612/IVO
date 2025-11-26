"""
TkInk OCR (SimpleTex · 키보드 인식 · 투명창 · 계산/그래프)
- 좌클릭=문자(검정, Google Vision 선택)
- 우클릭=수식(파랑, SimpleTex LaTeX)
- Space: OCR 실행
- c: 초기화, q: 종료
- t: LaTeX 오버레이 표시
- g: 그래프(y=f(x)) 표시
- =: 계산(정적분/등식 해 등)
- e/E: 열린 모든 오버레이 창 닫기
"""

import os, io, threading, hashlib, random, string, datetime
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageTk, ImageFont, ImageChops
import re


# ---- 디버그 플래그: 파서 경로/오류 콘솔 출력 -----------------------------------
DEBUG_PARSER = False

# ---- HTTP dep ----------------------------------------------------------------
try:
    import requests
except Exception:
    requests = None

# ---- Plot --------------------------------------------------------------------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---- SymPy (전역 parse_latex 바인딩 금지: 안전 로더 사용) -----------------------
try:
    import sympy as sp
except Exception:
    sp = None

try:
    from importlib.metadata import version as _pkg_version
except Exception:  # py<3.8
    from importlib_metadata import version as _pkg_version  # type: ignore

# ---- App config --------------------------------------------------------------
W, H = 980, 460
RESULT_ROWS = 9
PEN_WIDTH = 6
COLOR_TEXT = (0, 0, 0)
COLOR_FORM = (0, 0, 255)

SIMPLETEX_USE_TURBO = True
SIMPLETEX_TIMEOUT   = 30
SIMPLETEX_DOMAIN    = "https://server.simpletex.net"

# --- 그래프 크기(작게) ---
GRAPH_FIGSIZE = (3.2, 2.2)   # 인치 (가로, 세로)
GRAPH_DPI     = 140          # 픽셀 밀도

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\NanumGothic.ttf",
    r"C:\Windows\Fonts\NotoSansKR-Regular.otf",
]
FONT_PATH = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)

# ---- Image utils -------------------------------------------------------------
def nonwhite_crop(pil_img):
    """흰 배경에서 잉크가 있는 부분만 잘라 L(그레이)로 반환. 없으면 None."""
    g = pil_img.convert("L"); px = g.load()
    w, h = g.size; minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if px[x, y] < 250:
                if x < minx: minx = x
                if y < miny: miny = y
                if x > maxx: maxx = x
                if y > maxy: maxy = y
    if maxx == -1: return None
    pad = 8
    minx = max(0, minx - pad); miny = max(0, miny - pad)
    maxx = min(w - 1, maxx + pad); maxy = min(h - 1, maxy + pad)
    roi = pil_img.crop((minx, miny, maxx + 1, maxy + 1))
    return roi.convert("L").point(lambda v: 255 if v > 200 else 0, mode="1").convert("L")

def to_png_bytes(pil_img):
    bio = io.BytesIO()
    pil_img.save(bio, format="PNG")
    return bio.getvalue()

# ---- (optional) Google Vision ------------------------------------------------
def ocr_text_google(pil_bw):
    try:
        from google.cloud import vision
    except Exception:
        return "(Google Vision 미설치)"
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return "(GOOGLE_APPLICATION_CREDENTIALS 미설정)"
    client = vision.ImageAnnotatorClient()
    img = vision.Image(content=to_png_bytes(pil_bw))
    try:
        resp = client.document_text_detection(image=img, image_context={"language_hints": ["ko","en"]})
    except Exception as e:
        return f"(Vision 호출 오류: {e})"
    if resp.error.message:
        return f"(Vision 오류: {resp.error.message})"
    txt = (resp.full_text_annotation.text or "").strip()
    return txt if txt else "(인식 결과 없음)"

# ---- SimpleTex ---------------------------------------------------------------
def _st_random(n=16): return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(n))
def _st_sign(headers, data, secret):
    keys = sorted(set(list(headers.keys()) + list(data.keys())))
    pre = "&".join([f"{k}={headers.get(k, data.get(k,''))}" for k in keys]) + f"&secret={secret}"
    return hashlib.md5(pre.encode()).hexdigest()

def _get_simpletex_credentials():
    uat = "IIpNbdw6h4hS7YEx1CgjoPl8S8cBhPtZgzEp1amCKX3j6NrAchmmsO7c11Jx6lPM"  # 데모
    if not uat:
        try:
            with open(os.path.expanduser("~/.simpletex_uat"), "r", encoding="utf-8") as f:
                uat = f.read().strip()
        except FileNotFoundError:
            pass
    app_id = os.getenv("SIMPLETEX_APP_ID")
    app_secret = os.getenv("SIMPLETEX_APP_SECRET")
    return uat, app_id, app_secret

def simpletex_ocr(pil_img, prefer_turbo=True):
    if requests is None:
        return None, "requests 미설치: py -3.11 -m pip install requests"
    url = f"{SIMPLETEX_DOMAIN}/api/latex_ocr_turbo" if prefer_turbo else f"{SIMPLETEX_DOMAIN}/api/latex_ocr"
    UAT, APP_ID, APP_SECRET = _get_simpletex_credentials()
    headers, data = {}, {}
    if UAT:
        headers["token"] = UAT
    elif APP_ID and APP_SECRET:
        headers["timestamp"]  = str(int(datetime.datetime.now().timestamp()))
        headers["random-str"] = _st_random(16)
        headers["app-id"]     = APP_ID
        headers["sign"]       = _st_sign(headers, data, APP_SECRET)
    else:
        return None, "인증정보 없음: SIMPLETEX_UAT 또는 (SIMPLETEX_APP_ID/SECRET) 설정 필요"
    files = {"file": ("ink.png", to_png_bytes(pil_img.convert("RGB")), "image/png")}
    try:
        res = requests.post(url, headers=headers, data=data, files=files, timeout=SIMPLETEX_TIMEOUT)
    except Exception as e:
        return None, f"HTTP 요청 실패: {e}"
    try:
        j = res.json()
    except Exception:
        return None, f"응답 파싱 실패(HTTP {res.status_code})"
    if j.get("status") is True:
        r = j.get("res", {})
        latex = r.get("latex") if isinstance(r, dict) else r
        return (str(latex), None) if latex else (None, "결과 없음(res.latex 비어 있음)")
    return None, str(j)

def ocr_formula_simpletex(pil_bw):
    latex, err = simpletex_ocr(pil_bw, prefer_turbo=SIMPLETEX_USE_TURBO)
    if latex is None:
        return f"(SimpleTex 오류: {err})"
    # 화면에도 '텍스트 형태 수식'으로만 보여 주기 위해 정리
    return _clean_ocr_latex(str(latex))



# ---- LaTeX render ------------------------------------------------------------
def _sanitize_latex_for_mathtext(s):
    s = s.strip()
    if len(s)>=2 and s[0]=="$" and s[-1]=="$": s = s[1:-1].strip()
    if s.startswith(r"\[") and s.endswith(r"\]"): s = s[2:-2].strip()
    s = " ".join(s.split())
    for bad in (r"\displaystyle", r"\begin{aligned}", r"\end{aligned}",
                r"\begin{align}", r"\end{align}",
                r"\begin{equation}", r"\end{equation}", r"\textstyle"):
        s = s.replace(bad, "")
    s = s.replace(r"\left","").replace(r"\right","")
    return s

def render_latex_to_pil(latex, fontsize=36, dpi=220):
    s = f"${_sanitize_latex_for_mathtext(latex)}$"
    fig = plt.figure(dpi=dpi); fig.patch.set_alpha(0.0)
    plt.axis("off"); plt.text(0.5, 0.5, s, ha="center", va="center", fontsize=fontsize)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.15, transparent=True)
    plt.close(fig); buf.seek(0)
    return Image.open(buf).convert("RGBA")

# ---- SymPy parsing: safe loader + fallback -----------------------------------
def _safe_parse_latex():
    try:
        from sympy.parsing.latex import parse_latex as _pl
        return _pl
    except Exception:
        return None

def _check_antlr_runtime():
    if sp is None:
        return 'sympy 미설치: py -3.11 -m pip install -U sympy'
    pl = _safe_parse_latex()
    if not callable(pl):
        return ('SymPy LaTeX 파서를 불러올 수 없습니다.\n'
                '설치 확인: py -3.11 -m pip install -U sympy "antlr4-python3-runtime==4.11.*"')
    try:
        ver = _pkg_version('antlr4-python3-runtime')
    except Exception:
        ver = None
    if not ver or not ver.startswith('4.11'):
        return ('antlr4-python3-runtime 4.11.x 필요'
                f' (현재: {ver or "unknown"})\n> py -3.11 -m pip install "antlr4-python3-runtime==4.11.*"')
    return None

def _sanitize_latex_for_sympy(s: str) -> str:
    s = s.strip()
    if len(s)>=2 and s[0]=="$" and s[-1]=="$": s = s[1:-1].strip()
    if s.startswith(r"\[") and s.endswith(r"\]"): s = s[2:-2].strip()
    for bad in (r"\displaystyle", r"\textstyle", r"\begin{aligned}", r"\end{aligned}",
                r"\begin{align}", r"\end{align}", r"\begin{equation}", r"\end{equation}"):
        s = s.replace(bad, "")
    return s

def _latex_to_sympy(expr_latex):
    err = _check_antlr_runtime()
    if err: return None, err
    pl = _safe_parse_latex()
    if not callable(pl):
        return None, "SymPy LaTeX 파서를 사용할 수 없습니다."
    try:
        s = _sanitize_latex_for_sympy(expr_latex)
        if DEBUG_PARSER: print("[DBG] try LaTeX parse:", s)
        obj = pl(s)
        if DEBUG_PARSER: print("[DBG] LaTeX parse OK ->", type(obj))
        return obj, None
    except Exception as e:
        if DEBUG_PARSER: print("[DBG] LaTeX parse FAIL:", e)
        return None, f"SymPy 파싱 실패: {e}"

# --- ASCII fallback (sympify) -------------------------------------------------
_ASCII_LOCALS = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "exp": sp.exp,
    "log": sp.log, "sqrt": sp.sqrt, "pi": sp.pi, "e": sp.E,
}
def _normalize_ascii(s: str) -> str:
    # 기호 통일
    s = (s.replace("÷", "/").replace("×", "*").replace("·", "*")
           .replace("−", "-").replace("^", "**"))

    # 공백 여러 개 -> 하나로 줄이기
    s = " ".join(s.split())

    # 숫자 바로 뒤에 변수/괄호가 오면 곱셈으로 해석: 2x -> 2*x, 3(x+1) -> 3*(x+1)
    s = re.sub(r"(\d)\s*([A-Za-z(])", r"\1*\2", s)

    # 닫는 괄호 뒤에 변수/숫자/괄호가 오면 곱셈: (x+1)2 -> (x+1)*2, (x+1)(x-1) -> (x+1)*(x-1)
    s = re.sub(r"(\))\s*([A-Za-z0-9(])", r"\1*\2", s)


    return s.strip()

def _ascii_to_sympy(expr_str: str):
    s = _normalize_ascii(expr_str)
    if DEBUG_PARSER: print("[DBG] try ASCII(sympify):", s)
    if "=" in s and s.count("=") == 1:
        lhs_str, rhs_str = s.split("=", 1)
        lhs = sp.sympify(lhs_str, locals=_ASCII_LOCALS, evaluate=False)
        rhs = sp.sympify(rhs_str, locals=_ASCII_LOCALS, evaluate=False)
        obj = sp.Eq(lhs, rhs)
    else:
        obj = sp.sympify(s, locals=_ASCII_LOCALS, evaluate=False)
    if DEBUG_PARSER: print("[DBG] ASCII parse OK ->", type(obj))
    return obj, None

def _looks_like_latex(s: str) -> bool:
    s = s.strip()

    # 1) 백슬래시가 있으면 무조건 LaTeX
    if "\\" in s:
        return True

    # 2) 중괄호 + 지수 표기가 같이 있으면 LaTeX로 취급
    #    예: "y = 2{x}^2", "x^{2}", "{x}^3" 등
    if ("{" in s and "}" in s and "^" in s):
        return True

    # 3) 대표적인 LaTeX 토큰
    for t in ["\\frac", "\\int", "\\sum", "\\sqrt", "\\left", "\\right", "\\begin", "\\end"]:
        if t in s:
            return True

    return False

def _clean_ocr_latex(s: str) -> str:
    """
    SimpleTex가 뱉은 LaTeX/텍스트를
    - 곱하기, 나누기, 분수, 불필요한 LaTeX 껍데기 등을 정리해서
      '7*5', '(1)/(2)*x', 'x^2 + 3' 같은 텍스트 수식으로 만든다.
    """
    s = (s or "").strip()
    if not s:
        return s

    # 0) 자주 나오는 OCR 오타 보정: \test -> \text
    s = s.replace(r"\test", r"\text")

    # 1) 바깥 수식 구분자 제거: $...$, \[...\]
    if len(s) >= 2 and s[0] == "$" and s[-1] == "$":
        s = s[1:-1].strip()
    if s.startswith(r"\[") and s.endswith(r"\]"):
        s = s[2:-2].strip()

    # 2) display style / align 환경 제거
    for bad in (
        r"\displaystyle", r"\textstyle",
        r"\begin{aligned}", r"\end{aligned}",
        r"\begin{align}",   r"\end{align}",
        r"\begin{equation}", r"\end{equation}",
    ):
        s = s.replace(bad, "")

    # 3) \text{...}, \mathrm{...}, \operatorname{...}, \textrm{...} 껍데기 벗기기
    #    예: \text{3+3} -> 3+3
    s = re.sub(
        r"\\(?:text|mathrm|operatorname|textrm)\s*{([^{}]+)}",
        r"\1",
        s,
    )

    # 4) 단순 분수: \frac{num}{den} -> (num)/(den)
    def repl_frac(m):
        num = m.group(1).strip()
        den = m.group(2).strip()
        return f"({num})/({den})"

    s = re.sub(
        r"\\(?:frac|dfrac|tfrac)\s*{([^{}]+)}\s*{([^{}]+)}",
        repl_frac,
        s,
    )

    # 5) 곱하기 기호 정리
    #   - \times, \cdot, 유니코드 ×, ·
    #   - OCR이 /times 로 뱉는 경우도 처리: 7/times5 -> 7*5
    s = s.replace(r"\times", "*").replace(r"\cdot", "*")
    s = s.replace("×", "*").replace("·", "*")
    s = re.sub(r"/\s*times", "*", s)    # '7/times5' -> '7*5'
    s = re.sub(r"\btimes\b", "*", s)    # '7 times 5' -> '7 * 5'

    # 6) 나누기 기호 정리
    s = s.replace(r"\div", "/").replace("÷", "/")

    # 7) 자잘한 공백/레이아웃 명령 제거
    for t in [r"\left", r"\right", r"\!", r"\,", r"\;", r"\:", r"\ ", r"~"]:
        s = s.replace(t, "")

    # 8) 지수 괄호 정리: x^{2} -> x^2
    s = re.sub(r"\^\s*{([^{}]+)}", r"^\1", s)

    # (선택) 너무 단순한 적분: \int{4} 처럼 한 줄 전체가 이 꼴이면 그냥 안쪽만 남김
    m_int = re.fullmatch(r"\\int\s*{([^{}]+)}", s)
    if m_int:
        s = m_int.group(1).strip()

    # 9) 공백 정리
    s = " ".join(s.split())
    return s


def _parse_any(expr_str: str):
    """라텍스가 의심되면 LaTeX → 실패 시 ASCII 폴백, 아니면 ASCII 직행."""
    # 0) 먼저 OCR 특유의 LaTeX 노이즈를 정리해서
    #    '7/times5', '\frac{1}{2}x' 등을 텍스트 수식으로 바꾼다.
    s = _clean_ocr_latex(expr_str)
    if not s:
        return None, "빈 수식입니다."

    # 이후 로직은 동일
    if _looks_like_latex(s):
        obj, err = _latex_to_sympy(s)
        if obj is not None:
            return obj, None
        try:
            return _ascii_to_sympy(s)
        except Exception as e:
            return None, f"파싱 실패(라텍스→ASCII 폴백 실패): {e}"
    else:
        try:
            return _ascii_to_sympy(s)
        except Exception as e:
            return None, f"파싱 실패(ASCII): {e}"



# --- evaluate/plot ------------------------------------------------------------
def _eval_numeric(expr):
    try: expr = expr.doit()
    except Exception: pass
    try: expr = sp.simplify(expr)
    except Exception: pass
    try:
        if len(getattr(expr, "free_symbols", [])) == 0:
            return sp.N(expr)
    except Exception:
        pass
    return None

def _format_number(v, digits=2):
    """SymPy 수를 소수 digits자리로 반올림해서 문자열로 반환"""
    try:
        return f"{float(sp.N(v)):.{digits}f}"
    except Exception:
        return str(sp.N(v, digits))


def _format_number_list(vals, digits=2):
    """여러 개의 수를 'a, b, c' 형태 문자열로 변환"""
    return ", ".join(_format_number(v, digits) for v in vals)

def calc_from_latex(latex: str) -> str:
    obj, err = _parse_any(latex)
    if err: return f"(계산 불가) {err}"
    try:
        if not isinstance(obj, sp.Equality):
            v = _eval_numeric(obj)
            if v is not None: return _format_number(v, 2)
            return "(계산 불가) 기호 변수가 포함되어 숫자 평가가 곤란합니다."
        x = sp.Symbol("x")
        eq = sp.Eq(obj.lhs, obj.rhs)
        expr = sp.simplify(eq.lhs - eq.rhs)
        free = list(expr.free_symbols)
        if len(free) == 1 and free[0] == x:
            try:
                sol = sp.solveset(expr, x, domain=sp.S.Reals)
                if isinstance(sol, sp.FiniteSet):
                    vals = sorted([sp.N(s) for s in sol])
                    return "x = " + _format_number_list(vals, 2)
            except Exception: pass
            try:
                poly = sp.Poly(expr, x)
                vals = [sp.N(r) for r in poly.nroots() if abs(sp.im(r)) < 1e-9]
                if vals:
                    return "x ≈ " + _format_number_list(vals, 2)
            except Exception: pass
            return "(계산 불가) 해석/수치 해를 찾지 못했습니다."
        else:
            return "(계산 불가) 다변수 등식 또는 x가 아닌 변수입니다."
    except Exception as e:
        return f"(계산 중 오류) {e}"

def plot_from_latex(latex: str, x_range=(-10,10), samples=1000):
    obj, err = _parse_any(latex)
    if err: return None, err
    x = sp.Symbol("x"); y = sp.Symbol("y")
    try:
        target = None
        if isinstance(obj, sp.Equality):
            lhs, rhs = obj.lhs, obj.rhs
            if lhs == y: target = rhs
            elif rhs == y: target = lhs
            else:
                try:
                    sol = sp.solve(sp.Eq(lhs, rhs), y, dict=True)
                    if sol: target = sp.simplify(sol[0][y])
                except Exception: pass
        else:
            target = obj
        if target is None: return None, "y=f(x) 형태로 해석할 수 없습니다."
        try: target = sp.simplify(target.doit())
        except Exception: pass
        syms = list(target.free_symbols)
        if any(s != x for s in syms): return None, "단일 변수(x) 그래프만 지원합니다."

        f = sp.lambdify(x, target, "numpy")
        xs = np.linspace(x_range[0], x_range[1], samples)
        with np.errstate(all='ignore'):
            ys = f(xs)

        fig = plt.figure(figsize=GRAPH_FIGSIZE, dpi=GRAPH_DPI)  # 작게
        ax = fig.add_subplot(111)
        ax.plot(xs, ys); ax.grid(True, alpha=0.3)
        ax.set_xlabel("x"); ax.set_ylabel("y")
        ax.set_title(f"y = {sp.latex(target)}")
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", transparent=True)
        plt.close(fig); buf.seek(0)
        return Image.open(buf).convert("RGBA"), None
    except Exception as e:
        return None, f"그래프 생성 실패: {e}"

# ---- Tk app ------------------------------------------------------------------
class InkApp:
    def __init__(self, root):
        self.root = root
        root.title("TkInk OCR (SimpleTex · 키보드 인식 · 투명창 · 계산/그래프)")
        root.geometry(f"{W+15}x{H+380}")

        if requests is None:
            messagebox.showerror("의존성 오류", "requests 미설치:\npy -3.11 -m pip install requests")
            raise SystemExit(1)

        # 단축키
        root.bind("<space>",  self._hotkey_recognize)  # OCR
        root.bind("c",        self._hotkey_clear)      # 초기화
        root.bind("q",        self._hotkey_quit)       # 종료
        root.bind("t",        self._hotkey_preview)    # LaTeX 오버레이
        root.bind("T",        self._hotkey_preview)
        root.bind("g",        self._hotkey_plot)       # 그래프
        root.bind("<equal>",  self._hotkey_calc)       # '=' 계산
        root.bind("e",        self._hotkey_hide_overlays)  # 오버레이 닫기
        root.bind("E",        self._hotkey_hide_overlays)

        self.info = ttk.Label(
            root,
            text="좌=문자 / 우=수식 · Space: 인식 · c:초기화 · q:종료 · t:오버레이 · g:그래프 · =:계산 · e:오버레이 닫기"
        )
        self.info.pack(pady=4)

        self.canvas = tk.Canvas(root, width=W, height=H, bg="#FFFFFF",
                                highlightthickness=1, highlightbackground="#CCCCCC")
        self.canvas.pack()

        self.text_img = Image.new("RGB", (W, H), (255, 255, 255))
        self.form_img = Image.new("RGB", (W, H), (255, 255, 255))
        self.text_draw = ImageDraw.Draw(self.text_img)
        self.form_draw = ImageDraw.Draw(self.form_img)

        self.view_img = Image.new("RGB", (W, H), (255, 255, 255))
        self.view_tk = ImageTk.PhotoImage(self.view_img, master=self.canvas)
        self._img_refs = deque(maxlen=2); self._img_refs.append(self.view_tk)
        self.image_on_canvas = self.canvas.create_image(0, 0, image=self.view_tk, anchor="nw")

        # 마우스 드로잉
        self.canvas.bind("<Button-1>", self.pen_down_left)
        self.canvas.bind("<B1-Motion>", self.pen_move_left)
        self.canvas.bind("<ButtonRelease-1>", self.pen_up)
        self.canvas.bind("<Button-3>", self.pen_down_right)
        self.canvas.bind("<B3-Motion>", self.pen_move_right)
        self.canvas.bind("<ButtonRelease-3>", self.pen_up)

        self.status = ttk.Label(root, text="대기"); self.status.pack(pady=(2, 6))

        self.result = tk.Text(root, height=RESULT_ROWS, wrap="word")
        self.result.pack(fill="both", expand=True, padx=2, pady=6)
        self.result.configure(state="disabled")
        self.results = []

        self.drawing_left = False
        self.drawing_right = False
        self.last_pt = None
        self.processing = False

        self.font = ImageFont.truetype(FONT_PATH, 18) if FONT_PATH else None

        # 열린 오버레이 추적
        self._overlays = []
        self.refresh_view()

    # hotkeys
    def _hotkey_recognize(self, e): self.on_click_recognize()
    def _hotkey_clear(self, e): self.clear_all()
    def _hotkey_quit(self, e): self.root.destroy()
    def _hotkey_preview(self, e): self.on_preview_window()
    def _hotkey_plot(self, e): self.on_plot_window()
    def _hotkey_calc(self, e): self.on_calc()
    def _hotkey_hide_overlays(self, e): self.close_overlays()

    # drawing
    def refresh_view(self):
        merged = ImageChops.darker(self.text_img, self.form_img)
        self.view_img.paste(merged)
        new_tk = ImageTk.PhotoImage(self.view_img, master=self.canvas)
        self._img_refs.append(new_tk); self.view_tk = new_tk
        self.canvas.itemconfigure(self.image_on_canvas, image=self.view_tk)

    def pen_down_left(self, e):  self.drawing_left,  self.last_pt = True, (e.x, e.y)
    def pen_down_right(self, e): self.drawing_right, self.last_pt = True, (e.x, e.y)

    def pen_move_left(self, e):
        if not self.drawing_left: return
        x0, y0 = self.last_pt; x1, y1 = e.x, e.y
        self.text_draw.line([(x0, y0), (x1, y1)], fill=COLOR_TEXT, width=PEN_WIDTH)
        self.last_pt = (x1, y1); self.refresh_view()

    def pen_move_right(self, e):
        if not self.drawing_right: return
        x0, y0 = self.last_pt; x1, y1 = e.x, e.y
        self.form_draw.line([(x0, y0), (x1, y1)], fill=COLOR_FORM, width=PEN_WIDTH)
        self.last_pt = (x1, y1); self.refresh_view()

    def pen_up(self, e):
        self.drawing_left = False
        self.drawing_right = False
        self.last_pt = None

    # Space: 인식
    def on_click_recognize(self):
        if self.processing: return
        crop_t = nonwhite_crop(self.text_img)
        crop_m = nonwhite_crop(self.form_img)
        if crop_t is None and crop_m is None:
            messagebox.showinfo("알림", "인식할 잉크가 없습니다.")
            return
        self.processing = True
        self.status.configure(text="인식 중...")
        threading.Thread(target=self._do_recognize, args=(crop_t, crop_m), daemon=True).start()

    def _do_recognize(self, crop_t, crop_m):
        try:
            if crop_t is not None:
                txt = ocr_text_google(crop_t)
                self.results.append(("TEXT", txt))
                self.text_img.paste((255,255,255), (0,0,W,H))
            if crop_m is not None:
                latex = ocr_formula_simpletex(crop_m)
                self.results.append(("MATH", latex))
                self.form_img.paste((255,255,255), (0,0,W,H))
        finally:
            self.processing = False
            self.root.after(0, self._after_recognize_ui)

    def _after_recognize_ui(self):
        self.update_results(); self.refresh_view()
        self.status.configure(text="완료")

    def clear_all(self):
        self.text_img.paste((255,255,255), (0,0,W,H))
        self.form_img.paste((255,255,255), (0,0,W,H))
        self.results.clear()
        self.update_results(); self.refresh_view()
        self.status.configure(text="초기화 완료")

    def update_results(self):
        self.result.configure(state="normal"); self.result.delete("1.0", tk.END)
        for lab, txt in self.results[-200:]:
            tag = "[TEXT]" if lab == "TEXT" else ("[MATH]" if lab == "MATH" else "[CALC]")
            self.result.insert(tk.END, f"{tag} {txt}\n")
        self.result.configure(state="disabled"); self.result.see(tk.END)

    # 최신 수식
    def _last_latex(self):
        for lab, txt in reversed(self.results):
            if lab == "MATH" and txt and not txt.startswith("(SimpleTex 오류"):
                return txt.strip()
        return None

    # 오버레이 공용
    def show_float_window(self, pil_rgba):
        TRANSP = '#00FF00'
        win = tk.Toplevel(self.root)
        win.overrideredirect(True); win.wm_attributes('-topmost', 1)
        win.configure(bg=TRANSP)
        try:
            win.wm_attributes('-transparentcolor', TRANSP)  # Windows 10+
        except Exception:
            pass

        # 오버레이 추적 및 안전 종료 훅
        self._overlays.append(win)
        def _on_close():
            try:
                self._overlays.remove(win)
            except ValueError:
                pass
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        imgtk = ImageTk.PhotoImage(pil_rgba, master=win)
        win._imgtk = imgtk  # 개별 창에 이미지 참조 보관(가비지 컬렉션 방지)
        lbl = tk.Label(win, image=imgtk, bg=TRANSP, bd=0, highlightthickness=0)
        lbl.pack()
        def start(e): win._x, win._y = e.x, e.y
        def drag(e): win.geometry(f"+{win.winfo_x()+e.x-win._x}+{win.winfo_y()+e.y-win._y}")
        lbl.bind('<Button-1>', start); lbl.bind('<B1-Motion>', drag)
        win.bind('<Escape>', lambda e: _on_close())

        win.update_idletasks()
        sx = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        sy = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{max(0,sx)}+{max(0,sy)}")

    # e/E: 모든 오버레이 닫기
    def close_overlays(self):
        for w in list(self._overlays)[::-1]:
            try:
                w.destroy()  # protocol로 _on_close가 호출되어 목록에서 제거됨
            except Exception:
                pass
        self._overlays.clear()
        self.status.configure(text="오버레이 닫힘")

    # t: LaTeX 오버레이
    def on_preview_window(self):
        latex = self._last_latex()
        if not latex:
            messagebox.showinfo("알림", "표시할 수식이 없습니다. 먼저 Space로 인식하세요.")
            return
        try:
            pil = render_latex_to_pil(latex, fontsize=36, dpi=220)
            self.show_float_window(pil)
        except Exception as e:
            import traceback; traceback.print_exc()
            messagebox.showerror("미리보기 오류", str(e))

    # g: 그래프
    def on_plot_window(self):
        latex = self._last_latex()
        if not latex:
            messagebox.showinfo("알림", "그래프화할 수식이 없습니다.")
            return
        pil, err = plot_from_latex(latex, x_range=(-10,10))
        if err:
            messagebox.showwarning("그래프 불가", err); return
        self.show_float_window(pil)
        self.status.configure(text="그래프 완료")

    # '=': 계산
    def on_calc(self):
        latex = self._last_latex()
        if not latex:
            messagebox.showinfo("알림", "계산할 수식이 없습니다.")
            return
        res = calc_from_latex(latex)
        self.results.append(("CALC", res))
        self.update_results()
        self.status.configure(text="계산 완료")

# ---- main --------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = InkApp(root)
    root.mainloop()
