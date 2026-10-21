#!/usr/bin/env python3
"""L4 v3: animated explainer video with manim.

Each narration paragraph -> one manim Scene (rendered via the manim CLI,
duration passed through SCENE_DUR) -> muxed with Piper TTS audio via ffmpeg
-> concatenated into explainer.mp4 (1280x720, h264 + aac).

Scene file resolution: <topic>/manim_scenes.py if present, else the
pipeline default pipeline/manim_scenes.py. The file must define
SCENE_CLASSES, one scene name per narration paragraph.
"""
import contextlib
import importlib.util
import os
import shutil
import subprocess
import sys
import wave
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
VOICE = os.path.join(PROJECT, "assets", "voices", "en_US-lessac-medium.onnx")
DEFAULT_SCENES = os.path.join(HERE, "manim_scenes.py")


def resolve_tts_options(*, lang="en", tts_engine=None, tts_voice=None):
    """Return validated, effective TTS engine and voice using stdlib only."""
    if not isinstance(lang, str) or lang not in ("en", "zh"):
        raise ValueError("lang must be one of: en, zh")
    if (tts_engine is not None and
            (not isinstance(tts_engine, str) or
             tts_engine not in ("piper", "edge"))):
        raise ValueError("tts_engine must be one of: piper, edge")
    if tts_voice is not None and (not isinstance(tts_voice, str) or not tts_voice):
        raise ValueError("tts_voice must be a non-empty string when provided")

    engine = tts_engine or ("edge" if lang == "zh" else "piper")
    if tts_voice is None:
        if engine == "edge":
            voice = "zh-TW-HsiaoChenNeural" if lang == "zh" else "en-US-AriaNeural"
        elif lang == "zh":
            raise ValueError(
                "lang='zh' with tts_engine='piper' requires tts_voice: "
                "provide a Chinese .onnx model or use edge")
        else:
            voice = VOICE
    else:
        voice = tts_voice

    if engine == "edge":
        if not re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}-[A-Za-z0-9]+Neural", voice):
            raise ValueError(
                "edge tts_voice must match a neural voice short name such as "
                "en-US-AriaNeural")
    else:
        if not os.path.isabs(voice):
            voice = os.path.abspath(os.path.join(PROJECT, voice))
        else:
            voice = os.path.abspath(voice)
    return engine, voice


def _font_for_lang(lang):
    if lang not in ("en", "zh"):
        raise ValueError("lang must be one of: en, zh")
    return "Noto Sans CJK TC" if lang == "zh" else "DejaVu Sans"


def manim_bin():
    p = os.path.join(PROJECT, ".venv", "bin", "manim")
    if os.path.exists(p):
        return p
    return shutil.which("manim") or "manim"


def load_scene_classes(scenes_file):
    spec = importlib.util.spec_from_file_location("topic_scenes", scenes_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SCENE_CLASSES


def _tail(value):
    if value is None:
        return ""
    return str(value)[-1500:]


def _tts_failure(engine, voice, index, stage, detail):
    return RuntimeError(
        f"TTS engine={engine} voice={voice} paragraph={index + 1} "
        f"stage={stage} failed: {_tail(detail)}")


def _edge_tts_wavs(paras, workdir, voice):
    wavs = []
    for i, paragraph in enumerate(paras):
        txt = os.path.join(workdir, f"seg{i}.txt")
        mp3 = os.path.join(workdir, f"seg{i}.mp3")
        wav = os.path.join(workdir, f"seg{i}.wav")
        with open(txt, "w", encoding="utf-8") as f:
            f.write(paragraph)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "edge_tts", "--file", txt,
                 "--voice", voice, "--write-media", mp3],
                capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise _tts_failure("edge", voice, i, "synthesis", exc.stderr) from exc
        if result.returncode != 0:
            raise _tts_failure("edge", voice, i, "synthesis", result.stderr)
        if not os.path.isfile(mp3) or os.path.getsize(mp3) == 0:
            raise _tts_failure("edge", voice, i, "synthesis", "MP3 is empty or missing")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", mp3, "-vn", "-ac", "1", "-ar", "24000",
                 "-c:a", "pcm_s16le", wav],
                capture_output=True, text=True, check=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            raise _tts_failure("edge", voice, i, "wav conversion", exc.stderr) from exc
        except subprocess.CalledProcessError as exc:
            raise _tts_failure("edge", voice, i, "wav conversion", exc.stderr) from exc
        if not os.path.isfile(wav) or os.path.getsize(wav) == 0:
            raise _tts_failure("edge", voice, i, "wav validation", "WAV is empty or missing")
        try:
            if wav_seconds(wav) <= 0:
                raise ValueError("WAV duration is zero")
        except Exception as exc:
            raise _tts_failure("edge", voice, i, "wav validation", exc) from exc
        wavs.append(wav)
    return wavs


def tts_wavs(paras, workdir, *, lang="en", tts_engine=None, tts_voice=None):
    engine, voice = resolve_tts_options(
        lang=lang, tts_engine=tts_engine, tts_voice=tts_voice)
    os.makedirs(workdir, exist_ok=True)
    if engine == "edge":
        return _edge_tts_wavs(paras, workdir, voice)

    from piper import PiperVoice
    piper_voice = PiperVoice.load(voice)
    wavs = []
    for i, paragraph in enumerate(paras):
        wav = os.path.join(workdir, f"seg{i}.wav")
        with wave.open(wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(piper_voice.config.sample_rate)
            piper_voice.synthesize_wav(paragraph, wf)
        wavs.append(wav)
    return wavs


def wav_seconds(path):
    with contextlib.closing(wave.open(path)) as wf:
        return wf.getnframes() / wf.getframerate()


def render_scene(scene_cls, scenes_file, dur, wav_path, seg_path, workdir, idx,
                 *, lang="en"):
    font = _font_for_lang(lang)
    env = dict(os.environ, EXPLAIN_LANG=lang, EXPLAIN_FONT=font,
               SCENE_DUR=f"{dur:.2f}")
    media = os.path.join(workdir, "manim_media")
    out_name = f"scene{idx}"
    r = subprocess.run(
        [manim_bin(), "-qm", "--format=mp4", "--media_dir", media,
         "-o", out_name, scenes_file, scene_cls],
        capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"manim {scene_cls} failed:\n" + r.stderr[-3000:])
    module = os.path.splitext(os.path.basename(scenes_file))[0]
    silent = os.path.join(media, "videos", module, "720p30", out_name + ".mp4")
    if not os.path.exists(silent):
        raise RuntimeError(f"manim output missing: {silent}")
    # mux narration; pad audio tail with silence to the full scene duration
    subprocess.run(
        ["ffmpeg", "-y", "-i", silent, "-i", wav_path,
         "-c:v", "copy", "-af", "apad", "-t", f"{dur:.2f}",
         "-c:a", "aac", "-b:a", "160k", seg_path],
        check=True, capture_output=True)


def build(topic_dir, out_dir, diagram_png=None, *, lang="en", tts_engine=None,
          tts_voice=None):
    font = _font_for_lang(lang)
    engine, voice = resolve_tts_options(
        lang=lang, tts_engine=tts_engine, tts_voice=tts_voice)
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(out_dir, "_video_work")
    os.makedirs(work, exist_ok=True)

    with open(os.path.join(topic_dir, "narration.txt"), encoding="utf-8") as f:
        paras = [p.strip() for p in f.read().strip().split("\n\n") if p.strip()]

    scenes_file = os.path.join(topic_dir, "manim_scenes.py")
    if not os.path.exists(scenes_file):
        scenes_file = DEFAULT_SCENES
    old_lang = os.environ.get("EXPLAIN_LANG")
    old_font = os.environ.get("EXPLAIN_FONT")
    os.environ["EXPLAIN_LANG"] = lang
    os.environ["EXPLAIN_FONT"] = font
    try:
        scene_classes = load_scene_classes(scenes_file)
    finally:
        if old_lang is None:
            os.environ.pop("EXPLAIN_LANG", None)
        else:
            os.environ["EXPLAIN_LANG"] = old_lang
        if old_font is None:
            os.environ.pop("EXPLAIN_FONT", None)
        else:
            os.environ["EXPLAIN_FONT"] = old_font
    assert len(scene_classes) == len(paras), \
        f"{len(paras)} narration paragraphs but {len(scene_classes)} scenes"

    print(f"TTS engine={engine} voice={voice}", flush=True)
    wavs = tts_wavs(paras, work, lang=lang, tts_engine=engine,
                    tts_voice=voice)
    segs = []
    for i, (cls, wav) in enumerate(zip(scene_classes, wavs)):
        dur = wav_seconds(wav) + 0.8
        seg = os.path.join(work, f"seg{i}.mp4")
        print(f"  manim {cls} ({dur:.1f}s)...", flush=True)
        render_scene(cls, scenes_file, dur, wav, seg, work, i, lang=lang)
        segs.append(seg)

    lst = os.path.join(work, "concat.txt")
    with open(lst, "w") as f:
        for s in segs:
            f.write(f"file '{s}'\n")
    out = os.path.join(out_dir, "explainer.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", out],
                   check=True, capture_output=True)
    shutil.rmtree(os.path.join(work, "manim_media"), ignore_errors=True)
    return out


if __name__ == "__main__":
    print("video:", build(sys.argv[1], sys.argv[2],
                          sys.argv[3] if len(sys.argv) > 3 else None))
