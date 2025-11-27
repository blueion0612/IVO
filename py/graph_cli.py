#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Graph CLI - Function Plotting for Electron

Generates y=f(x) graphs from mathematical expressions and saves as PNG.
Delegates to math_cli.py for actual plotting.

Usage:
    python graph_cli.py "x**2 + 1" "C:\\temp\\graph.png"
"""

import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main():
    """Main entry point for graph CLI."""
    if len(sys.argv) != 3:
        print("ERROR: Usage: graph_cli.py <expr> <out_path>", file=sys.stderr)
        sys.exit(1)

    expr = sys.argv[1]
    out_path = sys.argv[2]

    # Delegate to math_cli for actual graph generation
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, base_dir)
        from math_cli import main as math_main
    except Exception as e:
        print(f"ERROR: Failed to import math_cli: {e}", file=sys.stderr)
        sys.exit(1)

    # Reconstruct argv for math_cli graph mode
    sys.argv = [sys.argv[0], "graph", expr, out_path]
    math_main()


if __name__ == "__main__":
    main()
