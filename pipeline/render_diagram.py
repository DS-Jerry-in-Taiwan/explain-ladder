#!/usr/bin/env python3
"""L2: render diagram.mmd -> diagram.svg (+ diagram.png) with mmdc."""
import os
import json
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
PUPPETEER_JSON = os.path.join(PROJECT, "assets", "puppeteer.json")


def _validate_theme_variables(value):
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError(
            "theme_variables must be a JSON-serializable object: "
            "expected a dict or None")

    def check_keys(obj):
        if isinstance(obj, dict):
            for key, child in obj.items():
                if not isinstance(key, str):
                    raise ValueError(
                        "theme_variables must be a JSON-serializable object: "
                        "all object keys must be strings")
                check_keys(child)
        elif isinstance(obj, (list, tuple)):
            for child in obj:
                check_keys(child)

    try:
        check_keys(value)
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError(
            "theme_variables must be a JSON-serializable object: "
            f"{exc}") from exc


def render(mmd_path, out_dir, scale=2, *, theme="default",
           theme_variables=None, background="white"):
    if not isinstance(theme, str) or theme not in (
            "default", "dark", "forest", "neutral", "base"):
        raise ValueError(f"unknown mermaid theme: {theme!r}")
    if isinstance(scale, bool) or not isinstance(scale, int) or scale <= 0:
        raise ValueError("diagram scale must be a positive integer")
    if not isinstance(background, str) or not background:
        raise ValueError("diagram background must be a non-empty string")
    _validate_theme_variables(theme_variables)
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, "diagram")
    svg, png = base + ".svg", base + ".png"
    config = None
    if theme_variables:
        config = os.path.abspath(os.path.join(out_dir, "mermaid-config.json"))
        with open(config, "w", encoding="utf-8") as f:
            f.write(json.dumps({"themeVariables": theme_variables},
                               ensure_ascii=False))
    common = ["mmdc", "--puppeteerConfigFile", PUPPETEER_JSON,
              "-i", mmd_path, "-b", background]
    if theme != "default":
        common += ["-t", theme]
    if config is not None:
        common += ["-c", config]
    r1 = subprocess.run(common + ["-o", svg], capture_output=True, text=True)
    if r1.returncode != 0 or not os.path.exists(svg):
        raise RuntimeError("mmdc SVG failed:\n" + r1.stderr[-2000:])
    if background != "white":
        # Chromium/mmdc serializes CSS hex colors as rgb(...). Preserve the
        # caller's valid CSS spelling on the root SVG style so the shared
        # diagram asset visibly carries the requested background value.
        with open(svg, encoding="utf-8") as f:
            svg_text = f.read()
        svg_text = re.sub(
            r'(<svg\b[^>]*\bstyle="[^"\n]*\bbackground-color:\s*)'
            r'rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)',
            r'\1' + background,
            svg_text,
            count=1)
        with open(svg, "w", encoding="utf-8") as f:
            f.write(svg_text)
    r2 = subprocess.run(common + ["-o", png, "-s", str(scale)],
                        capture_output=True, text=True)
    if r2.returncode != 0 or not os.path.exists(png):
        raise RuntimeError("mmdc PNG failed:\n" + r2.stderr[-2000:])
    return svg, png


if __name__ == "__main__":
    svg, png = render(sys.argv[1], sys.argv[2])
    print("diagram:", svg, png)
