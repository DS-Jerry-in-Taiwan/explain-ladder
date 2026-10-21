#!/usr/bin/env python3
"""Smoke test for the explain-ladder MCP server (stdio client).

Usage:
  test_client.py quick   # spec + validation + L2/L3 job
  test_client.py full    # full job incl. L4 video (takes minutes)
"""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SERVER_PY = os.path.join(HERE, "server.py")
SERVER_PYTHON = os.path.join(HERE, ".venv", "bin", "python")
DEMO = os.path.join(PROJECT, "demo", "rag")


def read(name):
    with open(os.path.join(DEMO, name), encoding="utf-8") as f:
        return f.read()


def text_of(result):
    return "".join(c.text for c in result.content if hasattr(c, "text"))


async def poll(session, job_id, timeout_s=1200):
    waited = 0
    while waited <= timeout_s:
        r = await session.call_tool("explain_status", {"job_id": job_id})
        st = json.loads(text_of(r))
        print("  status:", st["state"], "| step:", st.get("step"), flush=True)
        if st["state"] in ("done", "failed"):
            return st
        await asyncio.sleep(10)
        waited += 10
    raise TimeoutError(f"job {job_id} not finished in {timeout_s}s")


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    params = StdioServerParameters(command=SERVER_PYTHON, args=[SERVER_PY])
    async with stdio_client(params) as (read_s, write_s):
        async with ClientSession(read_s, write_s) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])

            spec = await session.call_tool("explain_spec", {})
            print("spec chars:", len(text_of(spec)))

            # validation: paragraph/scene mismatch must be rejected readably
            bad = await session.call_tool("explain_start", {
                "name": "bad-job", "brief_md": read("brief.md"),
                "diagram_mmd": read("diagram.mmd"),
                "narration_txt": "one\n\ntwo\n\nthree",
                "levels": ["L4"]})
            print("bad job rejected:", "exactly 4" in text_of(bad) or text_of(bad)[:120])

            levels = ["L2", "L3"] if mode == "quick" else ["L2", "L3", "L4"]
            r = await session.call_tool("explain_start", {
                "name": "rag-mcp-test", "brief_md": read("brief.md"),
                "diagram_mmd": read("diagram.mmd"),
                "narration_txt": read("narration.txt"),
                "glossary": [["Chunk", "A small piece of a document."],
                              ["Embedding", "Numbers that capture meaning."]],
                "levels": levels})
            started = json.loads(text_of(r))
            print("started:", started)
            st = await poll(session, started["job_id"])
            print("final:", st["state"])
            res = await session.call_tool(
                "explain_result", {"job_id": started["job_id"]})
            print("result:", text_of(res))


if __name__ == "__main__":
    asyncio.run(main())
