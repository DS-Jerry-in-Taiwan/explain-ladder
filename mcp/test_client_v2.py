#!/usr/bin/env python3
"""Real MCP acceptance tests for the explain-ladder v2 additions."""
import ast
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
SERVER_PYTHON = HERE / ".venv" / "bin" / "python"
SERVER_PY = HERE / "server.py"
JOBS_DIR = PROJECT / "mcp_jobs"
PROJECT_PYTHON = PROJECT / ".venv" / "bin" / "python"
SUMMARY = []


def text_of(result):
    return "".join(c.text for c in result.content if hasattr(c, "text"))


def assert_tool_ok(result):
    assert not result.isError, text_of(result)
    return text_of(result)


def assert_tool_error(result, *needles):
    text = text_of(result)
    assert result.isError, f"expected MCP tool error, got: {text}"
    for needle in needles:
        assert needle.lower() in text.lower(), f"missing {needle!r}: {text}"
    return text


async def poll(session, job_id, timeout_s=1800):
    waited = 0
    while waited <= timeout_s:
        status = json.loads(assert_tool_ok(
            await session.call_tool("explain_status", {"job_id": job_id})))
        print(f"  {job_id}: {status['state']} / {status.get('step')}", flush=True)
        if status["state"] in ("done", "failed"):
            return status
        await asyncio.sleep(5)
        waited += 5
    raise AssertionError(f"job {job_id} did not finish within {timeout_s}s")


async def run_job(session, payload, timeout_s=1800):
    started = json.loads(assert_tool_ok(
        await session.call_tool("explain_start", payload)))
    assert started["state"] == "running"
    status = await poll(session, started["job_id"], timeout_s)
    result = json.loads(assert_tool_ok(
        await session.call_tool("explain_result", {"job_id": started["job_id"]})))
    assert result["state"] == status["state"]
    return started["job_id"], status, result


def read_job(job_id):
    with open(JOBS_DIR / job_id / "job.json", encoding="utf-8") as f:
        return json.load(f)


def output_path(result, key):
    assert key in result["outputs"], (key, result)
    path = Path(result["outputs"][key]["path"])
    assert path.is_file() and path.stat().st_size > 0, path
    return path


def ffprobe_duration(path):
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(path)], text=True)
    duration = float(json.loads(raw)["format"]["duration"])
    assert duration > 0, (path, duration)
    return duration


def image_size(path):
    code = ("from PIL import Image; import json, sys; "
            "print(json.dumps(Image.open(sys.argv[1]).size))")
    raw = subprocess.check_output([str(PROJECT_PYTHON), "-c", code, str(path)],
                                  text=True)
    size = tuple(json.loads(raw))
    assert size[0] > 0 and size[1] > 0
    return size


def job_dirs():
    if not JOBS_DIR.exists():
        return set()
    return {p.name for p in JOBS_DIR.iterdir() if p.is_dir()}


def chinese_payload(name, levels=("L2", "L3", "L4")):
    return {
        "name": name,
        "brief_md": "# 檢索增強生成\n\n這個系統根據文件回答問題。",
        "diagram_mmd": 'flowchart LR\n A["文件"] --> B["嵌入向量"] --> C["答案"]',
        "narration_txt": (
            "這是檢索增強生成。它讓語言模型根據你的文件回答問題，而不只依靠記憶。\n\n"
            "先把文件切成小片段。把每個片段轉成嵌入向量，再存進向量資料庫。\n\n"
            "使用者提出問題時，也把問題轉成向量。搜尋資料庫，找出最相關的文件片段。\n\n"
            "最後，把問題和找到的片段交給語言模型。模型根據這些資料產生答案，讓回答有所依據。"
        ),
        "glossary": [["文件片段", "文件中的一小段內容。"]],
        "levels": list(levels),
        "lang": "zh",
    }


def assert_page_zh(path, expected_text):
    page = path.read_text(encoding="utf-8")
    for needle in ('lang="zh-Hant"', "互動式講解", "閱讀", "圖解", "逐步導覽",
                   "術語表", "← 上一步", "下一步 →", "步驟 1 /",
                   "Noto Sans CJK TC", expected_text):
        assert needle in page, f"missing page assertion: {needle}"
    return page


def normalize_color(value):
    value = value.strip().lower()
    if value.startswith("#"):
        if len(value) == 4:
            return "#" + "".join(c * 2 for c in value[1:])
        if len(value) == 7:
            return value
    match = re.fullmatch(
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,[^)]*)?\s*\)", value)
    if match:
        return "#%02x%02x%02x".format(*(int(x) for x in match.groups()))
    return value


def css_declarations(text):
    return {key.strip().lower(): value.strip()
            for key, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", text)}


def node_fills(svg_path):
    root = ET.parse(svg_path).getroot()
    parent = {child: node for node in root.iter() for child in node}
    style_text = "\n".join(
        node.text or "" for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] == "style")
    rules = []
    for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]+)\}", style_text):
        decl = css_declarations(declarations)
        if "fill" in decl:
            rules.append((selectors.lower(), normalize_color(decl["fill"])))
    fills = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "rect":
            continue
        ancestors = []
        current = node
        while current in parent:
            current = parent[current]
            ancestors.append(current)
        classes = " ".join(n.attrib.get("class", "")
                            for n in [node] + ancestors).lower()
        if not any(x in classes for x in ("node", "label-container", "basic")):
            continue
        if "fill" in node.attrib:
            fills.append(normalize_color(node.attrib["fill"]))
        fills.extend(normalize_color(v) for k, v in css_declarations(
            node.attrib.get("style", "")).items() if k == "fill")
        for selectors, fill in rules:
            if any(x in selectors for x in (".node", ".basic", ".label-container")):
                fills.append(fill)
    return set(fills)


def direct_validation_tests(base_payload):
    sys.path.insert(0, str(HERE))
    import server

    before = job_dirs()
    circular = {}
    circular["self"] = circular
    cases = [
        ({"mermaid_theme_variables": {"bad": {1: "key"}}}, "keys"),
        ({"mermaid_theme_variables": circular}, "serializable"),
        ({"mermaid_theme_variables": float("nan")}, "dict"),
        ({"lang": "fr"}, "lang"),
        ({"tts_engine": "wat"}, "tts_engine"),
        ({"tts_voice": ""}, "tts_voice"),
        ({"mermaid_theme": "wat"}, "theme"),
        ({"diagram_scale": 0}, "scale"),
        ({"diagram_scale": -1}, "scale"),
        ({"diagram_scale": True}, "scale"),
    ]
    for index, (overrides, needle) in enumerate(cases):
        payload = dict(base_payload)
        payload.update(overrides)
        payload["name"] = f"direct-invalid-{index}"
        try:
            server.explain_start(**payload)
        except (ValueError, TypeError) as exc:
            assert needle.lower() in str(exc).lower(), str(exc)
        else:
            raise AssertionError(f"direct validation accepted {overrides}")
    assert job_dirs() == before, "direct validation created a job directory"
    SUMMARY.append("C direct validation: invalid option cases rejected pre-launch")


def direct_tts_stub_tests():
    sys.path.insert(0, str(PROJECT / "pipeline"))
    import build_video

    voice = "zh-TW-HsiaoChenNeural"
    original_run = build_video.subprocess.run

    def check(message, stage):
        for token in ("engine=edge", f"voice={voice}", "paragraph=1", stage):
            assert token in message, message

    with tempfile.TemporaryDirectory() as work:
        def nonzero(cmd, **kwargs):
            return type("Result", (), {"returncode": 7, "stderr": "stub network error"})()
        build_video.subprocess.run = nonzero
        try:
            build_video.tts_wavs(["一段"], work, lang="zh", tts_engine="edge", tts_voice=voice)
        except RuntimeError as exc:
            check(str(exc), "synthesis")
        else:
            raise AssertionError("nonzero edge stub did not fail")

        def timed_out(cmd, **kwargs):
            raise build_video.subprocess.TimeoutExpired(
                cmd, kwargs.get("timeout"), stderr="stub timeout")
        build_video.subprocess.run = timed_out
        try:
            build_video.tts_wavs(["一段"], work, lang="zh", tts_engine="edge", tts_voice=voice)
        except RuntimeError as exc:
            check(str(exc), "synthesis")
        else:
            raise AssertionError("timeout edge stub did not fail")

        def empty_mp3(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b"")
            return type("Result", (), {"returncode": 0, "stderr": ""})()
        build_video.subprocess.run = empty_mp3
        try:
            build_video.tts_wavs(["一段"], work, lang="zh", tts_engine="edge", tts_voice=voice)
        except RuntimeError as exc:
            check(str(exc), "synthesis")
        else:
            raise AssertionError("empty MP3 edge stub did not fail")

        def ffmpeg_failure(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                raise build_video.subprocess.CalledProcessError(
                    1, cmd, stderr="stub ffmpeg error")
            Path(cmd[-1]).write_bytes(b"not-empty")
            return type("Result", (), {"returncode": 0, "stderr": ""})()
        build_video.subprocess.run = ffmpeg_failure
        try:
            build_video.tts_wavs(["一段"], work, lang="zh", tts_engine="edge", tts_voice=voice)
        except RuntimeError as exc:
            check(str(exc), "wav conversion")
        else:
            raise AssertionError("ffmpeg edge stub did not fail")
    build_video.subprocess.run = original_run
    SUMMARY.append("C direct TTS stubs: nonzero, timeout, empty MP3, ffmpeg failure readable")


def default_compatibility_tests():
    sys.path.insert(0, str(HERE))
    import server
    assert server.SPEC == server.explain_spec() == server.explain_spec(lang="en")
    old_source = subprocess.check_output(
        ["git", "show", "18d838b:mcp/server.py"], cwd=PROJECT, text=True)
    old_tree = ast.parse(old_source)
    old_spec = next(node.value.value for node in old_tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "SPEC"
                            for t in node.targets))
    assert server.SPEC == old_spec
    zh = server.explain_spec(lang="zh")
    for phrase in ("中文白話", "scene", "EXPLAIN_LANG", "EXPLAIN_FONT"):
        assert phrase in zh

    with tempfile.TemporaryDirectory() as temp:
        topic = Path(temp) / "topic"
        out = Path(temp) / "out"
        shutil.copytree(PROJECT / "demo" / "rag", topic)
        out.mkdir()
        shutil.copy(PROJECT / "out" / "rag" / "diagram.svg", out / "diagram.svg")
        sys.path.insert(0, str(PROJECT / "pipeline"))
        from build_page import build
        generated = Path(build(str(topic), str(out)))
        baseline = PROJECT / "out" / "rag" / "index.html"
        assert baseline.exists() and generated.read_bytes() == baseline.read_bytes()

    import render_diagram
    with tempfile.TemporaryDirectory() as temp:
        calls = []
        original_run = render_diagram.subprocess.run
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"output")
            return type("Result", (), {"returncode": 0, "stderr": ""})()
        render_diagram.subprocess.run = fake_run
        try:
            render_diagram.render("input.mmd", temp)
        finally:
            render_diagram.subprocess.run = original_run
        assert len(calls) == 2
        assert all("-t" not in call and "-c" not in call for call in calls)
        assert calls[1][-2:] == ["-s", "2"]
    SUMMARY.append("C compatibility: English SPEC/page bytes and default render argv match v1")


async def stub_failure_job():
    payload = {
        "name": "edge-stub-failure", "brief_md": "# Stub failure\n\n短文。",
        "diagram_mmd": 'flowchart LR\n A["起點"] --> B["終點"]',
        "narration_txt": "一步。", "manim_scenes_py": 'SCENE_CLASSES = ["Never"]',
        "levels": ["L2", "L3", "L4"], "lang": "zh",
        "tts_engine": "edge", "tts_voice": "zh-TW-HsiaoChenNeural"}
    with tempfile.TemporaryDirectory() as temp:
        Path(temp, "edge_tts.py").write_text(
            "import sys\nprint('stub edge failure', file=sys.stderr)\nsys.exit(7)\n",
            encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=temp, EXPLAIN_EDGE_STUB="nonzero")
        params = StdioServerParameters(
            command=str(SERVER_PYTHON), args=[str(SERVER_PY)], env=env)
        async with stdio_client(params) as (read_s, write_s):
            async with ClientSession(read_s, write_s) as session:
                await session.initialize()
                job_id, status, result = await run_job(session, payload, timeout_s=300)
                assert status["state"] == "failed"
                assert "video_mp4" not in result["outputs"]
                assert {"diagram_svg", "diagram_png", "page_html"} <= result["outputs"].keys()
                error = result["error"] or ""
                for needle in ("engine=edge", "zh-TW-HsiaoChenNeural", "paragraph=1", "synthesis"):
                    assert needle in error, error
                log = (JOBS_DIR / job_id / "run.log").read_text(
                    encoding="utf-8", errors="replace")
                assert "stub edge failure" in log
                SUMMARY.append(
                    f"C failed job {job_id}: readable edge synthesis failure; L2/L3 retained")


async def main():
    params = StdioServerParameters(command=str(SERVER_PYTHON), args=[str(SERVER_PY)])
    async with stdio_client(params) as (read_s, write_s):
        async with ClientSession(read_s, write_s) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            assert {"explain_spec", "explain_start", "explain_status", "explain_result"} <= tools.keys()
            schema = tools["explain_start"].inputSchema
            required = set(schema.get("required", []))
            assert {"name", "brief_md", "diagram_mmd", "narration_txt"} <= required
            for name in ("lang", "tts_engine", "tts_voice", "mermaid_theme",
                         "mermaid_theme_variables", "diagram_background", "diagram_scale"):
                assert name not in required, (name, schema)

            assert_tool_error(await session.call_tool("explain_spec", {"lang": "fr"}), "lang")
            before = job_dirs()
            for value in (["bad"], "bad"):
                bad = chinese_payload("invalid-vars", levels=("L2",))
                bad["mermaid_theme_variables"] = value
                assert_tool_error(
                    await session.call_tool("explain_start", bad),
                    "mermaid_theme_variables")
            assert job_dirs() == before
            SUMMARY.append("C MCP schema/errors: optional fields are optional; invalid vars create no job")

            # A: exact four-paragraph Chinese narration with default zh edge voice.
            chinese_id, chinese_status, chinese_result = await run_job(
                session, chinese_payload("zh-rag-e2e"), timeout_s=2400)
            assert chinese_status["state"] == "done", chinese_status
            chinese_job = read_job(chinese_id)
            assert chinese_job["lang"] == "zh"
            assert chinese_job["tts_engine"] == "edge"
            assert chinese_job["tts_voice"] == "zh-TW-HsiaoChenNeural"
            page = output_path(chinese_result, "page_html")
            assert_page_zh(page, "這是檢索增強生成")
            video = output_path(chinese_result, "video_mp4")
            duration = ffprobe_duration(video)
            for i in range(4):
                wav = JOBS_DIR / chinese_id / "out" / "_video_work" / f"seg{i}.wav"
                assert wav.is_file()
                with wave.open(str(wav)) as wf:
                    assert wf.getnframes() / wf.getframerate() > 0
            log = (JOBS_DIR / chinese_id / "run.log").read_text(
                encoding="utf-8", errors="replace")
            assert "TTS engine=edge voice=zh-TW-HsiaoChenNeural" in log
            # Automated duration checks substitute for manual listening.
            SUMMARY.append(
                f"A Chinese L4 {chinese_id}: done, MP4 {duration:.2f}s, 4 positive WAV durations, voice logged")

            font_code = (
                "import os; os.environ['EXPLAIN_LANG']='zh'; "
                "os.environ['EXPLAIN_FONT']='Noto Sans CJK TC'; "
                "import manim_scenes; assert manim_scenes.FONT == 'Noto Sans CJK TC'; "
                "print(manim_scenes.FONT)"
            )
            font_out = subprocess.check_output(
                [str(PROJECT_PYTHON), "-c", font_code],
                cwd=PROJECT / "pipeline", text=True)
            assert "Noto Sans CJK TC" in font_out

            topic_scene = '''import os\nfrom manim import *\n\nIMPORT_LANG = os.environ.get("EXPLAIN_LANG")\nIMPORT_FONT = os.environ.get("EXPLAIN_FONT")\n\nclass TopicScene(Scene):\n    def construct(self):\n        assert os.environ.get("EXPLAIN_LANG") == "zh"\n        assert os.environ.get("EXPLAIN_FONT") == "Noto Sans CJK TC"\n        self.add(Text("中文測試", font=os.environ["EXPLAIN_FONT"]))\n        self.wait(float(os.environ.get("SCENE_DUR", "1")))\n\nSCENE_CLASSES = ["TopicScene"]\n'''
            smoke = chinese_payload("zh-topic-env", levels=("L2", "L3", "L4"))
            smoke["narration_txt"] = "這是一個中文主題場景。"
            smoke["manim_scenes_py"] = topic_scene
            smoke_id, smoke_status, smoke_result = await run_job(
                session, smoke, timeout_s=1200)
            assert smoke_status["state"] == "done", smoke_status
            smoke_video = output_path(smoke_result, "video_mp4")
            assert ffprobe_duration(smoke_video) > 0
            smoke_log = (JOBS_DIR / smoke_id / "run.log").read_text(
                encoding="utf-8", errors="replace")
            assert "missing glyph" not in smoke_log.lower()
            SUMMARY.append(
                f"A topic env smoke {smoke_id}: custom Chinese scene rendered; no missing-glyph warning")

            # B: baseline and custom theme jobs, plus same-preset scale comparison.
            diagram = 'flowchart LR\n A["起點"] --> B["終點"]'
            base_payload = {
                "name": "diagram-base", "brief_md": "# 圖解測試\n\n短文。",
                "diagram_mmd": diagram, "narration_txt": "一步。",
                "levels": ["L2", "L3"]}
            base_id, base_status, base_result = await run_job(session, base_payload)
            assert base_status["state"] == "done"
            custom_payload = dict(base_payload)
            custom_payload.update({
                "name": "diagram-custom", "mermaid_theme": "base",
                "mermaid_theme_variables": {
                    "primaryColor": "#ff00aa", "primaryBorderColor": "#112233"},
                "diagram_background": "#faf0e6", "diagram_scale": 3})
            custom_id, custom_status, custom_result = await run_job(
                session, custom_payload)
            assert custom_status["state"] == "done"
            scale_payload = dict(base_payload)
            scale_payload.update({"name": "diagram-scale", "diagram_scale": 3})
            scale_id, scale_status, scale_result = await run_job(session, scale_payload)
            assert scale_status["state"] == "done"

            base_svg = output_path(base_result, "diagram_svg")
            custom_svg = output_path(custom_result, "diagram_svg")
            base_svg_text = base_svg.read_text(encoding="utf-8").lower()
            custom_svg_text = custom_svg.read_text(encoding="utf-8").lower()
            assert "#ff00aa" not in base_svg_text
            assert "#faf0e6" in custom_svg_text
            assert "#ff00aa" in node_fills(custom_svg)
            custom_job = read_job(custom_id)
            config = JOBS_DIR / custom_id / "out" / "mermaid-config.json"
            assert json.loads(config.read_text(encoding="utf-8")) == {
                "themeVariables": {
                    "primaryColor": "#ff00aa", "primaryBorderColor": "#112233"}}
            custom_page = output_path(custom_result, "page_html").read_text(encoding="utf-8")
            assert custom_svg.read_text(encoding="utf-8") in custom_page
            assert custom_job["diagram_scale"] == 3
            base_size = image_size(output_path(base_result, "diagram_png"))
            scale_size = image_size(output_path(scale_result, "diagram_png"))
            assert abs(scale_size[0] - base_size[0] * 1.5) <= 2
            assert abs(scale_size[1] - base_size[1] * 1.5) <= 2
            SUMMARY.append(
                f"B diagram jobs {base_id}/{custom_id}/{scale_id}: themed fill, config, SVG embedding, scale {base_size}->{scale_size}")

            direct_validation_tests(dict(base_payload, levels=["L2"]))
            direct_tts_stub_tests()
            default_compatibility_tests()

    await stub_failure_job()


if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("\nV2 TEST SUMMARY")
        for item in SUMMARY:
            print("PASS", item)
        print(f"All {len(SUMMARY)} v2 checks passed.")
    except Exception as exc:
        print(f"V2 TEST FAILURE: {exc}", file=sys.stderr)
        raise
