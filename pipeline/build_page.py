#!/usr/bin/env python3
"""L3: assemble a single-file interactive HTML page.

Inputs: brief.md (L1), diagram.svg (L2), narration.txt (walkthrough steps).
Output: index.html with tabs, a step-through walkthrough, and a glossary.
"""
import html
import os
import sys

import markdown

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Interactive Explainer</title>
<style>
  :root {{ --bg:#0f172a; --card:#1e293b; --ink:#e2e8f0; --mut:#94a3b8; --acc:#38bdf8; }}
  body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background:var(--bg); color:var(--ink); margin:0; padding:24px; line-height:1.7; }}
  .wrap {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 1.9rem; }}
  .sub {{ color: var(--mut); margin-top:-12px; }}
  .tabs {{ display:flex; gap:8px; margin:20px 0; }}
  .tab {{ padding:10px 18px; border-radius:10px; border:1px solid #334155; background:var(--card); color:var(--ink); cursor:pointer; font-size:1rem; }}
  .tab.active {{ background:var(--acc); color:#082f49; border-color:var(--acc); font-weight:700; }}
  .panel {{ display:none; background:var(--card); border-radius:14px; padding:24px; }}
  .panel.active {{ display:block; }}
  .panel svg {{ width:100%; height:auto; background:#fff; border-radius:10px; }}
  .stepper {{ display:flex; align-items:center; gap:12px; margin:16px 0; }}
  .stepper button {{ padding:8px 16px; border-radius:8px; border:1px solid var(--acc); background:transparent; color:var(--acc); cursor:pointer; font-size:1rem; }}
  .stepper button:disabled {{ opacity:.35; cursor:default; }}
  #stepCard {{ background:#0b1220; border:1px solid #334155; border-radius:10px; padding:18px; min-height:110px; }}
  #stepNum {{ color:var(--acc); font-weight:700; }}
  details {{ border:1px solid #334155; border-radius:10px; padding:12px 16px; margin:10px 0; background:#0b1220; }}
  summary {{ cursor:pointer; font-weight:600; }}
  .ladder {{ color:var(--mut); font-size:.9rem; margin-top:28px; border-top:1px solid #334155; padding-top:12px; }}
  code {{ background:#0b1220; padding:2px 6px; border-radius:6px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{title}</h1>
  <p class="sub">Karpathy's explain ladder — Level 3: interactive page. Built by the explain-ladder pipeline.</p>
  <div class="tabs">
    <button class="tab active" data-p="p1">📖 Read</button>
    <button class="tab" data-p="p2">🔀 Diagram</button>
    <button class="tab" data-p="p3">👣 Walkthrough</button>
    <button class="tab" data-p="p4">📚 Glossary</button>
  </div>

  <div class="panel active" id="p1">{brief_html}</div>
  <div class="panel" id="p2">{diagram_svg}<p style="color:var(--mut)">Flowchart rendered from <code>diagram.mmd</code> with mermaid.</p></div>
  <div class="panel" id="p3">
    <div class="stepper">
      <button id="prevBtn">← Prev</button>
      <span id="stepNum"></span>
      <button id="nextBtn">Next →</button>
    </div>
    <div id="stepCard"></div>
  </div>
  <div class="panel" id="p4">{glossary_html}</div>

  <p class="ladder">Ladder: L1 plain words → L2 diagram → <b>L3 this page</b> → L4 video (<code>explainer.mp4</code>).</p>
</div>
<script>
const steps = {steps_json};
let i = 0;
const card = document.getElementById('stepCard');
const num = document.getElementById('stepNum');
const prev = document.getElementById('prevBtn');
const next = document.getElementById('nextBtn');
function show() {{
  card.innerHTML = '<p>'+steps[i]+'</p>';
  num.textContent = 'Step '+(i+1)+' / '+steps.length;
  prev.disabled = (i===0); next.disabled = (i===steps.length-1);
}}
prev.onclick = ()=>{{ if(i>0){{i--;show();}} }};
next.onclick = ()=>{{ if(i<steps.length-1){{i++;show();}} }};
show();
document.querySelectorAll('.tab').forEach(t=>{{
  t.onclick = ()=>{{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById(t.dataset.p).classList.add('active');
  }};
}});
</script>
</body>
</html>
"""

GLOSSARY = [
    ("Chunk", "A small piece of a document. RAG works on chunks, not whole books."),
    ("Embedding", "A list of numbers that captures the meaning of text. Similar meanings sit close together."),
    ("Vector database", "A database that stores embeddings and finds the nearest ones fast."),
    ("Retrieval", "The step where the system fetches the chunks most related to your question."),
    ("Grounding", "Making the model's answer come from your documents instead of its memory."),
]


def build(topic_dir, out_dir):
    import json as _json
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(topic_dir, "brief.md"), encoding="utf-8") as f:
        brief_md = f.read()
    with open(os.path.join(out_dir, "diagram.svg"), encoding="utf-8") as f:
        diagram_svg = f.read()
    with open(os.path.join(topic_dir, "narration.txt"), encoding="utf-8") as f:
        paras = [p.strip() for p in f.read().strip().split("\n\n") if p.strip()]

    glossary = GLOSSARY
    glossary_path = os.path.join(topic_dir, "glossary.json")
    if os.path.exists(glossary_path):
        with open(glossary_path, encoding="utf-8") as f:
            glossary = [tuple(pair) for pair in _json.load(f)]

    title = brief_md.splitlines()[0].lstrip("# ").strip()
    brief_html = markdown.markdown("\n".join(brief_md.splitlines()[1:]))
    glossary_html = "".join(
        f"<details><summary>{html.escape(t)}</summary><p>{html.escape(d)}</p></details>"
        for t, d in glossary)
    steps_json = _json.dumps([html.escape(p) for p in paras])

    page = PAGE_TEMPLATE.format(
        title=html.escape(title), brief_html=brief_html,
        diagram_svg=diagram_svg, glossary_html=glossary_html,
        steps_json=steps_json)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    return out


if __name__ == "__main__":
    print("page:", build(sys.argv[1], sys.argv[2]))
