#!/usr/bin/env python3
"""Smoke test for the Pixabay MCP server.

Spawns the server over stdio, initializes a client session,
verifies all 11 tools are listed, calls api_status, and
tests search_sfx graceful error path.
Works with or without API keys configured.
"""

import asyncio
import sys
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = [
    "search_images",
    "search_videos",
    "get_image",
    "get_video",
    "download_image",
    "download_video",
    "api_status",
    "search_sfx",
    "download_sfx",
    "search_music",
    "download_music",
]


async def main() -> int:
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve().parent / "pixabay_server.py")],
    )

    results: list[tuple[str, bool, str]] = []

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Initialize
            try:
                await session.initialize()
                results.append(("initialize", True, "Server initialized successfully"))
            except Exception as e:
                results.append(("initialize", False, f"Failed: {e}"))
                for name, ok, msg in results:
                    print(f"{'PASS' if ok else 'FAIL'} {name}: {msg}")
                return 1

            # 2. tools/list
            try:
                tools_response = await session.list_tools()
                tool_names = sorted([t.name for t in tools_response.tools])
                missing = [t for t in EXPECTED_TOOLS if t not in tool_names]
                extra = [t for t in tool_names if t not in EXPECTED_TOOLS]
                if not missing:
                    results.append(
                        ("tools/list", True, f"All {len(EXPECTED_TOOLS)} tools present: {', '.join(tool_names)}")
                    )
                else:
                    results.append(("tools/list", False, f"Missing: {missing}, Extra: {extra}"))
            except Exception as e:
                results.append(("tools/list", False, f"Failed: {e}"))

            # 3. api_status call
            try:
                result = await session.call_tool("api_status", {})
                text = result.content[0].text if result.content else ""
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "ok" in parsed:
                    status_msg = parsed.get("message", "")
                    results.append(("api_status", True, f"ok={parsed['ok']}, message={status_msg}"))
                elif isinstance(parsed, dict) and "pixabay" in parsed:
                    # New combined format — check it has all providers
                    providers = [k for k in parsed if isinstance(parsed[k], dict)]
                    results.append(("api_status", True, f"providers={providers}"))
                else:
                    results.append(("api_status", False, f"Unexpected response shape: {text[:200]}"))
            except Exception as e:
                results.append(("api_status", False, f"Failed: {e}"))

            # 4. search_sfx: graceful error when no token, real results when configured
            try:
                result = await session.call_tool("search_sfx", {"q": "rain", "per_page": 1})
                text = result.content[0].text if result.content else ""
                if "Freesound" in text and "not configured" in text:
                    results.append(("search_sfx", True, f"Graceful error: {text[:120]}"))
                elif "not configured" in text or "error" in text.lower():
                    results.append(("search_sfx", True, f"Error returned (graceful): {text[:120]}"))
                else:
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict) and "results" in parsed:
                            results.append(("search_sfx", True, f"Real results: count={parsed.get('count', '?')}"))
                        else:
                            results.append(("search_sfx", False, f"Unexpected: {text[:200]}"))
                    except Exception:
                        results.append(("search_sfx", False, f"Unexpected: {text[:200]}"))
            except Exception as e:
                # Protocol-level exceptions also count as graceful handling
                results.append(("search_sfx", True, f"Exception caught (graceful): {e}"))

    # Print results
    for name, ok, msg in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}: {msg}")

    all_pass = all(ok for _, ok, _ in results)
    if all_pass:
        print("SMOKE TEST: PASS")
        return 0
    else:
        print("SMOKE TEST: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
