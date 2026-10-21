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
PIPELINE = os.path.join(PROJECT, "pipeline")
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

from build_video import resolve_tts_options

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

SPEC_ZH = """# Explain Ladder — 給呼叫代理的繁體中文 authoring spec

你提供內容；工具會以可重現的方式建立輸出。
一次 render job 接受三個內容輸入（以及一個可選檔案）：

## brief_md（用於 L1 文字與 L3 頁面）
- 第一行必須是 `# 標題`；它會成為頁面標題。
- 中文白話，使用短句，一句一個概念。不要求中文套用 ASD-STE100。
- Markdown 可在標題下方使用。

## diagram_mmd（L2 圖解）
- 必須是有效的 Mermaid 語法，由 mermaid-cli 渲染。
- 含特殊字元的中文 labels 請使用引號；需要換行時在 label 內使用 `\\n`。

## narration_txt（L4 旁白，也用於 L3 逐步導覽）
- 使用繁體中文純文字，以一個空白行分隔段落。
- 一段等於一個 scene，也等於一個 TTS segment。
- 段落數必須等於影片使用的 scene 數。

## manim_scenes_py（可選；新主題的 L4 實務上需要）
- Python source 必須定義 `SCENE_CLASSES = ["SceneA", ...]`，每個旁白段落依序對應一個 Manim Scene subclass。
- 若省略，會使用內建的 **4 個 English RAG scenes**。lang 只更換字型，不會翻譯場景文案；要使用全中文 visuals 或其他主題，請提供自己的 scenes 和中文 glossary，不要誤用 English RAG fallback glossary。
- topic scenes 可讀 `EXPLAIN_LANG`（`en` / `zh`）與解析後的 `EXPLAIN_FONT`；可用 `os.environ.get("EXPLAIN_FONT", "DejaVu Sans")` 指定 `Text(font=...)`。`SCENE_DUR` 約定不變。自行使用 `Tex`/`MathTex` 的 CJK 支援不在本次保證範圍。

## glossary（可選，用於 L3 頁面）
- `[term, definition]` pairs 的 list。省略時，中文頁面使用繁體中文 RAG glossary；自訂 glossary 優先。

## levels
- `L2`、`L3`、`L4` 的子集。L2 一定會渲染，因為 L3 需要 SVG、L4 需要 PNG。
- L4 影片可能需要數分鐘；L2+L3 通常數秒完成。

## 語言與 TTS / diagram 選項
- 呼叫 `explain_spec(lang="zh")` 只取得本規格，不設定 job；`explain_start` 仍必須傳 `lang="zh"`。
- `lang` 可為 `en` 或 `zh`。預設英文使用 Piper 與原 English voice；中文預設使用 edge-tts 的 `zh-TW-HsiaoChenNeural`。edge English voice 預設為 `en-US-AriaNeural`。
- 可明確傳 `tts_engine="piper"` 或 `"edge"`，以及對應的 `tts_voice`；中文 Piper 必須明確提供中文 `.onnx` 模型。
- `mermaid_theme` 可為 `default`、`dark`、`forest`、`neutral`、`base`；`mermaid_theme_variables` 是 Mermaid `themeVariables` object。`diagram_background` 傳給 Mermaid，`diagram_scale` 是 PNG scale，預設分別為 `white` 與 `2`。

## 呼叫協定（async）
1. `explain_start(...)` → `{job_id, warnings}`。
2. 持續呼叫 `explain_status(job_id)`，直到 state 是 `done` 或 `failed`。
3. `explain_result(job_id)` → 輸出檔案路徑。

validation errors 會以可讀文字回傳，修正輸入後再呼叫 `explain_start`。

旁白段落、scene-count、glossary、levels 與 async protocol 規則均與 English spec 相同。
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
def explain_spec(*, lang: str = "en") -> str:
    """Return the authoring spec an agent must follow to call the
    explain-ladder render tools: input formats for brief_md,
    diagram_mmd, narration_txt and manim_scenes_py, the hard
    paragraph/scene-count rule, and the async call protocol."""
    if lang == "en":
        return SPEC
    if lang == "zh":
        return SPEC_ZH
    raise ValueError("lang must be one of: en, zh")


def _validate_theme_variables(value):
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError(
            "mermaid_theme_variables must be a JSON-serializable object: "
            "expected a dict or None")

    def check_keys(obj):
        if isinstance(obj, dict):
            for key, child in obj.items():
                if not isinstance(key, str):
                    raise ValueError(
                        "mermaid_theme_variables must be a JSON-serializable "
                        "object: all object keys must be strings")
                check_keys(child)
        elif isinstance(obj, (list, tuple)):
            for child in obj:
                check_keys(child)

    try:
        check_keys(value)
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError(
            "mermaid_theme_variables must be a JSON-serializable object: "
            f"{exc}") from exc


def _validate_options(lang, tts_engine, tts_voice, mermaid_theme,
                      mermaid_theme_variables, diagram_background,
                      diagram_scale, levels):
    if not isinstance(lang, str) or lang not in ("en", "zh"):
        raise ValueError("lang must be one of: en, zh")
    if (not isinstance(mermaid_theme, str) or
            mermaid_theme not in ("default", "dark", "forest", "neutral", "base")):
        raise ValueError(
            "unknown mermaid_theme: {!r}; allowed: default, dark, forest, "
            "neutral, base".format(mermaid_theme))
    if not isinstance(diagram_background, str) or not diagram_background:
        raise ValueError("diagram_background must be a non-empty string")
    if isinstance(diagram_scale, bool) or not isinstance(diagram_scale, int) or diagram_scale <= 0:
        raise ValueError("diagram_scale must be a positive integer")
    _validate_theme_variables(mermaid_theme_variables)
    engine, voice = resolve_tts_options(
        lang=lang, tts_engine=tts_engine, tts_voice=tts_voice)
    if "L4" in levels and engine == "piper":
        if not (os.path.isfile(voice) and os.path.isfile(voice + ".json")):
            raise ValueError(
                "Piper voice model and matching .onnx.json must exist for L4: "
                f"{voice}")
    return engine, voice


@mcp.tool()
def explain_start(name: str, brief_md: str, diagram_mmd: str,
                  narration_txt: str, manim_scenes_py: str = "",
                  glossary: list = None, levels: list = None, *,
                  lang: str = "en", tts_engine: str | None = None,
                  tts_voice: str | None = None,
                  mermaid_theme: str = "default",
                  mermaid_theme_variables: dict | None = None,
                  diagram_background: str = "white",
                  diagram_scale: int = 2) -> str:
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

    # Keep every v2 option check before creating the job directory or starting
    # the runner.  resolve_tts_options also normalizes Piper paths.
    engine, voice = _validate_options(
        lang, tts_engine, tts_voice, mermaid_theme,
        mermaid_theme_variables, diagram_background, diagram_scale, levels)

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
           "warnings": warnings, "error": None,
           "lang": lang, "tts_engine": engine, "tts_voice": voice,
           "mermaid_theme": mermaid_theme,
           "mermaid_theme_variables": mermaid_theme_variables,
           "diagram_background": diagram_background,
           "diagram_scale": diagram_scale}
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
