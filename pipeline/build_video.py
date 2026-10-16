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

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
VOICE = os.path.join(PROJECT, "assets", "voices", "en_US-lessac-medium.onnx")
DEFAULT_SCENES = os.path.join(HERE, "manim_scenes.py")


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


def tts_wavs(paras, workdir):
    from piper import PiperVoice
    voice = PiperVoice.load(VOICE)
    wavs = []
    for i, p in enumerate(paras):
        wav = os.path.join(workdir, f"seg{i}.wav")
        with wave.open(wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(voice.config.sample_rate)
            voice.synthesize_wav(p, wf)
        wavs.append(wav)
    return wavs


def wav_seconds(path):
    with contextlib.closing(wave.open(path)) as wf:
        return wf.getnframes() / wf.getframerate()


def render_scene(scene_cls, scenes_file, dur, wav_path, seg_path, workdir, idx):
    env = dict(os.environ, SCENE_DUR=f"{dur:.2f}")
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


def build(topic_dir, out_dir, diagram_png=None):
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(out_dir, "_video_work")
    os.makedirs(work, exist_ok=True)

    with open(os.path.join(topic_dir, "narration.txt"), encoding="utf-8") as f:
        paras = [p.strip() for p in f.read().strip().split("\n\n") if p.strip()]

    scenes_file = os.path.join(topic_dir, "manim_scenes.py")
    if not os.path.exists(scenes_file):
        scenes_file = DEFAULT_SCENES
    scene_classes = load_scene_classes(scenes_file)
    assert len(scene_classes) == len(paras), \
        f"{len(paras)} narration paragraphs but {len(scene_classes)} scenes"

    wavs = tts_wavs(paras, work)
    segs = []
    for i, (cls, wav) in enumerate(zip(scene_classes, wavs)):
        dur = wav_seconds(wav) + 0.8
        seg = os.path.join(work, f"seg{i}.mp4")
        print(f"  manim {cls} ({dur:.1f}s)...", flush=True)
        render_scene(cls, scenes_file, dur, wav, seg, work, i)
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
