#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Math CLI - Mathematical Operations for Electron

Provides calculation, graph plotting, and system of equations solving.
Uses InkOCR module for math processing.

Usage:
    # Single expression calculation
    python math_cli.py calc "<latex_or_expr>"

    # Graph plotting
    python math_cli.py graph "<latex_or_expr>" "output.png"

    # System of equations (newline-separated)
    python math_cli.py system "x^2 + y = 1\\nx - y = 2"
"""

import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

try:
    from InkOCR import calc_from_latex, plot_from_latex, solve_system_from_latex_list
except ImportError:
    try:
        from InkOCR import calc_from_latex, plot_from_latex  # type: ignore
        solve_system_from_latex_list = None  # type: ignore
    except Exception as e:
        print(f"ERROR: Failed to import InkOCR: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """
    Main entry point for math CLI.

    Modes:
        calc  - Single expression calculation
        graph - Plot y=f(x) graph and save to file
        system - Solve system of equations
    """
    if len(sys.argv) < 3:
        print(
            "ERROR: Usage: math_cli.py <calc|graph|system> <expr_or_lines> [out_path]",
            file=sys.stderr,
        )
        sys.exit(1)

    mode = sys.argv[1]
    expr_or_lines = sys.argv[2]

    # Calculate single expression
    if mode == "calc":
        try:
            result = calc_from_latex(expr_or_lines)
        except Exception as e:
            print(f"ERROR: calc_from_latex failed: {e}", file=sys.stderr)
            sys.exit(1)

        out = (str(result) + "\n").encode("utf-8", errors="replace")
        sys.stdout.buffer.write(out)
        sys.stdout.flush()
        sys.exit(0)

    # Generate graph
    if mode == "graph":
        if len(sys.argv) >= 4:
            out_path = sys.argv[3]
        else:
            out_path = os.path.join(os.getcwd(), "graph.png")

        try:
            pil_img, err = plot_from_latex(expr_or_lines, x_range=(-10, 10))
        except Exception as e:
            print(f"ERROR: plot_from_latex failed: {e}", file=sys.stderr)
            sys.exit(1)

        if pil_img is None:
            print(f"ERROR: {err or 'Unknown error'}", file=sys.stderr)
            sys.exit(1)

        # Save graph to file
        try:
            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            pil_img.save(out_path, format="PNG")
        except Exception as e:
            print(f"ERROR: Failed to save graph: {e}", file=sys.stderr)
            sys.exit(1)

        # Output path to stdout
        out = (out_path + "\n").encode("utf-8", errors="replace")
        sys.stdout.buffer.write(out)
        sys.stdout.flush()
        sys.exit(0)

    # Solve system of equations
    if mode == "system":
        if solve_system_from_latex_list is None:
            print(
                "ERROR: solve_system_from_latex_list not available. "
                "Update InkOCR.py to the latest version.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Split by newlines
        lines = [line for line in expr_or_lines.splitlines() if line.strip()]

        if not lines:
            print("ERROR: Empty equation list", file=sys.stderr)
            sys.exit(1)

        try:
            text = solve_system_from_latex_list(lines)  # type: ignore
        except Exception as e:
            print(f"ERROR: System solve failed: {e}", file=sys.stderr)
            sys.exit(1)

        out = (str(text) + "\n").encode("utf-8", errors="replace")
        sys.stdout.buffer.write(out)
        sys.stdout.flush()
        sys.exit(0)

    # Invalid mode
    print("ERROR: Mode must be 'calc', 'graph', or 'system'", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
