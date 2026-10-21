#!/usr/bin/env python3
"""Job runner for the explain-ladder MCP server.

Executed with the project venv python (pipeline deps live there).
Usage: runner.py <job_dir>
Reads job.json in the job dir, renders the requested levels, and keeps
job.json updated (state/step/outputs/error). Stdout/stderr go to run.log.
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
PIPELINE = os.path.join(PROJECT, "pipeline")
sys.path.insert(0, PIPELINE)

# mmdc (mermaid-cli) is installed as a local npm dep under mcp/node_modules;
# the pipeline calls bare `mmdc`, so put its bin dir on PATH.
_MMDC_BIN = os.path.join(HERE, "node_modules", ".bin")
if os.path.isdir(_MMDC_BIN):
    os.environ["PATH"] = _MMDC_BIN + os.pathsep + os.environ.get("PATH", "")


def save(job_dir, job):
    with open(os.path.join(job_dir, "job.json"), "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)


def main():
    job_dir = os.path.abspath(sys.argv[1])
    with open(os.path.join(job_dir, "job.json"), encoding="utf-8") as f:
        job = json.load(f)
    topic = job["topic_dir"]
    out = job["out_dir"]
    levels = job["levels"]
    os.makedirs(out, exist_ok=True)

    from render_diagram import render
    from build_page import build as build_page
    from build_video import build as build_video

    outputs = {}
    try:
        # L2 is a dependency of both L3 (needs diagram.svg) and L4 (needs png).
        job["step"] = "L2 diagram"
        save(job_dir, job)
        print("== L2 diagram ==", flush=True)
        svg, png = render(
            os.path.join(topic, "diagram.mmd"), out,
            scale=job.get("diagram_scale", 2),
            theme=job.get("mermaid_theme", "default"),
            theme_variables=job.get("mermaid_theme_variables"),
            background=job.get("diagram_background", "white"))
        outputs["diagram_svg"] = svg
        outputs["diagram_png"] = png
        job["outputs"] = outputs
        save(job_dir, job)

        if "L3" in levels:
            job["step"] = "L3 page"
            save(job_dir, job)
            print("== L3 page ==", flush=True)
            outputs["page_html"] = build_page(
                topic, out, lang=job.get("lang", "en"))
            job["outputs"] = outputs
            save(job_dir, job)

        if "L4" in levels:
            job["step"] = "L4 video"
            save(job_dir, job)
            print("== L4 video ==", flush=True)
            outputs["video_mp4"] = build_video(
                topic, out, png, lang=job.get("lang", "en"),
                tts_engine=job.get("tts_engine"),
                tts_voice=job.get("tts_voice"))
            job["outputs"] = outputs
            save(job_dir, job)

        job["state"] = "done"
        job["step"] = "done"
        save(job_dir, job)
        print("DONE", flush=True)
    except Exception:
        job["state"] = "failed"
        job["error"] = traceback.format_exc()[-3000:]
        save(job_dir, job)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
