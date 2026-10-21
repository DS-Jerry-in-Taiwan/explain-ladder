"""manim scenes for the demo topic (How RAG Works).

Each Scene reads its target duration from the SCENE_DUR env var so the
animation fills exactly the narration segment. build_video.py renders one
Scene per narration paragraph, then muxes the Piper TTS audio.

Convention for new topics: copy this file next to your topic dir as
<topic>/manim_scenes.py and set SCENE_CLASSES to your scene names
(one per narration paragraph).
"""
import os

from manim import *

config.pixel_width = 1280
config.pixel_height = 720

BG = "#0f172a"
INK = "#e2e8f0"
MUT = "#94a3b8"
ACC = "#38bdf8"
GREEN = "#34d399"
CARD = "#1e293b"
EDGE = "#334155"

D = float(os.environ.get("SCENE_DUR", "5.0"))
FONT = os.environ.get("EXPLAIN_FONT") or (
    "Noto Sans CJK TC" if os.environ.get("EXPLAIN_LANG") == "zh"
    else "DejaVu Sans")


def card(w=3.4, h=1.9, outline=EDGE, fill=CARD):
    return RoundedRectangle(
        corner_radius=0.18, width=w, height=h,
        fill_color=fill, fill_opacity=1,
        stroke_color=outline, stroke_width=3,
    )


def header(text):
    return Text(text, font=FONT, font_size=28, color=MUT).to_edge(UP, buff=0.6)


def chip(text):
    r = RoundedRectangle(
        corner_radius=0.12, width=1.8, height=0.85,
        fill_color="#153f2e", fill_opacity=1,
        stroke_color=GREEN, stroke_width=2.5,
    )
    t = Text(text, font=FONT, font_size=22, color=GREEN)
    t.move_to(r.get_center())
    return VGroup(r, t)


class SceneIntro(Scene):
    def construct(self):
        self.camera.background_color = BG
        title = Text("How RAG Works", font=FONT, font_size=64, color=INK)
        line = Line(LEFT * 3.5, RIGHT * 3.5, color=ACC, stroke_width=8)
        line.next_to(title, DOWN, buff=0.35)
        sub = Text("An explainer video — Karpathy's ladder, level 4",
                   font=FONT, font_size=26, color=MUT)
        sub.next_to(line, DOWN, buff=0.35)
        self.play(Write(title), run_time=D * 0.35)
        self.play(GrowFromCenter(line), run_time=D * 0.20)
        self.play(FadeIn(sub, shift=UP * 0.2), run_time=D * 0.20)
        self.wait(D * 0.25)


class SceneIndex(Scene):
    def construct(self):
        self.camera.background_color = BG
        self.play(FadeIn(header("Step 1 · Build the index")), run_time=D * 0.08)
        names = ["Split into\nchunks", "Embed to\nvectors", "Vector\ndatabase"]
        xs = [-4.4, 0.0, 4.4]
        groups, boxes = [], []
        for x, name in zip(xs, names):
            b = card(outline=ACC if "Vector" in name else EDGE)
            t = Text(name, font=FONT, font_size=28, color=INK)
            t.move_to(b.get_center())
            g = VGroup(b, t).move_to([x, 0.3, 0])
            boxes.append(b)
            groups.append(g)
        arrows = [Arrow(groups[i].get_right(), groups[i + 1].get_left(),
                        color=ACC, stroke_width=6, buff=0.15)
                  for i in range(2)]
        u = D * 0.72 / 5
        for i, g in enumerate(groups):
            self.play(FadeIn(g, shift=UP * 0.25), run_time=u)
            if i < 2:
                self.play(Create(arrows[i]), run_time=u * 0.7)
        self.play(Indicate(boxes[2], color=GREEN), run_time=D * 0.12)
        self.wait(D * 0.08)


class SceneSearch(Scene):
    def construct(self):
        self.camera.background_color = BG
        self.play(FadeIn(header("Step 2 · Retrieve")), run_time=D * 0.08)
        qb = card(w=3.0, h=1.8)
        qt = Text("User\nquestion", font=FONT, font_size=28, color=INK)
        qt.move_to(qb.get_center())
        qg = VGroup(qb, qt).move_to([-4.6, 0.5, 0])
        db = card(w=3.0, h=1.8, outline=ACC)
        dt = Text("Vector\ndatabase", font=FONT, font_size=28, color=INK)
        dt.move_to(db.get_center())
        dbg = VGroup(db, dt).move_to([0.6, 0.5, 0])
        arr = Arrow(qg.get_right(), dbg.get_left(),
                    color=ACC, stroke_width=6, buff=0.15)
        u = D * 0.50 / 3
        self.play(FadeIn(qg, shift=RIGHT * 0.3), run_time=u)
        self.play(Create(arr), run_time=u * 0.8)
        self.play(FadeIn(dbg, shift=UP * 0.25), run_time=u)
        chips = VGroup(*[chip(f"chunk {i + 1}") for i in range(3)])
        chips.arrange(RIGHT, buff=0.4).next_to(dbg, DOWN, buff=0.7)
        self.play(
            LaggedStart(*[FadeIn(c, shift=UP * 0.3, scale=0.8) for c in chips],
                        lag_ratio=0.35),
            run_time=D * 0.30,
        )
        self.wait(D * 0.12)


class SceneAnswer(Scene):
    def construct(self):
        self.camera.background_color = BG
        self.play(FadeIn(header("Step 3 · Generate")), run_time=D * 0.08)
        lb = card(w=3.6, h=2.0, outline=ACC)
        lt = Text("LLM", font=FONT, font_size=44, color=INK)
        lt.move_to(lb.get_center())
        llmg = VGroup(lb, lt).move_to([0, 1.2, 0])
        self.play(FadeIn(llmg, shift=UP * 0.25), run_time=D * 0.12)
        chips = VGroup(*[chip(f"chunk {i + 1}") for i in range(3)])
        for c, y in zip(chips, [-0.8, -1.9, -3.0]):
            c.move_to([-5.8, y, 0])
        self.play(*[FadeIn(c) for c in chips], run_time=D * 0.10)
        self.play(
            *[c.animate.move_to(lb.get_center() + RIGHT * (i - 1) * 0.25)
              for i, c in enumerate(chips)],
            run_time=D * 0.18,
        )
        self.play(*[FadeOut(c) for c in chips], run_time=D * 0.08)
        ans = Text("Answer grounded in your data ✓", font=FONT,
                   font_size=40, color=GREEN).move_to([0, -1.8, 0])
        self.play(AddTextLetterByLetter(ans), run_time=D * 0.32)
        self.wait(D * 0.12)


SCENE_CLASSES = ["SceneIntro", "SceneIndex", "SceneSearch", "SceneAnswer"]
