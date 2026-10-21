#!/usr/bin/env python3
"""Explain Ladder MCP server (v1, stdio transport).

Wraps the explain-ladder pipeline (L2 diagram / L3 interactive page /
L4 manim explainer video) as MCP tools that any agent can call.

Tools:
  explain_spec   -> the authoring spec calling agents must follow
  explain_start  -> validate inputs, launch a render job (async), return job_id
  explain_status -> poll a job
  explain_result -> collect output file paths when done

Run with this dir's venv:  mcp/.venv/bin/python mcp/server.py
"""
import ast
import json
import os
import re
import subprocess
import sys
import time
import uuid

from mcp.server.fastmcp import FastMCP

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
JOBS_DIR = os.path.join(PROJECT, "mcp_jobs")
VENV_PY = os.path.join(PROJECT, ".venv", "bin", "python")
RUNNER = os.path.join(HERE, "runner.py")

mcp = FastMCP("explain-ladder")

SPEC = """# Explain Ladder — authoring spec for calling agents

You provide the content; the tool renders it deterministically.
A render job takes three content inputs (plus one optional file):

## brief_md  (used by L1 text and the L3 page)
- First line MUST be `# Title` — it becomes the page title.
- Body in ASD-STE100 style: short sentences, one idea per sentence,
  plain words. Markdown is allowed below the title.

## diagram_mmd  (L2 diagram)
- Must be valid Mermaid syntax (rendered by mermaid-cli).
- Quote node labels that contain special characters; use \\n for
  line breaks inside labels.

## narration_txt  (L4 narration, also the L3 step guide)
- Plain text. Paragraphs separated by a blank line.
- ONE paragraph = ONE video scene = one TTS segment.
- HARD RULE: the paragraph count must equal the number of scenes
  (SCENE_CLASSES) used for the video.

## manim_scenes_py  (optional; effectively required for L4 on new topics)
- Python source defining SCENE_CLASSES = ["SceneA", ...] with one
  Manim Scene subclass per narration paragraph, in order.
- Scenes are rendered at 720p30; each scene's duration is driven by
  its TTS audio length (SCENE_DUR), do not hardcode total duration.
- If omitted, the pipeline's built-in scenes are used. Those are
  RAG-themed and there are exactly 4, so narration must then have
  exactly 4 paragraphs — and the visuals will be the RAG demo visuals.

## glossary  (optional, for the L3 page)
- A list of [term, definition] pairs. If omitted, a built-in
  RAG glossary is used (wrong for other topics — provide your own).

## levels
- Subset of ["L2", "L3", "L4"]. L2 (diagram) is always rendered
  because L3 needs the SVG and L4 needs the PNG.
- L4 (video) takes minutes; L2+L3 finish in seconds.

## Call protocol (async)
1. explain_start(...) -> {job_id, warnings}
2. explain_status(job_id) until state is "done" or "failed"
3. explain_result(job_id) -> output file paths
Validation errors are returned in plain language so you can fix the
input and call explain_start again.
"""


def _job_dir(job_id):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", job_id or ""):
        raise ValueError(f"invalid job_id: {job_id!r}")
    return os.path.join(JOBS_DIR, job_id)


def _load_job(job_id):
    d = _job_dir(job_id)
    p = os.path.join(d, "job.json")
    if not os.path.exists(p):
        raise ValueError(f"unknown job_id: {job_id}")
    with open(p, encoding="utf-8") as f:
        return d, json.load(f)


def _scene_count(manim_scenes_py):
    tree = ast.parse(manim_scenes_py)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "SCENE_CLASSES":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        return len(node.value.elts)
    return None


@mcp.tool()
def explain_spec() -> str:
    """Return the authoring spec an agent must follow to call the
    explain-ladder render tools: input formats for brief_md,
    diagram_mmd, narration_txt and manim_scenes_py, the hard
    paragraph/scene-count rule, and the async call protocol."""
    return SPEC


@mcp.tool()
def explain_start(name: str, brief_md: str, diagram_mmd: str,
                  narration_txt: str, manim_scenes_py: str = "",
                  glossary: list = None, levels: list = None) -> str:
    """Start an explain-ladder render job (async).

    name: slug for the topic, [a-z0-9][a-z0-9-_]*.
    brief_md: markdown, first line '# Title', ASD-STE100 style body.
    diagram_mmd: valid Mermaid source for the L2 diagram.
    narration_txt: plain text, blank-line separated paragraphs;
        one paragraph per video scene.
    manim_scenes_py: optional Python defining SCENE_CLASSES (one
        Manim Scene per narration paragraph). Required in practice
        for L4 on any new topic; without it the built-in 4 RAG scenes
        are used and narration must have exactly 4 paragraphs.
    glossary: optional list of [term, definition] pairs for L3.
    levels: subset of ["L2","L3","L4"], default all three.
    Returns JSON with job_id and warnings. Poll explain_status, then
    collect files with explain_result."""
    levels = levels or ["L2", "L3", "L4"]
    bad = [lv for lv in levels if lv not in ("L2", "L3", "L4")]
    if bad:
        raise ValueError(f"unknown levels: {bad}; allowed: L2, L3, L4")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-_]*", name or ""):
        raise ValueError("name must be a slug: [a-z0-9][a-z0-9-_]*")
    if not brief_md.lstrip().startswith("# "):
        raise ValueError("brief_md must start with a '# Title' line")
    if not diagram_mmd.strip():
        raise ValueError("diagram_mmd is empty; provide valid Mermaid source")

    paras = [p.strip() for p in narration_txt.strip().split("\n\n") if p.strip()]
    if not paras:
        raise ValueError("narration_txt is empty; provide at least one paragraph")

    warnings = []
    if "L4" in levels:
        if manim_scenes_py.strip():
            n = _scene_count(manim_scenes_py)
            if n is None:
                raise ValueError(
                    "manim_scenes_py must define SCENE_CLASSES = [...]")
            if n != len(paras):
                raise ValueError(
                    f"narration has {len(paras)} paragraphs but SCENE_CLASSES "
                    f"has {n} scenes; they must be equal (one scene per paragraph)")
        else:
            if len(paras) != 4:
                raise ValueError(
                    f"no manim_scenes_py given: built-in scenes are exactly 4, "
                    f"but narration has {len(paras)} paragraphs. Either provide "
                    f"manim_scenes_py or use exactly 4 paragraphs.")
            warnings.append(
                "L4 will use the built-in RAG-themed scenes; visuals may not "
                "match a non-RAG topic.")

    job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + name + "-" + uuid.uuid4().hex[:6]
    d = _job_dir(job_id)
    topic = os.path.join(d, "topic")
    out = os.path.join(d, "out")
    os.makedirs(topic, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(topic, "brief.md"), "w", encoding="utf-8") as f:
        f.write(brief_md)
    with open(os.path.join(topic, "diagram.mmd"), "w", encoding="utf-8") as f:
        f.write(diagram_mmd)
    with open(os.path.join(topic, "narration.txt"), "w", encoding="utf-8") as f:
        f.write(narration_txt)
    if manim_scenes_py.strip():
        with open(os.path.join(topic, "manim_scenes.py"), "w", encoding="utf-8") as f:
            f.write(manim_scenes_py)
    if glossary:
        with open(os.path.join(topic, "glossary.json"), "w", encoding="utf-8") as f:
            json.dump(glossary, f, ensure_ascii=False)

    job = {"job_id": job_id, "name": name, "levels": levels,
           "state": "running", "step": "queued",
           "topic_dir": topic, "out_dir": out, "outputs": {},
           "warnings": warnings, "error": None}
    with open(os.path.join(d, "job.json"), "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)

    log = open(os.path.join(d, "run.log"), "ab")
    proc = subprocess.Popen(
        [VENV_PY, RUNNER, d], stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True)
    job["pid"] = proc.pid
    with open(os.path.join(d, "job.json"), "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)

    return json.dumps({"job_id": job_id, "state": "running",
                       "warnings": warnings}, ensure_ascii=False)


@mcp.tool()
def explain_status(job_id: str) -> str:
    """Poll a render job. Returns JSON: state (running/done/failed),
    current step, and outputs produced so far."""
    d, job = _load_job(job_id)
    if job["state"] == "running":
        pid = job.get("pid")
        alive = False
        if pid:
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                alive = False
        if not alive:
            job["state"] = "failed"
            job["error"] = (job.get("error") or
                            "runner process ended without a final state; "
                            "see run.log")
    tail = ""
    logp = os.path.join(d, "run.log")
    if os.path.exists(logp):
        with open(logp, encoding="utf-8", errors="replace") as f:
            tail = f.read()[-800:]
    return json.dumps({"job_id": job_id, "state": job["state"],
                       "step": job.get("step"), "outputs": job.get("outputs", {}),
                       "log_tail": tail}, ensure_ascii=False)


@mcp.tool()
def explain_result(job_id: str) -> str:
    """Collect a finished job's outputs. Returns JSON with state and,
    for each output, its file path and size in bytes. If the job
    failed, includes the error excerpt."""
    d, job = _load_job(job_id)
    outs = {}
    for k, p in (job.get("outputs") or {}).items():
        outs[k] = {"path": p,
                   "bytes": os.path.getsize(p) if os.path.exists(p) else None}
    return json.dumps({"job_id": job_id, "state": job["state"],
                       "outputs": outs, "warnings": job.get("warnings", []),
                       "error": (job.get("error") or "")[-1500:] or None},
                      ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
