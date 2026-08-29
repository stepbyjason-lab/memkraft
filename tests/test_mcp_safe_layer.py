"""Contract tests for the bounded MCP memory tools."""
from __future__ import annotations

import json

import pytest

from memkraft import mcp
from memkraft.compat import install_v3_compat


class SearchSpy:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        print("library status must not reach JSON-RPC stdout")
        return self.result


def test_remember_tracks_before_updating(tmp_path):
    from memkraft import MemKraft

    mk = MemKraft(base_dir=str(tmp_path))
    mk.init(verbose=False)
    result = mcp.dispatch(mk, "remember", {"name": "새 엔터티", "info": "새 사실"})

    assert result == {"ok": True, "name": "새 엔터티", "canonical_name": "새-엔터티"}
    assert "새 사실" in (mk.live_notes_dir / "새-엔터티.md").read_text(encoding="utf-8")


def test_remember_uses_the_same_korean_josa_normalization_for_track_and_update(tmp_path):
    from memkraft import MemKraft

    mk = MemKraft(base_dir=str(tmp_path))
    mk.init(verbose=False)

    result = mcp.dispatch(mk, "remember", {"name": "고양이를", "info": "집 고양이"})

    assert result == {"ok": True, "name": "고양이를", "canonical_name": "고양이"}
    path = mk.live_notes_dir / "고양이.md"
    assert path.exists()
    assert "집 고양이" in path.read_text(encoding="utf-8")

    repeated = mcp.dispatch(mk, "remember", {"name": "고양이를", "info": "두 번째 기록"})
    canonical_lookup = mcp.dispatch(mk, "recall", {"name": "고양이"})
    particle_lookup = mcp.dispatch(mk, "recall", {"name": "고양이를"})

    assert repeated["canonical_name"] == "고양이"
    assert canonical_lookup["found"] is True
    assert particle_lookup["found"] is True
    assert "두 번째 기록" in canonical_lookup["text"]


@pytest.mark.parametrize("value", [None, "", 1, "가" * (mcp.QUERY_MAX_CHARS + 1)])
def test_recall_rejects_invalid_or_unbounded_names(value, tmp_path):
    from memkraft import MemKraft

    mk = MemKraft(base_dir=str(tmp_path))
    mk.init(verbose=False)

    with pytest.raises(mcp.McpInputError):
        mcp.dispatch(mk, "recall", {"name": value})


def test_remember_schema_and_runtime_bound_write_inputs(monkeypatch, tmp_path):
    from memkraft import MemKraft

    schema = next(tool for tool in mcp._tool_schemas() if tool["name"] == "remember")["inputSchema"]
    assert schema["properties"]["name"]["maxLength"] == mcp.QUERY_MAX_CHARS
    assert schema["properties"]["info"]["maxLength"] == mcp.REMEMBER_INFO_MAX_CHARS
    assert schema["properties"]["source"]["maxLength"] == mcp.SOURCE_MAX_CHARS
    assert schema["properties"]["entity_type"]["default"] == "person"

    mk = MemKraft(base_dir=str(tmp_path))
    mk.init(verbose=False)
    monkeypatch.setattr(mcp, "REMEMBER_INFO_MAX_BYTES", 10)
    with pytest.raises(mcp.McpInputError, match="info is too long"):
        mcp.dispatch(mk, "remember", {"name": "x", "info": "가가가가"})


def test_search_defaults_to_bounded_canonical_smart_search(capsys):
    mk = SearchSpy([{"file": "x.md", "snippet": "한글 결과"}])

    result = mcp.dispatch(mk, "search", {"query": "  한글 질의  "})

    assert mk.calls == [("한글 질의", {"mode": "smart", "fuzzy": False, "top_k": 8})]
    assert result["results"][0]["snippet"] == "한글 결과"
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("strategy", ["smart", "v2", "legacy"])
def test_search_maps_supported_strategies_to_canonical_mode(strategy):
    mk = SearchSpy([])

    mcp.dispatch(mk, "search", {"query": "q", "strategy": strategy, "fuzzy": True, "top_k": 1})

    assert mk.calls == [("q", {"mode": strategy, "fuzzy": True, "top_k": 1})]


@pytest.mark.parametrize("mode", ["smart", "v2"])
def test_compat_forwards_fuzzy_and_cache_to_mcp_modern_search_modes(mode):
    class CompatSpy:
        calls = []

        def append_event(self, *args, **kwargs):
            return None

        def search(self, query, **kwargs):
            self.calls.append(("legacy", query, kwargs))
            return []

        def search_v2(self, query, **kwargs):
            self.calls.append(("v2", query, kwargs))
            return []

        def search_smart(self, query, **kwargs):
            self.calls.append(("smart", query, kwargs))
            return []

        def search_hybrid(self, query, **kwargs):
            self.calls.append(("hybrid", query, kwargs))
            return []

    install_v3_compat(CompatSpy)
    mk = CompatSpy()

    mk.search("query", mode=mode, fuzzy=True, cache=False, top_k=3)

    assert mk.calls == [(mode, "query", {"top_k": 3, "fuzzy": True, "cache": False})]


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"query": ""}, "query must not be empty"),
        ({"query": 1}, "query must be a string"),
        ({"query": "q", "strategy": "other"}, "strategy must be one of"),
        ({"query": "q", "top_k": 0}, "top_k must be between"),
        ({"query": "q", "top_k": True}, "top_k must be an integer"),
        ({"query": "q", "fuzzy": "false"}, "fuzzy must be a boolean"),
    ],
)
def test_search_rejects_invalid_arguments(arguments, message):
    with pytest.raises(mcp.McpInputError, match=message):
        mcp.dispatch(SearchSpy([]), "search", arguments)


def test_search_payload_is_bounded_and_unicode_safe():
    mk = SearchSpy([
        {"file": f"{index}.md", "snippet": "가" * 3_000}
        for index in range(20)
    ])

    result = mcp.dispatch(mk, "search", {"query": "가", "top_k": 20})

    encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
    assert len(encoded) <= mcp.SEARCH_PAYLOAD_MAX_BYTES
    assert result["truncated"] is True
    assert result["truncated_fields"]


def test_payload_caps_include_metadata(monkeypatch):
    search_results = [{"file": "one.md", "snippet": "가" * 100}]
    uncapped = {
        "results": search_results,
        "total_results": 1,
        "truncated": False,
        "truncated_fields": [],
    }
    monkeypatch.setattr(mcp, "SEARCH_PAYLOAD_MAX_BYTES", len(mcp._json_bytes(uncapped)) + 1)
    search = mcp._cap_search_payload(search_results, top_k=1)
    assert len(mcp._json_bytes(search)) <= mcp.SEARCH_PAYLOAD_MAX_BYTES

    recall_source = {"found": True, "name": "x", "text": "가" * 100}
    monkeypatch.setattr(mcp, "RECALL_PAYLOAD_MAX_BYTES", len(mcp._json_bytes(recall_source)) + 1)
    recall = mcp._cap_recall_payload(recall_source)
    assert len(mcp._json_bytes(recall)) <= mcp.RECALL_PAYLOAD_MAX_BYTES
    assert recall["truncated"] is True


def test_search_payload_drops_truncation_paths_for_removed_rows(monkeypatch):
    results = [
        {"file": f"{index}.md", "snippet": "가" * 3_000}
        for index in range(2)
    ]
    monkeypatch.setattr(mcp, "SEARCH_PAYLOAD_MAX_BYTES", 7_000)

    payload = mcp._cap_search_payload(results, top_k=2)

    assert all(
        not field.startswith("results[")
        or int(field.split("[", 1)[1].split("]", 1)[0]) < payload["returned_results"]
        for field in payload["truncated_fields"]
    )


def test_remember_requires_a_file_change_for_existing_entity(tmp_path):
    from memkraft import MemKraft

    mk = MemKraft(base_dir=str(tmp_path))
    mk.init(verbose=False)
    mcp.dispatch(mk, "remember", {"name": "existing", "info": "first"})

    original_update = mk.update
    mk.update = lambda *args, **kwargs: None
    with pytest.raises(mcp.McpMemoryError):
        mcp.dispatch(mk, "remember", {"name": "existing", "info": "core"})
    mk.update = original_update


class RecallSpy:
    entities_dir = None
    live_notes_dir = None

    def _slugify(self, name):
        return name

    def brief(self, name):
        print("dossier noise")
        return "다" * (mcp.RECALL_PAYLOAD_MAX_BYTES // 2)


def test_recall_payload_is_bounded_and_dispatch_does_not_write_stdout(monkeypatch, tmp_path, capsys):
    mk = RecallSpy()
    mk.entities_dir = tmp_path
    mk.live_notes_dir = tmp_path

    result = mcp.dispatch(mk, "recall", {"name": "한국어"})

    assert len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= mcp.RECALL_PAYLOAD_MAX_BYTES
    assert result["truncated"] is True
    assert capsys.readouterr().out == ""


def test_tool_result_contains_text_structured_content_and_error_flag():
    class FakeTypes:
        class TextContent:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class CallToolResult:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

    payload = mcp._error_payload("INVALID_ARGUMENT", "잘못된 입력")
    result = mcp._tool_result(FakeTypes, payload, is_error=True)

    assert result.isError is True
    assert result.structuredContent == payload
    assert json.loads(result.content[0].text) == payload


def test_execution_tool_result_uses_protocol_canonical_json():
    class FakeTypes:
        class TextContent:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class CallToolResult:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

    payload = {"ok": True, "nested": {"z": False, "a": None}}
    result = mcp._tool_result(FakeTypes, payload, is_error=False, canonical_text=True)

    assert result.content[0].text == mcp.json_text(payload)
