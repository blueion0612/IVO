#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
InkOCR - Handwriting Recognition and Math Processing Module

Provides OCR capabilities for handwritten text and mathematical formulas,
with integrated calculation and graph plotting features.

Features:
- Google Vision API for text OCR
- SimpleTex API for LaTeX/math formula recognition
- SymPy-based mathematical expression parsing and evaluation
- Matplotlib graph plotting for y=f(x) functions
- System of equations solver

Dependencies:
    pip install requests pillow matplotlib sympy numpy
    pip install google-cloud-vision  # Optional, for Google Vision OCR
"""

import os
import io
import threading
import hashlib
import random
import string
import datetime
import re
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageTk, ImageFont, ImageChops

# =============================================================================
# Configuration
# =============================================================================

# Debug flag for parser output
DEBUG_PARSER = False

# Canvas dimensions
W, H = 980, 460
RESULT_ROWS = 9
PEN_WIDTH = 6
COLOR_TEXT = (0, 0, 0)      # Black for text
COLOR_FORM = (0, 0, 255)    # Blue for formulas

# SimpleTex API settings
SIMPLETEX_USE_TURBO = True
SIMPLETEX_TIMEOUT = 30
SIMPLETEX_DOMAIN = "https://server.simpletex.net"

# Graph dimensions
GRAPH_FIGSIZE = (3.2, 2.2)  # inches (width, height)
GRAPH_DPI = 140             # pixel density

# Font candidates for Korean text rendering
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\NanumGothic.ttf",
    r"C:\Windows\Fonts\NotoSansKR-Regular.otf",
]
FONT_PATH = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)


# =============================================================================
# Optional Dependencies
# =============================================================================

try:
    import requests
except ImportError:
    requests = None

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import sympy as sp
except ImportError:
    sp = None

try:
    from importlib.metadata import version as _pkg_version
except ImportError:
    from importlib_metadata import version as _pkg_version  # type: ignore


# =============================================================================
# Image Utilities
# =============================================================================

def nonwhite_crop(pil_img):
    """
    Crop image to non-white region and convert to grayscale.

    Args:
        pil_img: PIL Image with white background

    Returns:
        Cropped grayscale image or None if no ink found
    """
    g = pil_img.convert("L")
    px = g.load()
    w, h = g.size
    minx, miny, maxx, maxy = w, h, -1, -1

    for y in range(h):
        for x in range(w):
            if px[x, y] < 250:
                if x < minx:
                    minx = x
                if y < miny:
                    miny = y
                if x > maxx:
                    maxx = x
                if y > maxy:
                    maxy = y

    if maxx == -1:
        return None

    pad = 8
    minx = max(0, minx - pad)
    miny = max(0, miny - pad)
    maxx = min(w - 1, maxx + pad)
    maxy = min(h - 1, maxy + pad)

    roi = pil_img.crop((minx, miny, maxx + 1, maxy + 1))
    return roi.convert("L").point(lambda v: 255 if v > 200 else 0, mode="1").convert("L")


def to_png_bytes(pil_img):
    """Convert PIL Image to PNG bytes."""
    bio = io.BytesIO()
    pil_img.save(bio, format="PNG")
    return bio.getvalue()


# =============================================================================
# Google Vision OCR
# =============================================================================

def ocr_text_google(pil_bw):
    """
    Perform text OCR using Google Vision API.

    Args:
        pil_bw: Grayscale PIL Image

    Returns:
        Recognized text string or error message
    """
    try:
        from google.cloud import vision
    except ImportError:
        return "(Google Vision not installed)"

    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return "(GOOGLE_APPLICATION_CREDENTIALS not set)"

    client = vision.ImageAnnotatorClient()
    img = vision.Image(content=to_png_bytes(pil_bw))

    try:
        resp = client.document_text_detection(
            image=img,
            image_context={"language_hints": ["ko", "en"]}
        )
    except Exception as e:
        return f"(Vision API error: {e})"

    if resp.error.message:
        return f"(Vision error: {resp.error.message})"

    txt = (resp.full_text_annotation.text or "").strip()
    return txt if txt else "(No text recognized)"


# =============================================================================
# SimpleTex API
# =============================================================================

def _st_random(n=16):
    """Generate random string for SimpleTex API."""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(n))


def _st_sign(headers, data, secret):
    """Generate signature for SimpleTex API."""
    keys = sorted(set(list(headers.keys()) + list(data.keys())))
    pre = "&".join([f"{k}={headers.get(k, data.get(k, ''))}" for k in keys]) + f"&secret={secret}"
    return hashlib.md5(pre.encode()).hexdigest()


def _get_simpletex_credentials():
    """Get SimpleTex API credentials."""
    # Demo token (replace with your own for production)
    uat = "IIpNbdw6h4hS7YEx1CgjoPl8S8cBhPtZgzEp1amCKX3j6NrAchmmsO7c11Jx6lPM"

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
    """
    Perform math OCR using SimpleTex API.

    Args:
        pil_img: PIL Image
        prefer_turbo: Use turbo API endpoint if True

    Returns:
        Tuple of (latex_string, error_message)
    """
    if requests is None:
        return None, "requests not installed: pip install requests"

    url = f"{SIMPLETEX_DOMAIN}/api/latex_ocr_turbo" if prefer_turbo else f"{SIMPLETEX_DOMAIN}/api/latex_ocr"
    UAT, APP_ID, APP_SECRET = _get_simpletex_credentials()

    headers, data = {}, {}

    if UAT:
        headers["token"] = UAT
    elif APP_ID and APP_SECRET:
        headers["timestamp"] = str(int(datetime.datetime.now().timestamp()))
        headers["random-str"] = _st_random(16)
        headers["app-id"] = APP_ID
        headers["sign"] = _st_sign(headers, data, APP_SECRET)
    else:
        return None, "No credentials: Set SIMPLETEX_UAT or SIMPLETEX_APP_ID/SECRET"

    files = {"file": ("ink.png", to_png_bytes(pil_img.convert("RGB")), "image/png")}

    try:
        res = requests.post(url, headers=headers, data=data, files=files, timeout=SIMPLETEX_TIMEOUT)
    except Exception as e:
        return None, f"HTTP request failed: {e}"

    try:
        j = res.json()
    except Exception:
        return None, f"Response parse failed (HTTP {res.status_code})"

    if j.get("status") is True:
        r = j.get("res", {})
        latex = r.get("latex") if isinstance(r, dict) else r
        return (str(latex), None) if latex else (None, "Empty result")

    return None, str(j)


def ocr_formula_simpletex(pil_bw):
    """
    Perform formula OCR and clean the result.

    Args:
        pil_bw: Grayscale PIL Image

    Returns:
        Cleaned formula string or error message
    """
    latex, err = simpletex_ocr(pil_bw, prefer_turbo=SIMPLETEX_USE_TURBO)
    if latex is None:
        return f"(SimpleTex error: {err})"
    return _clean_ocr_latex(str(latex))


# =============================================================================
# LaTeX Rendering
# =============================================================================

def _sanitize_latex_for_mathtext(s):
    """Clean LaTeX for matplotlib mathtext rendering."""
    s = s.strip()
    if len(s) >= 2 and s[0] == "$" and s[-1] == "$":
        s = s[1:-1].strip()
    if s.startswith(r"\[") and s.endswith(r"\]"):
        s = s[2:-2].strip()
    s = " ".join(s.split())

    for bad in (r"\displaystyle", r"\begin{aligned}", r"\end{aligned}",
                r"\begin{align}", r"\end{align}",
                r"\begin{equation}", r"\end{equation}", r"\textstyle"):
        s = s.replace(bad, "")

    s = s.replace(r"\left", "").replace(r"\right", "")
    return s


def render_latex_to_pil(latex, fontsize=36, dpi=220):
    """
    Render LaTeX to PIL Image.

    Args:
        latex: LaTeX string
        fontsize: Font size for rendering
        dpi: Output resolution

    Returns:
        RGBA PIL Image
    """
    s = f"${_sanitize_latex_for_mathtext(latex)}$"
    fig = plt.figure(dpi=dpi)
    fig.patch.set_alpha(0.0)
    plt.axis("off")
    plt.text(0.5, 0.5, s, ha="center", va="center", fontsize=fontsize)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.15, transparent=True)
    plt.close(fig)
    buf.seek(0)

    return Image.open(buf).convert("RGBA")


# =============================================================================
# SymPy Parsing
# =============================================================================

def _safe_parse_latex():
    """Safely load SymPy LaTeX parser."""
    try:
        from sympy.parsing.latex import parse_latex as _pl
        return _pl
    except Exception:
        return None


def _check_antlr_runtime():
    """Check ANTLR runtime compatibility."""
    if sp is None:
        return "sympy not installed: pip install sympy"

    pl = _safe_parse_latex()
    if not callable(pl):
        return ("Cannot load SymPy LaTeX parser.\n"
                "Install: pip install sympy 'antlr4-python3-runtime==4.11.*'")

    try:
        ver = _pkg_version('antlr4-python3-runtime')
    except Exception:
        ver = None

    if not ver or not ver.startswith('4.11'):
        return (f"antlr4-python3-runtime 4.11.x required (current: {ver or 'unknown'})\n"
                "Install: pip install 'antlr4-python3-runtime==4.11.*'")

    return None


def _sanitize_latex_for_sympy(s: str) -> str:
    """Clean LaTeX for SymPy parsing."""
    s = s.strip()
    if len(s) >= 2 and s[0] == "$" and s[-1] == "$":
        s = s[1:-1].strip()
    if s.startswith(r"\[") and s.endswith(r"\]"):
        s = s[2:-2].strip()

    for bad in (r"\displaystyle", r"\textstyle", r"\begin{aligned}", r"\end{aligned}",
                r"\begin{align}", r"\end{align}", r"\begin{equation}", r"\end{equation}"):
        s = s.replace(bad, "")

    return s


def _latex_to_sympy(expr_latex):
    """
    Convert LaTeX to SymPy expression.

    Returns:
        Tuple of (sympy_expr, error_message)
    """
    err = _check_antlr_runtime()
    if err:
        return None, err

    pl = _safe_parse_latex()
    if not callable(pl):
        return None, "Cannot use SymPy LaTeX parser"

    try:
        s = _sanitize_latex_for_sympy(expr_latex)
        if DEBUG_PARSER:
            print("[DBG] LaTeX parse:", s)
        obj = pl(s)
        if DEBUG_PARSER:
            print("[DBG] LaTeX parse OK ->", type(obj))
        return obj, None
    except Exception as e:
        if DEBUG_PARSER:
            print("[DBG] LaTeX parse FAIL:", e)
        return None, f"SymPy parse failed: {e}"


# ASCII fallback locals
_ASCII_LOCALS = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "exp": sp.exp,
    "log": sp.log, "sqrt": sp.sqrt, "pi": sp.pi, "e": sp.E,
} if sp else {}


def _normalize_ascii(s: str) -> str:
    """Normalize ASCII math expression."""
    # Unify operators
    s = (s.replace("÷", "/").replace("×", "*").replace("·", "*")
         .replace("−", "-").replace("^", "**"))

    # Collapse whitespace
    s = " ".join(s.split())

    # Insert multiplication: 2x -> 2*x, 3(x+1) -> 3*(x+1)
    s = re.sub(r"(\d)\s*([A-Za-z(])", r"\1*\2", s)

    # Insert multiplication after closing paren: (x+1)2 -> (x+1)*2
    s = re.sub(r"(\))\s*([A-Za-z0-9(])", r"\1*\2", s)

    return s.strip()


def _ascii_to_sympy(expr_str: str):
    """
    Convert ASCII math to SymPy expression.

    Returns:
        Tuple of (sympy_expr, error_message)
    """
    s = _normalize_ascii(expr_str)
    if DEBUG_PARSER:
        print("[DBG] ASCII(sympify):", s)

    if "=" in s and s.count("=") == 1:
        lhs_str, rhs_str = s.split("=", 1)
        lhs = sp.sympify(lhs_str, locals=_ASCII_LOCALS, evaluate=False)
        rhs = sp.sympify(rhs_str, locals=_ASCII_LOCALS, evaluate=False)
        obj = sp.Eq(lhs, rhs)
    else:
        obj = sp.sympify(s, locals=_ASCII_LOCALS, evaluate=False)

    if DEBUG_PARSER:
        print("[DBG] ASCII parse OK ->", type(obj))

    return obj, None


def _looks_like_latex(s: str) -> bool:
    """Check if string appears to be LaTeX."""
    s = s.strip()

    # Backslash indicates LaTeX
    if "\\" in s:
        return True

    # Braces with exponent indicates LaTeX
    if "{" in s and "}" in s and "^" in s:
        return True

    # Common LaTeX tokens
    for t in ["\\frac", "\\int", "\\sum", "\\sqrt", "\\left", "\\right", "\\begin", "\\end"]:
        if t in s:
            return True

    return False


def _clean_ocr_latex(s: str) -> str:
    """
    Clean OCR LaTeX output to readable text expression.

    Converts LaTeX constructs like \\frac{1}{2} to (1)/(2)
    and cleans up common OCR artifacts.

    Args:
        s: Raw LaTeX string from OCR

    Returns:
        Cleaned text expression
    """
    s = (s or "").strip()
    if not s:
        return s

    # Fix common OCR typo
    s = s.replace(r"\test", r"\text")

    # Remove outer delimiters
    if len(s) >= 2 and s[0] == "$" and s[-1] == "$":
        s = s[1:-1].strip()
    if s.startswith(r"\[") and s.endswith(r"\]"):
        s = s[2:-2].strip()

    # Remove display/align environments
    for bad in (r"\displaystyle", r"\textstyle",
                r"\begin{aligned}", r"\end{aligned}",
                r"\begin{align}", r"\end{align}",
                r"\begin{equation}", r"\end{equation}"):
        s = s.replace(bad, "")

    # Remove text wrappers
    s = re.sub(r"\\(?:text|mathrm|operatorname|textrm)\s*{([^{}]+)}", r"\1", s)

    # Convert fractions: \frac{num}{den} -> (num)/(den)
    def repl_frac(m):
        num = m.group(1).strip()
        den = m.group(2).strip()
        return f"({num})/({den})"

    s = re.sub(r"\\(?:frac|dfrac|tfrac)\s*{([^{}]+)}\s*{([^{}]+)}", repl_frac, s)

    # Normalize multiplication symbols
    s = s.replace(r"\times", "*").replace(r"\cdot", "*")
    s = s.replace("×", "*").replace("·", "*")
    s = re.sub(r"/\s*times", "*", s)
    s = re.sub(r"\btimes\b", "*", s)

    # Normalize division
    s = s.replace(r"\div", "/").replace("÷", "/")

    # Remove spacing commands
    for t in [r"\left", r"\right", r"\!", r"\,", r"\;", r"\:", r"\ ", r"~"]:
        s = s.replace(t, "")

    # Simplify exponents: x^{2} -> x^2
    s = re.sub(r"\^\s*{([^{}]+)}", r"^\1", s)

    # Handle simple integral: \int{4} -> 4
    m_int = re.fullmatch(r"\\int\s*{([^{}]+)}", s)
    if m_int:
        s = m_int.group(1).strip()

    # Collapse whitespace
    s = " ".join(s.split())
    return s


def _parse_any(expr_str: str):
    """
    Parse expression (LaTeX or ASCII) to SymPy.

    Tries LaTeX parsing first if expression looks like LaTeX,
    falls back to ASCII parsing.

    Returns:
        Tuple of (sympy_expr, error_message)
    """
    s = _clean_ocr_latex(expr_str)
    if not s:
        return None, "Empty expression"

    if _looks_like_latex(s):
        obj, err = _latex_to_sympy(s)
        if obj is not None:
            return obj, None
        try:
            return _ascii_to_sympy(s)
        except Exception as e:
            return None, f"Parse failed (LaTeX->ASCII fallback): {e}"
    else:
        try:
            return _ascii_to_sympy(s)
        except Exception as e:
            return None, f"Parse failed (ASCII): {e}"


# =============================================================================
# Calculation and Plotting
# =============================================================================

def _eval_numeric(expr):
    """Evaluate expression numerically if possible."""
    try:
        expr = expr.doit()
    except Exception:
        pass

    try:
        expr = sp.simplify(expr)
    except Exception:
        pass

    try:
        if len(getattr(expr, "free_symbols", [])) == 0:
            return sp.N(expr)
    except Exception:
        pass

    return None


def _format_number(v, digits=2):
    """Format SymPy number to string with specified decimal places."""
    try:
        return f"{float(sp.N(v)):.{digits}f}"
    except Exception:
        return str(sp.N(v, digits))


def _format_number_list(vals, digits=2):
    """Format list of numbers as comma-separated string."""
    return ", ".join(_format_number(v, digits) for v in vals)


def calc_from_latex(latex: str) -> str:
    """
    Calculate result from LaTeX expression.

    Handles:
    - Simple numeric expressions
    - Equations in x (solves for x)

    Args:
        latex: LaTeX or ASCII math expression

    Returns:
        Result string or error message
    """
    obj, err = _parse_any(latex)
    if err:
        return f"(Cannot calculate) {err}"

    try:
        if not isinstance(obj, sp.Equality):
            v = _eval_numeric(obj)
            if v is not None:
                return _format_number(v, 2)
            return "(Cannot calculate) Expression contains symbolic variables"

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
            except Exception:
                pass

            try:
                poly = sp.Poly(expr, x)
                vals = [sp.N(r) for r in poly.nroots() if abs(sp.im(r)) < 1e-9]
                if vals:
                    return "x ≈ " + _format_number_list(vals, 2)
            except Exception:
                pass

            return "(Cannot calculate) Could not find solution"
        else:
            return "(Cannot calculate) Multi-variable or non-x variable equation"

    except Exception as e:
        return f"(Calculation error) {e}"


def plot_from_latex(latex: str, x_range=(-10, 10), samples=1000):
    """
    Generate graph from LaTeX expression.

    Args:
        latex: LaTeX or ASCII expression (y=f(x) form)
        x_range: Tuple of (min_x, max_x)
        samples: Number of sample points

    Returns:
        Tuple of (PIL_Image, error_message)
    """
    obj, err = _parse_any(latex)
    if err:
        return None, err

    x = sp.Symbol("x")
    y = sp.Symbol("y")

    try:
        target = None

        if isinstance(obj, sp.Equality):
            lhs, rhs = obj.lhs, obj.rhs
            if lhs == y:
                target = rhs
            elif rhs == y:
                target = lhs
            else:
                try:
                    sol = sp.solve(sp.Eq(lhs, rhs), y, dict=True)
                    if sol:
                        target = sp.simplify(sol[0][y])
                except Exception:
                    pass
        else:
            target = obj

        if target is None:
            return None, "Cannot interpret as y=f(x) form"

        try:
            target = sp.simplify(target.doit())
        except Exception:
            pass

        syms = list(target.free_symbols)
        if any(s != x for s in syms):
            return None, "Only single variable (x) graphs supported"

        f = sp.lambdify(x, target, "numpy")
        xs = np.linspace(x_range[0], x_range[1], samples)

        with np.errstate(all='ignore'):
            ys = f(xs)

        fig = plt.figure(figsize=GRAPH_FIGSIZE, dpi=GRAPH_DPI)
        ax = fig.add_subplot(111)
        ax.plot(xs, ys)
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_title(f"y = {sp.latex(target)}")

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", transparent=True)
        plt.close(fig)
        buf.seek(0)

        return Image.open(buf).convert("RGBA"), None

    except Exception as e:
        return None, f"Graph generation failed: {e}"


def solve_system_from_latex_list(latex_lines: list) -> str:
    """
    Solve system of equations.

    Args:
        latex_lines: List of equation strings

    Returns:
        Solution string or error message
    """
    if sp is None:
        return "(Error) SymPy not installed"

    equations = []
    all_symbols = set()

    for line in latex_lines:
        obj, err = _parse_any(line)
        if err:
            return f"(Parse error) {err}"

        if isinstance(obj, sp.Equality):
            equations.append(obj)
            all_symbols.update(obj.free_symbols)
        else:
            # Assume expression = 0
            equations.append(sp.Eq(obj, 0))
            all_symbols.update(obj.free_symbols)

    if not equations:
        return "(Error) No valid equations"

    try:
        solutions = sp.solve(equations, list(all_symbols), dict=True)

        if not solutions:
            return "(No solution found)"

        result_parts = []
        for sol in solutions:
            parts = [f"{sym} = {_format_number(val, 2)}" for sym, val in sol.items()]
            result_parts.append(", ".join(parts))

        return " | ".join(result_parts)

    except Exception as e:
        return f"(Solve error) {e}"


# =============================================================================
# Tk Application (Standalone Mode)
# =============================================================================

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False


if TK_AVAILABLE:
    class InkApp:
        """Tkinter application for handwriting OCR."""

        def __init__(self, root):
            self.root = root
            root.title("InkOCR - Handwriting Recognition")
            root.geometry(f"{W+15}x{H+380}")

            if requests is None:
                messagebox.showerror("Dependency Error", "requests not installed:\npip install requests")
                raise SystemExit(1)

            # Hotkeys
            root.bind("<space>", self._hotkey_recognize)
            root.bind("c", self._hotkey_clear)
            root.bind("q", self._hotkey_quit)
            root.bind("t", self._hotkey_preview)
            root.bind("T", self._hotkey_preview)
            root.bind("g", self._hotkey_plot)
            root.bind("<equal>", self._hotkey_calc)
            root.bind("e", self._hotkey_hide_overlays)
            root.bind("E", self._hotkey_hide_overlays)

            self.info = ttk.Label(
                root,
                text="Left=Text / Right=Formula | Space: OCR | c: Clear | q: Quit | t: Preview | g: Graph | =: Calc | e: Close overlays"
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
            self._img_refs = deque(maxlen=2)
            self._img_refs.append(self.view_tk)
            self.image_on_canvas = self.canvas.create_image(0, 0, image=self.view_tk, anchor="nw")

            # Mouse drawing
            self.canvas.bind("<Button-1>", self.pen_down_left)
            self.canvas.bind("<B1-Motion>", self.pen_move_left)
            self.canvas.bind("<ButtonRelease-1>", self.pen_up)
            self.canvas.bind("<Button-3>", self.pen_down_right)
            self.canvas.bind("<B3-Motion>", self.pen_move_right)
            self.canvas.bind("<ButtonRelease-3>", self.pen_up)

            self.status = ttk.Label(root, text="Ready")
            self.status.pack(pady=(2, 6))

            self.result = tk.Text(root, height=RESULT_ROWS, wrap="word")
            self.result.pack(fill="both", expand=True, padx=2, pady=6)
            self.result.configure(state="disabled")
            self.results = []

            self.drawing_left = False
            self.drawing_right = False
            self.last_pt = None
            self.processing = False

            self.font = ImageFont.truetype(FONT_PATH, 18) if FONT_PATH else None

            self._overlays = []
            self.refresh_view()

        def _hotkey_recognize(self, e):
            self.on_click_recognize()

        def _hotkey_clear(self, e):
            self.clear_all()

        def _hotkey_quit(self, e):
            self.root.destroy()

        def _hotkey_preview(self, e):
            self.on_preview_window()

        def _hotkey_plot(self, e):
            self.on_plot_window()

        def _hotkey_calc(self, e):
            self.on_calc()

        def _hotkey_hide_overlays(self, e):
            self.close_overlays()

        def refresh_view(self):
            merged = ImageChops.darker(self.text_img, self.form_img)
            self.view_img.paste(merged)
            new_tk = ImageTk.PhotoImage(self.view_img, master=self.canvas)
            self._img_refs.append(new_tk)
            self.view_tk = new_tk
            self.canvas.itemconfigure(self.image_on_canvas, image=self.view_tk)

        def pen_down_left(self, e):
            self.drawing_left, self.last_pt = True, (e.x, e.y)

        def pen_down_right(self, e):
            self.drawing_right, self.last_pt = True, (e.x, e.y)

        def pen_move_left(self, e):
            if not self.drawing_left:
                return
            x0, y0 = self.last_pt
            x1, y1 = e.x, e.y
            self.text_draw.line([(x0, y0), (x1, y1)], fill=COLOR_TEXT, width=PEN_WIDTH)
            self.last_pt = (x1, y1)
            self.refresh_view()

        def pen_move_right(self, e):
            if not self.drawing_right:
                return
            x0, y0 = self.last_pt
            x1, y1 = e.x, e.y
            self.form_draw.line([(x0, y0), (x1, y1)], fill=COLOR_FORM, width=PEN_WIDTH)
            self.last_pt = (x1, y1)
            self.refresh_view()

        def pen_up(self, e):
            self.drawing_left = False
            self.drawing_right = False
            self.last_pt = None

        def on_click_recognize(self):
            if self.processing:
                return
            crop_t = nonwhite_crop(self.text_img)
            crop_m = nonwhite_crop(self.form_img)
            if crop_t is None and crop_m is None:
                messagebox.showinfo("Info", "No ink to recognize")
                return
            self.processing = True
            self.status.configure(text="Processing...")
            threading.Thread(target=self._do_recognize, args=(crop_t, crop_m), daemon=True).start()

        def _do_recognize(self, crop_t, crop_m):
            try:
                if crop_t is not None:
                    txt = ocr_text_google(crop_t)
                    self.results.append(("TEXT", txt))
                    self.text_img.paste((255, 255, 255), (0, 0, W, H))
                if crop_m is not None:
                    latex = ocr_formula_simpletex(crop_m)
                    self.results.append(("MATH", latex))
                    self.form_img.paste((255, 255, 255), (0, 0, W, H))
            finally:
                self.processing = False
                self.root.after(0, self._after_recognize_ui)

        def _after_recognize_ui(self):
            self.update_results()
            self.refresh_view()
            self.status.configure(text="Done")

        def clear_all(self):
            self.text_img.paste((255, 255, 255), (0, 0, W, H))
            self.form_img.paste((255, 255, 255), (0, 0, W, H))
            self.results.clear()
            self.update_results()
            self.refresh_view()
            self.status.configure(text="Cleared")

        def update_results(self):
            self.result.configure(state="normal")
            self.result.delete("1.0", tk.END)
            for lab, txt in self.results[-200:]:
                tag = "[TEXT]" if lab == "TEXT" else ("[MATH]" if lab == "MATH" else "[CALC]")
                self.result.insert(tk.END, f"{tag} {txt}\n")
            self.result.configure(state="disabled")
            self.result.see(tk.END)

        def _last_latex(self):
            for lab, txt in reversed(self.results):
                if lab == "MATH" and txt and not txt.startswith("(SimpleTex"):
                    return txt.strip()
            return None

        def show_float_window(self, pil_rgba):
            TRANSP = '#00FF00'
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.wm_attributes('-topmost', 1)
            win.configure(bg=TRANSP)
            try:
                win.wm_attributes('-transparentcolor', TRANSP)
            except Exception:
                pass

            self._overlays.append(win)

            def _on_close():
                try:
                    self._overlays.remove(win)
                except ValueError:
                    pass
                win.destroy()

            win.protocol("WM_DELETE_WINDOW", _on_close)

            imgtk = ImageTk.PhotoImage(pil_rgba, master=win)
            win._imgtk = imgtk
            lbl = tk.Label(win, image=imgtk, bg=TRANSP, bd=0, highlightthickness=0)
            lbl.pack()

            def start(e):
                win._x, win._y = e.x, e.y

            def drag(e):
                win.geometry(f"+{win.winfo_x()+e.x-win._x}+{win.winfo_y()+e.y-win._y}")

            lbl.bind('<Button-1>', start)
            lbl.bind('<B1-Motion>', drag)
            win.bind('<Escape>', lambda e: _on_close())

            win.update_idletasks()
            sx = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
            sy = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 2
            win.geometry(f"+{max(0,sx)}+{max(0,sy)}")

        def close_overlays(self):
            for w in list(self._overlays)[::-1]:
                try:
                    w.destroy()
                except Exception:
                    pass
            self._overlays.clear()
            self.status.configure(text="Overlays closed")

        def on_preview_window(self):
            latex = self._last_latex()
            if not latex:
                messagebox.showinfo("Info", "No formula to display. Run OCR first (Space)")
                return
            try:
                pil = render_latex_to_pil(latex, fontsize=36, dpi=220)
                self.show_float_window(pil)
            except Exception as e:
                import traceback
                traceback.print_exc()
                messagebox.showerror("Preview Error", str(e))

        def on_plot_window(self):
            latex = self._last_latex()
            if not latex:
                messagebox.showinfo("Info", "No formula to graph")
                return
            pil, err = plot_from_latex(latex, x_range=(-10, 10))
            if err:
                messagebox.showwarning("Cannot Graph", err)
                return
            self.show_float_window(pil)
            self.status.configure(text="Graph complete")

        def on_calc(self):
            latex = self._last_latex()
            if not latex:
                messagebox.showinfo("Info", "No formula to calculate")
                return
            res = calc_from_latex(latex)
            self.results.append(("CALC", res))
            self.update_results()
            self.status.configure(text="Calculation complete")


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    if TK_AVAILABLE:
        root = tk.Tk()
        app = InkApp(root)
        root.mainloop()
    else:
        print("Tkinter not available. This module can be used as a library.")
