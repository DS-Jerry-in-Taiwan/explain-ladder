#!/usr/bin/env python3
"""Orchestrator: topic dir -> L2 diagram, L3 page, L4 video.

Usage: python3 pipeline/run.py <topic_dir> [--out out/<name>]
Topic dir needs: brief.md (L1), diagram.mmd (L2), narration.txt (L4).
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_VENV_DIR = os.path.join(os.path.dirname(_HERE), ".venv")
_VENV_PY = os.path.join(_VENV_DIR, "bin", "python")
# All pipeline deps (manim, piper, markdown, pillow) live in the project venv.
# Re-exec under it so `python3 pipeline/run.py` just works.
if os.path.exists(_VENV_PY) and os.path.realpath(sys.prefix) != os.path.realpath(_VENV_DIR):
    os.execv(_VENV_PY, [_VENV_PY] + sys.argv)

sys.path.insert(0, _HERE)
from render_diagram import render
from build_page import build as build_page
from build_video import build as build_video


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    topic = os.path.abspath(a.topic)
    name = os.path.basename(topic.rstrip("/"))
    out = os.path.abspath(a.out or os.path.join(
        os.path.dirname(_HERE), "out", name))
    for f in ("brief.md", "diagram.mmd", "narration.txt"):
        if not os.path.exists(os.path.join(topic, f)):
            sys.exit(f"missing input: {f}")

    print(f"== L2 diagram ==")
    svg, png = render(os.path.join(topic, "diagram.mmd"), out)
    print("  ", svg, f"({os.path.getsize(svg)//1024} KB)")
    print("  ", png, f"({os.path.getsize(png)//1024} KB)")

    print("== L3 page ==")
    page = build_page(topic, out)
    print("  ", page, f"({os.path.getsize(page)//1024} KB)")

    print("== L4 video ==")
    video = build_video(topic, out, png)
    print("  ", video, f"({os.path.getsize(video)//1024} KB)")

    print(f"\nDone. Open {os.path.join(out, 'index.html')} and play {video}")


if __name__ == "__main__":
    main()
