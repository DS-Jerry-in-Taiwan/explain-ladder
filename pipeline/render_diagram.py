#!/usr/bin/env python3
"""L2: render diagram.mmd -> diagram.svg (+ diagram.png) with mmdc."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
PUPPETEER_JSON = os.path.join(PROJECT, "assets", "puppeteer.json")


def render(mmd_path, out_dir, scale=2):
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, "diagram")
    svg, png = base + ".svg", base + ".png"
    common = ["mmdc", "--puppeteerConfigFile", PUPPETEER_JSON,
              "-i", mmd_path, "-b", "white"]
    r1 = subprocess.run(common + ["-o", svg], capture_output=True, text=True)
    if r1.returncode != 0 or not os.path.exists(svg):
        sys.exit("mmdc SVG failed:\n" + r1.stderr[-2000:])
    r2 = subprocess.run(common + ["-o", png, "-s", str(scale)],
                        capture_output=True, text=True)
    if r2.returncode != 0 or not os.path.exists(png):
        sys.exit("mmdc PNG failed:\n" + r2.stderr[-2000:])
    return svg, png


if __name__ == "__main__":
    svg, png = render(sys.argv[1], sys.argv[2])
    print("diagram:", svg, png)
