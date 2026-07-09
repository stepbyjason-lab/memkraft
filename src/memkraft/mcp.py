"""memkraft.mcp — MCP stdio server exposing MemKraft primitives.

Requires the `mcp` extra:

    pip install 'memkraft[mcp]'

Run:

    python -m memkraft.mcp

Exposes four tools:
    - remember(name, info, source)
    - search(query, fuzzy)
    - recall(name)
    - link(source, target)
"""
from __future__ import annotations

import contextlib
import inspect
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from . import __version__


QUERY_MAX_CHARS = 2000
DEFAULT_TOP_K = 8
MAX_TOP_K = 20
SEARCH_FIELD_MAX_CHARS = 2000
SEARCH_PAYLOAD_MAX_BYTES = 64 * 1024
RECALL_PAYLOAD_MAX_BYTES = 256 * 1024

_MCP_HINT = (
    "mcp package not installed. install it with:\n"
    "    pip install 'memkraft[mcp]'\n"
    "then retry `python -m memkraft.mcp`"
)


def _require_mcp():
    try:
        import mcp  # noqa: F401
        from mcp.server import Server  # noqa: F401
        from mcp.server.stdio import stdio_server
        import mcp.types as types  # noqa: F401
    except ImportError:
        print(f"❌ {_MCP_HINT}", file=sys.stderr)
        sys.exit(2)
    sig = inspect.signature(stdio_server)
    if "stdin" not in sig.parameters or "stdout" not in sig.parameters:
        print("❌ installed mcp stdio_server does not support explicit streams", file=sys.stderr)
        sys.exit(2)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(_jsonable(k)): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


def _json_text(payload: Any):
    import mcp.types as types

    text = json.dumps(_jsonable(payload), ensure_ascii=False, separators=(",", ":"))
    return [types.TextContent(type="text", text=text)]


def _error_result(kind: str, message: str = "tool call failed"):
    import mcp.types as types

    text = json.dumps(
        {"error": {"type": kind, "message": message}},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text=text)],
    )


def _validate_query(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("query is required")
    query = value.strip()
    if not query:
        raise ValueError("query is required")
    if len(query) > QUERY_MAX_CHARS:
        raise ValueError("query is too long")
    return query


def _validate_top_k(value: Any) -> int:
    if value is None:
        return DEFAULT_TOP_K
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("top_k must be an integer")
    if value < 1 or value > MAX_TOP_K:
        raise ValueError("top_k is out of range")
    return value


def _validate_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError("fuzzy must be a boolean")
    return value


def _normalize_results(value: Any) -> list[dict[str, Any]]:
    value = _jsonable(value)
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        for key in ("results", "items", "matches", "data"):
            if isinstance(value.get(key), list):
                items = value[key]
                break
        else:
            items = [value]
    else:
        items = [{"value": value}]
    return [item if isinstance(item, dict) else {"value": item} for item in items]


def _truncate_search_results(results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool, list[str]]:
    truncated = False
    fields: list[str] = []
    text_keys = {"text", "snippet", "body", "content", "summary"}
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(results):
        new_item = dict(item)
        for key, value in list(new_item.items()):
            if key in text_keys and isinstance(value, str) and len(value) > SEARCH_FIELD_MAX_CHARS:
                new_item[key] = value[:SEARCH_FIELD_MAX_CHARS]
                truncated = True
                fields.append(f"results[{idx}].{key}")
        out.append(new_item)
    return out, truncated, fields


def _cap_payload(payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= max_bytes:
        return payload
    payload = dict(payload)
    payload["truncated"] = True
    fields = list(payload.get("truncated_fields") or [])
    fields.append("$payload")
    payload["truncated_fields"] = fields
    results = list(payload.get("results") or [])
    while results and len(json.dumps({**payload, "results": results}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > max_bytes:
        results.pop()
    payload["results"] = results
    return payload


def _cap_recall(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload.setdefault("truncated", False)
    fields = list(payload.get("truncated_fields") or [])
    text = payload.get("text")
    if not isinstance(text, str):
        payload["truncated_fields"] = fields
        return payload
    while len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > RECALL_PAYLOAD_MAX_BYTES and text:
        text = text[: max(0, int(len(text) * 0.8))]
        payload["text"] = text
        payload["truncated"] = True
        if "text" not in fields:
            fields.append("text")
        payload["truncated_fields"] = fields
    payload.setdefault("truncated_fields", fields)
    return payload


def _setup_stdio_streams() -> tuple[Any, Any]:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    original_stdin_buffer = sys.stdin.buffer
    original_stdout_buffer = sys.stdout.buffer
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
        elif hasattr(stream, "buffer"):
            wrapped = io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")
            if stream is sys.stdin:
                sys.stdin = wrapped  # type: ignore[assignment]
            elif stream is sys.stdout:
                sys.stdout = wrapped  # type: ignore[assignment]
            else:
                sys.stderr = wrapped  # type: ignore[assignment]
        else:
            raise RuntimeError("stdio stream is not UTF-8 configurable")
    protocol_stdin = io.TextIOWrapper(original_stdin_buffer, encoding="utf-8", errors="replace")
    protocol_stdout = io.TextIOWrapper(original_stdout_buffer, encoding="utf-8", errors="replace")
    sys.stdout = sys.stderr
    return protocol_stdin, protocol_stdout


def _tool_schemas() -> list:
    """Return tool schemas shared between extras-installed and stub modes."""
    return [
        {
            "name": "remember",
            "description": "Store new information about an entity (person/org/project).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "info": {"type": "string"},
                    "source": {"type": "string", "default": "mcp"},
                },
                "required": ["name", "info"],
            },
        },
        {
            "name": "search",
            "description": "Bounded search over all stored memory. Defaults to search_smart for fast MCP use.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": QUERY_MAX_CHARS},
                    "fuzzy": {"type": "boolean"},
                    "top_k": {
                        "type": "integer",
                        "default": DEFAULT_TOP_K,
                        "minimum": 1,
                        "maximum": MAX_TOP_K,
                    },
                    "strategy": {
                        "type": "string",
                        "enum": ["smart", "v2", "legacy"],
                        "default": "smart",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "recall",
            "description": "Return a dossier for a single entity.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
        },
        {
            "name": "link",
            "description": "Create a wiki-style link between two entities.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                },
                "required": ["source", "target"],
            },
        },
    ]


def dispatch(mk, name: str, args: Dict[str, Any]) -> Any:
    """Pure dispatch — no MCP dependency. Unit-testable."""
    if name == "remember":
        mk.update(args["name"], args["info"], source=args.get("source", "mcp"))
        return {"ok": True, "name": args["name"]}
    if name == "search":
        query = _validate_query(args.get("query"))
        strategy = args.get("strategy", "smart")
        if strategy not in {"smart", "v2", "legacy"}:
            raise ValueError("strategy is invalid")
        top_k = _validate_top_k(args.get("top_k"))
        fuzzy = _validate_bool(args.get("fuzzy"), default=False)

        with contextlib.redirect_stdout(sys.stderr):
            if strategy == "smart" and callable(getattr(mk, "search_smart", None)):
                raw = mk.search_smart(query, top_k=top_k, fuzzy=fuzzy, cache=True)
            elif strategy == "v2" and callable(getattr(mk, "search_v2", None)):
                raw = mk.search_v2(query, top_k=top_k, fuzzy=fuzzy, cache=True)
            elif strategy == "legacy":
                raw = mk.search(query, fuzzy=fuzzy)
            else:
                raise ValueError("search strategy is unavailable")

        results = _normalize_results(raw)[:top_k]
        results, truncated, fields = _truncate_search_results(results)
        return _cap_payload(
            {
                "results": results,
                "truncated": truncated,
                "truncated_fields": fields,
                "total_results": len(results),
            },
            SEARCH_PAYLOAD_MAX_BYTES,
        )
    if name == "recall":
        brief = getattr(mk, "brief", None)
        if not callable(brief):
            return {"found": False, "name": args["name"], "text": "", "truncated": False, "truncated_fields": []}
        with contextlib.redirect_stdout(sys.stderr):
            text = brief(args["name"]) or ""
        # Existence is decided by file presence, not by truthiness of the brief
        # text. ``brief()`` always returns a non-empty dossier (even a
        # "not found" notice), so relying on the old ``or`` fallback masked
        # successful lookups as ``found: False``.
        slug = mk._slugify(args["name"])
        found = (mk.entities_dir / f"{slug}.md").exists() or (
            mk.live_notes_dir / f"{slug}.md"
        ).exists()
        return _cap_recall({"found": found, "name": args["name"], "text": text})
    if name == "link":
        link_add = getattr(mk, "link_add", None)
        if callable(link_add):
            link_add(args["source"], args["target"])
            return {"ok": True}
        return {"ok": False, "error": "link_add not available in this MemKraft version"}
    raise ValueError(f"unknown tool: {name}")


def main() -> None:
    _require_mcp()

    import asyncio
    import anyio
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types

    from .core import MemKraft

    protocol_stdin, protocol_stdout = _setup_stdio_streams()
    mk = MemKraft()
    server = Server("memkraft")

    @server.list_tools()
    async def _list_tools():
        return [
            types.Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in _tool_schemas()
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any]):
        try:
            result = dispatch(mk, name, arguments or {})
            return _json_text(result)
        except ValueError as e:
            return _error_result("invalid_input", str(e))
        except Exception:
            return _error_result("internal_error", "tool call failed")

    async def _run():
        stdin_async = anyio.wrap_file(protocol_stdin)
        stdout_async = anyio.wrap_file(protocol_stdout)
        async with stdio_server(stdin=stdin_async, stdout=stdout_async) as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
