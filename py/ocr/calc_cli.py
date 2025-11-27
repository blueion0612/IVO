#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Calculator CLI - Expression Evaluation for Electron

Simple expression calculator using SymPy.
Evaluates mathematical expressions and outputs numeric results.

Usage:
    python calc_cli.py "2+3*4"
    python calc_cli.py "x**2 + 1"  # Variables substituted with 0
"""

import sys
import sympy as sp


def main():
    """Main entry point for calculator CLI."""
    if len(sys.argv) < 2:
        print("No expression provided", file=sys.stderr)
        sys.exit(1)

    expr_str = sys.argv[1]

    try:
        x = sp.symbols("x")
        expr = sp.sympify(expr_str)
        free = list(expr.free_symbols)

        if len(free) == 0:
            val = expr.evalf()
        else:
            # Substitute all variables with 0 for simple evaluation
            subs = {s: 0 for s in free}
            val = expr.subs(subs).evalf()

        print(val)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
