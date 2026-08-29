# Maintained Fork: v4 MCP Port

This document is the source of truth for the maintained fork's MCP changes.
Read it before changing `src/memkraft/mcp.py`, `src/memkraft/compat.py`, or an
MCP host command.

## Base and scope

- **Upstream base:** `seojoonkim/memkraft` tag `v4.0.2`
  (`33b5092946471fab810407a1ebcbeb30e12488ed`)
- **Fork branch:** `codex/mcp-v4-port`
- **Changed production files:** `src/memkraft/mcp.py`,
  `src/memkraft/compat.py`
- **Changed tests:** `tests/test_execution_mcp.py`,
  `tests/test_v081_mcp.py`, `tests/test_mcp_safe_layer.py`

The port changes the MCP transport and compatibility delegation only. It does
not change the store core, Windows locking implementation, memory file format,
or migration policy.

## Why this fork exists

Upstream `v4.0.2` exposed legacy MCP search directly:

```python
mk.search(query, fuzzy=True)
```

The maintained fork makes modern, bounded MCP retrieval the default and moves
the previously machine-local fast-search behavior into the package server. It
replaces a separate `memkraft_fast_mcp.py` wrapper at deployment time; do not
copy that old wrapper back into this module.

## Behavioral diff from upstream

| Area | Upstream v4.0.2 | Maintained fork |
|---|---|---|
| Default search | `search(..., fuzzy=True)` | `search(..., mode="smart", fuzzy=False, top_k=8)` |
| Search selection | No MCP strategy | `strategy`: `smart`, `v2`, `legacy` |
| Result bound | No MCP `top_k` bound | Integer `top_k`, range 1–20 |
| Search response | Raw list | `results`, `total_results`, `returned_results`, truncation metadata |
| Payload protection | No MCP byte cap | Search 64 KiB; recall 256 KiB; UTF-8 JSON |
| Protocol stdout | Library status output may leak | Tool dispatch output redirects to stderr |
| Error envelope | Generic text failure | `INVALID_ARGUMENT`, `MEMORY_ERROR`, `INTERNAL_ERROR` with MCP `isError` |
| Remember | `update()` can no-op for an unknown entity | Existing file resolution, otherwise track then update; success requires a byte change |
| Korean names | Repeated josa normalization can split files | Existing raw slug is preferred, then one normalized slug |
| MCP SDK | Legacy decorator API | SDK 1.x decorator and 2.x callback server support |

## Tool contract

### `search`

```json
{
  "query": "required non-empty query",
  "strategy": "smart",
  "fuzzy": false,
  "top_k": 8
}
```

- `smart` and `v2` use canonical `MemKraft.search(mode=...)`.
- The compatibility layer forwards both `fuzzy` and `cache` for those modes.
- `legacy` is available only when explicitly requested.
- The response includes result counts and explicit truncation metadata.

### `remember`

```json
{
  "name": "requested display name",
  "info": "non-empty text",
  "source": "optional source, default mcp",
  "entity_type": "optional type, default person"
}
```

- `name` and `source`: at most 2,000 characters.
- `entity_type`: at most 64 characters.
- `info`: at most 65,536 characters and 256 KiB after UTF-8 size checking.
- Success returns the requested `name` and the on-disk `canonical_name`.
- Supported inputs are ordinary valid Unicode text. Do not send unpaired
  surrogate code points; they are outside the supported MCP write contract.

### `recall`

`recall(name)` preserves the requested name in its response but resolves an
existing raw-slug file before applying one Korean-josa normalization pass.

## Intentional non-changes

- Do **not** reintroduce a Windows no-op `fcntl` shim. Upstream v4's real
  Windows lock behavior remains intact.
- Do **not** alter shared memory files during installation or configuration.
- Do **not** use a global Python, `pipx`, or a stale `PYTHONPATH` for this
  runtime.

## Installation and rollout

Use a dedicated virtual environment and the wheel built from this checkout.

```powershell
python -m venv .live-venv
.\.live-venv\Scripts\python.exe -m pip install "dist\memkraft-4.0.2-py3-none-any.whl[mcp]"
```

Configure the host command as:

```text
<checkout>\.live-venv\Scripts\python.exe -u -m memkraft.mcp
```

Set `MEMKRAFT_DIR` to the existing absolute memory directory and set
`PYTHONUTF8=1` plus `PYTHONIOENCODING=utf-8`. Back up host configuration first
and restart the host after editing it; existing MCP child processes keep their
old command until restart.

## Verification evidence

- Focused MCP suite: **38 passed**.
- Built wheel tested in fresh MCP Python SDK 1.29 and 2.x environments.
- Scratch stdio: `tools/list`, `remember`, `search`, `recall`, and invalid
  input cases.
- Korean josa round-trip: `remember("고양이를")` then
  `recall("고양이를")`.
- Live rollout smoke: configured shared-memory `search` only, after host
  configuration switch.
- Final owner review: `NO FINDINGS`, assurance `PASS_LIMITED`.

`PASS_LIMITED` reflects the user-selected Grok-owner / AGY-support review
topology, not an unresolved code finding in the reviewed scope.

## Agent handoff

1. Preserve bounded smart search, stdout isolation, byte caps, Korean name
   resolution, and MCP SDK 1.x/2.x support.
2. Run the focused MCP tests before claiming completion.
3. Do not change live MCP configuration, shared memory, global installation,
   commit, push, or release metadata without explicit user approval.
4. When upstream releases a newer stable tag, compare `mcp.py`, `compat.py`,
   and the MCP tests before rebasing. Do not automatically move to upstream
   `main`.
