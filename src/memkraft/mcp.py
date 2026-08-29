"""memkraft.mcp — MCP stdio server exposing MemKraft primitives.

Requires the `mcp` extra:

    pip install 'memkraft[mcp]'

Run:

    python -m memkraft.mcp

Exposes six tools:
    - remember(name, info, source)
    - search(query, strategy, fuzzy, top_k)
    - recall(name)
    - link(source, target)
    - memkraft_execution_query(request_id, op, target, args)
    - memkraft_execution_describe(request_id)
"""
from __future__ import annotations

import contextlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from . import __version__


_MCP_HINT = (
    "mcp package not installed. install it with:\n"
    "    pip install 'memkraft[mcp]'\n"
    "then retry `python -m memkraft.mcp`"
)

QUERY_MAX_CHARS = 2_000
REMEMBER_INFO_MAX_CHARS = 64 * 1024
REMEMBER_INFO_MAX_BYTES = 256 * 1024
SOURCE_MAX_CHARS = 2_000
ENTITY_TYPE_MAX_CHARS = 64
DEFAULT_TOP_K = 8
MAX_TOP_K = 20
SEARCH_FIELD_MAX_CHARS = 2_000
SEARCH_PAYLOAD_MAX_BYTES = 64 * 1024
RECALL_PAYLOAD_MAX_BYTES = 256 * 1024


class McpInputError(ValueError):
    """An invalid MCP argument with a stable caller-facing error code."""

    code = "INVALID_ARGUMENT"


class McpMemoryError(RuntimeError):
    """A memory operation did not persist its requested change."""

    code = "MEMORY_ERROR"


def _utf8_text(value: str) -> str:
    """Replace any invalid surrogate while preserving ordinary Unicode text."""
    return value.encode("utf-8", errors="replace").decode("utf-8")


def _jsonable(value: Any) -> Any:
    """Convert MCP payloads into JSON-safe, UTF-8-safe values."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _utf8_text(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return _utf8_text(str(value))


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(
        _jsonable(payload), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _payload_text(payload: Any) -> str:
    """JSON text for the memory tools, including their user-authored fields."""
    return _json_bytes(payload).decode("utf-8")


def _validate_query(value: Any) -> str:
    if not isinstance(value, str):
        raise McpInputError("query must be a string")
    query = value.strip()
    if not query:
        raise McpInputError("query must not be empty")
    if len(query) > QUERY_MAX_CHARS:
        raise McpInputError("query is too long")
    return query


def _validate_required_text(value: Any, *, name: str, max_chars: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise McpInputError(f"{name} must be a non-empty string")
    if max_chars is not None and len(value) > max_chars:
        raise McpInputError(f"{name} is too long")
    return value


def _validate_source(value: Any) -> str:
    return _validate_required_text(value, name="source", max_chars=SOURCE_MAX_CHARS)


def _validate_remember_info(value: Any) -> str:
    info = _validate_required_text(value, name="info", max_chars=REMEMBER_INFO_MAX_CHARS)
    if len(_utf8_text(info).encode("utf-8")) > REMEMBER_INFO_MAX_BYTES:
        raise McpInputError("info is too long")
    return info


def _memory_name(mk: Any, value: Any) -> str:
    name = _validate_required_text(value, name="name", max_chars=QUERY_MAX_CHARS)
    strip_josa = getattr(mk, "_strip_korean_josa", None)
    canonical = strip_josa(name.strip()) if callable(strip_josa) else name.strip()
    if not canonical:
        raise McpInputError("name must be a non-empty string")
    return canonical


def _existing_memory_path(mk: Any, requested_name: str) -> Path | None:
    """Resolve a stored entity before applying Korean josa normalization again."""
    raw_path = mk.live_notes_dir / f"{mk._slugify(requested_name.strip())}.md"
    if raw_path.exists():
        return raw_path
    canonical_path = mk.live_notes_dir / f"{mk._slugify(_memory_name(mk, requested_name))}.md"
    return canonical_path if canonical_path.exists() else None


def _validate_top_k(value: Any) -> int:
    if value is None:
        return DEFAULT_TOP_K
    if isinstance(value, bool) or not isinstance(value, int):
        raise McpInputError("top_k must be an integer")
    if not 1 <= value <= MAX_TOP_K:
        raise McpInputError(f"top_k must be between 1 and {MAX_TOP_K}")
    return value


def _validate_bool(value: Any, *, default: bool, name: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise McpInputError(f"{name} must be a boolean")
    return value


def _search_arguments(args: Dict[str, Any]) -> tuple[str, str, bool, int]:
    query = _validate_query(args.get("query"))
    strategy = args.get("strategy", "smart")
    if not isinstance(strategy, str) or strategy not in {"smart", "v2", "legacy"}:
        raise McpInputError("strategy must be one of: smart, v2, legacy")
    fuzzy = _validate_bool(args.get("fuzzy"), default=False, name="fuzzy")
    return query, strategy, fuzzy, _validate_top_k(args.get("top_k"))


def _normalize_results(value: Any) -> list[dict[str, Any]]:
    value = _jsonable(value)
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = next(
            (value[key] for key in ("results", "items", "matches", "data")
             if isinstance(value.get(key), list)),
            [value],
        )
    else:
        items = [{"value": value}]
    return [item if isinstance(item, dict) else {"value": item} for item in items]


def _truncate_search_results(results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    fields: list[str] = []
    text_keys = {"text", "snippet", "body", "content", "summary"}
    truncated: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        item = dict(result)
        for key, value in tuple(item.items()):
            if key in text_keys and isinstance(value, str) and len(value) > SEARCH_FIELD_MAX_CHARS:
                item[key] = value[:SEARCH_FIELD_MAX_CHARS]
                fields.append(f"results[{index}].{key}")
        truncated.append(item)
    return truncated, fields


def _cap_search_payload(results: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    items, fields = _truncate_search_results(results[:top_k])
    original_count = len(items)
    payload: dict[str, Any] = {
        "results": items,
        "total_results": original_count,
        "truncated": bool(fields),
        "truncated_fields": fields,
        "returned_results": len(items),
    }
    while items and len(_json_bytes(payload)) > SEARCH_PAYLOAD_MAX_BYTES:
        items.pop()
        payload["truncated"] = True
        if "$payload" not in fields:
            fields.append("$payload")
        payload["returned_results"] = len(items)
    fields = [
        field for field in fields
        if not field.startswith("results[")
        or int(field.split("[", 1)[1].split("]", 1)[0]) < len(items)
    ]
    payload["truncated_fields"] = fields
    return payload


def _cap_recall_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = _jsonable(dict(payload))
    assert isinstance(result, dict)
    fields: list[str] = []
    text = result.get("text")
    result["truncated"] = False
    result["truncated_fields"] = fields
    if isinstance(text, str):
        while text and len(_json_bytes(result)) > RECALL_PAYLOAD_MAX_BYTES:
            text = text[: max(0, len(text) * 4 // 5)]
            result["text"] = text
            if "text" not in fields:
                fields.append("text")
            result["truncated"] = True
    return result


def _error_payload(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": _utf8_text(message)}}


def _require_mcp():
    try:
        import mcp  # noqa: F401
        from mcp.server import Server  # noqa: F401
        from mcp.server.stdio import stdio_server  # noqa: F401
        import mcp.types as types  # noqa: F401
    except ImportError:
        print(f"❌ {_MCP_HINT}", file=sys.stderr)
        sys.exit(2)


def _tool_schemas() -> list:
    """Return tool schemas shared between extras-installed and stub modes."""
    return [
        {
            "name": "remember",
            "description": "Store new information about an entity (person/org/project).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": QUERY_MAX_CHARS},
                    "info": {"type": "string", "maxLength": REMEMBER_INFO_MAX_CHARS},
                    "source": {"type": "string", "maxLength": SOURCE_MAX_CHARS, "default": "mcp"},
                    "entity_type": {"type": "string", "maxLength": ENTITY_TYPE_MAX_CHARS, "default": "person"},
                },
                "required": ["name", "info"],
            },
        },
        {
            "name": "search",
            "description": "Bounded search over stored memory. Defaults to fast smart search.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": QUERY_MAX_CHARS},
                    "strategy": {
                        "type": "string",
                        "enum": ["smart", "v2", "legacy"],
                        "default": "smart",
                    },
                    "fuzzy": {"type": "boolean", "default": False},
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_TOP_K,
                        "default": DEFAULT_TOP_K,
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
                    "name": {"type": "string", "maxLength": QUERY_MAX_CHARS},
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
        {
            "name": "memkraft_execution_query",
            "description": (
                "Read execution state, run an advisory assessment, or export a "
                "handoff. should_run is advisory and does not authorize dispatch."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string"},
                    "op": {"type": "string", "enum": [
                        "state.read", "assess.run", "handoff.export"
                    ]},
                    "target": {"type": "object"},
                    "args": {"type": "object"},
                    "capabilities_digest": {"type": "string"},
                },
                "required": ["request_id", "op", "target", "args"],
            },
            "annotations": {"readOnlyHint": True},
        },
        {
            "name": "memkraft_execution_describe",
            "description": "Describe MKEP/0 execution capabilities without reading or writing state.",
            "inputSchema": {
                "type": "object",
                "properties": {"request_id": {"type": "string"}},
                "required": ["request_id"],
            },
            "annotations": {"readOnlyHint": True},
        },
    ]


def json_text(payload: Dict[str, Any]) -> str:
    """Deterministic JSON TextContent fallback."""
    from .execution_protocol import MAX_PROTOCOL_ARRAY_LENGTH, mkcjson
    return mkcjson(payload, MAX_PROTOCOL_ARRAY_LENGTH).decode("utf-8")


def dispatch_execution(mk, request: Dict[str, Any], now: str = "") -> Dict[str, Any]:
    """Read-only conduit to the common dispatcher; no apply op is reachable."""
    from .execution_dispatch import MCP_OPS, dispatch as dispatch_mkep
    envelope = dict(request)
    op = envelope.get("op")
    if op not in MCP_OPS:
        envelope["op"] = "__mcp_read_only__"
    if op != "describe" and "now" not in envelope:
        envelope["now"] = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return dispatch_mkep(mk, envelope)


def dispatch(mk, name: str, args: Dict[str, Any]) -> Any:
    """Pure dispatch — no MCP dependency. Unit-testable."""
    # MemKraft's library APIs emit human-facing status messages.  Redirect only
    # tool work, leaving the stdio transport's own protocol stdout intact.
    with contextlib.redirect_stdout(sys.stderr):
        return _dispatch(mk, name, args)


def _dispatch(mk, name: str, args: Dict[str, Any]) -> Any:
    if name == "remember":
        requested_name = _validate_required_text(
            args.get("name"), name="name", max_chars=QUERY_MAX_CHARS,
        )
        info = _validate_remember_info(args.get("info"))
        source = _validate_source(args.get("source", "mcp"))
        entity_type = _validate_required_text(
            args.get("entity_type", "person"), name="entity_type", max_chars=ENTITY_TYPE_MAX_CHARS,
        )
        track = getattr(mk, "track", None)
        path = _existing_memory_path(mk, requested_name)
        if path is None and callable(track):
            # ``update`` deliberately refuses unknown entities.  An MCP
            # remember call means "store this new fact", so establish the
            # entity first while keeping existing tracked entities idempotent.
            tracked_path = track(requested_name, entity_type=entity_type, source=source)
        else:
            tracked_path = None
        if path is None:
            path = tracked_path or _existing_memory_path(mk, requested_name)
        if path is None:
            raise McpMemoryError("remember did not create a memory file")
        memory_name = path.stem
        slug = mk._slugify(memory_name)
        path = mk.live_notes_dir / f"{slug}.md"
        if not path.exists():
            raise McpMemoryError("remember did not create a memory file")
        before_update = path.read_bytes()
        mk.update(memory_name, info, source=source)
        if path.read_bytes() == before_update:
            raise McpMemoryError("remember did not persist the requested memory")
        return {"ok": True, "name": requested_name, "canonical_name": memory_name}
    if name == "search":
        query, strategy, fuzzy, top_k = _search_arguments(args)
        raw = mk.search(query, mode=strategy, fuzzy=fuzzy, top_k=top_k)
        return _cap_search_payload(_normalize_results(raw), top_k=top_k)
    if name == "recall":
        requested_name = _validate_required_text(
            args.get("name"), name="name", max_chars=QUERY_MAX_CHARS,
        )
        path = _existing_memory_path(mk, requested_name)
        memory_name = path.stem if path is not None else _memory_name(mk, requested_name)
        brief = getattr(mk, "brief", None)
        if not callable(brief):
            return _cap_recall_payload({"found": False, "name": requested_name, "text": ""})
        text = str(brief(memory_name) or "")
        # Existence is decided by file presence, not by truthiness of the brief
        # text. ``brief()`` always returns a non-empty dossier (even a
        # "not found" notice), so relying on the old ``or`` fallback masked
        # successful lookups as ``found: False``.
        slug = mk._slugify(memory_name)
        found = (mk.entities_dir / f"{slug}.md").exists() or (
            mk.live_notes_dir / f"{slug}.md"
        ).exists()
        return _cap_recall_payload({"found": found, "name": requested_name, "text": text})
    if name == "link":
        link_add = getattr(mk, "link_add", None)
        if callable(link_add):
            link_add(args["source"], args["target"])
            return {"ok": True}
        return {"ok": False, "error": "link_add not available in this MemKraft version"}
    if name == "memkraft_execution_describe":
        return dispatch_execution(mk, {
            "mkep": "0", "kind": "query", "request_id": args.get("request_id"),
            "op": "describe", "target": {}, "args": {},
        })
    if name == "memkraft_execution_query":
        request = {
            "mkep": "0", "kind": "query", "request_id": args.get("request_id"),
            "op": args.get("op"), "target": args.get("target", {}),
            "args": args.get("args", {}),
        }
        if "capabilities_digest" in args:
            request["capabilities_digest"] = args["capabilities_digest"]
        return dispatch_execution(mk, request)
    raise ValueError(f"unknown tool: {name}")


def _tool_result(types: Any, payload: dict[str, Any], *, is_error: bool,
                 canonical_text: bool = False) -> Any:
    """Build a complete MCP result when the installed SDK supports it."""
    text = json_text(payload) if canonical_text else _payload_text(payload)
    content = [types.TextContent(type="text", text=text)]
    result_type = getattr(types, "CallToolResult", None)
    if result_type is None:
        return content
    return result_type(content=content, structuredContent=payload, isError=is_error)


def _tool_objects(types: Any) -> list[Any]:
    tools = []
    for schema in _tool_schemas():
        kwargs = {
            "name": schema["name"], "description": schema["description"],
            "inputSchema": schema["inputSchema"],
        }
        if "annotations" in schema:
            kwargs["annotations"] = schema["annotations"]
        tools.append(types.Tool(**kwargs))
    return tools


def _handle_tool_call(types: Any, mk: Any, name: str, arguments: Dict[str, Any] | None) -> Any:
    try:
        result = dispatch(mk, name, arguments or {})
        return _tool_result(
            types, result, is_error=not result.get("ok", True),
            canonical_text=name.startswith("memkraft_execution_"),
        )
    except McpInputError as error:
        return _tool_result(types, _error_payload(error.code, str(error)), is_error=True)
    except McpMemoryError as error:
        return _tool_result(types, _error_payload(error.code, str(error)), is_error=True)
    except OSError as error:
        return _tool_result(types, _error_payload("MEMORY_ERROR", str(error)), is_error=True)
    except Exception as error:
        return _tool_result(types, _error_payload("INTERNAL_ERROR", str(error)), is_error=True)


def main() -> None:
    _require_mcp()

    import asyncio
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types

    from .core import MemKraft

    mk = MemKraft()
    if hasattr(Server, "list_tools"):
        # MCP Python SDK 1.x decorator API.
        server = Server("memkraft")

        @server.list_tools()
        async def _list_tools():
            return _tool_objects(types)

        @server.call_tool()
        async def _call_tool(name: str, arguments: Dict[str, Any]):
            return _handle_tool_call(types, mk, name, arguments)
    else:
        # MCP Python SDK 2.x callback API.  Keep the public dependency as
        # ``mcp>=1`` because v1 and v2 are both supported at this boundary.
        async def _list_tools_v2(_context: Any, _params: Any):
            return types.ListToolsResult(tools=_tool_objects(types))

        async def _call_tool_v2(_context: Any, params: Any):
            return _handle_tool_call(types, mk, params.name, params.arguments)

        server = Server(
            "memkraft", on_list_tools=_list_tools_v2, on_call_tool=_call_tool_v2,
        )

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
