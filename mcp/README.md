# Explain Ladder MCP Server (v1)

Wraps the explain-ladder pipeline as MCP tools (stdio transport) so any
agent can render an explainer: L2 diagram, L3 interactive page, L4 manim
video with Piper narration.

## Setup (already done on this machine)

```bash
python3 -m venv mcp/.venv
mcp/.venv/bin/pip install 'mcp<2'        # v1 API; FastMCP was renamed in mcp 2.x
cd mcp && npm install @mermaid-js/mermaid-cli   # provides mmdc for L2
```

Pipeline deps (manim, piper, ...) stay in the project `.venv`; the server
shells out to it via `mcp/runner.py`. Jobs live under `mcp_jobs/<job_id>/`
(topic inputs, outputs, job.json, run.log).

## Run

```bash
mcp/.venv/bin/python mcp/server.py
```

Point any MCP client at that command (stdio). Smoke test:

```bash
mcp/.venv/bin/python mcp/test_client.py quick   # spec + validation + L2/L3
mcp/.venv/bin/python mcp/test_client.py full    # + L4 video (minutes)
```

## Tools

| Tool | Purpose |
|---|---|
| `explain_spec` | Authoring spec calling agents must follow (formats, hard rules, protocol) |
| `explain_start` | Validate inputs, launch async render job, returns `job_id` + warnings |
| `explain_status` | Poll job state/step/outputs |
| `explain_result` | Collect output file paths + sizes (or the error excerpt) |

Inputs: `name` (slug), `brief_md` (first line `# Title`, ASD-STE100 body),
`diagram_mmd` (valid Mermaid), `narration_txt` (blank-line paragraphs,
one per scene), optional `manim_scenes_py` (defines `SCENE_CLASSES`, one
scene per narration paragraph), optional `glossary` ([term, definition]
pairs for L3), `levels` subset of L2/L3/L4 (L2 always rendered: L3 needs
its SVG, L4 its PNG).

## Known limits (v1)

- stdio only, single machine, no auth. HTTP transport + deployment next
  to the central MCP gateway is phase 2.
- Without `manim_scenes_py`, L4 uses the built-in 4 RAG-themed scenes and
  narration must have exactly 4 paragraphs.
