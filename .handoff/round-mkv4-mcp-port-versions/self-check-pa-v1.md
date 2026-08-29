# P-A 자가 범위 점검 — 구현 v1

**상류:** `.handoff/round-mkv4-mcp-port-plan-lite.md` v1
**대상:** `src/memkraft/mcp.py`, `tests/test_v081_mcp.py`, `tests/test_execution_mcp.py`, `tests/test_mcp_safe_layer.py` diff
**as-of:** 미정 — 기획서는 untracked라 승인 시각을 파일 메타데이터로 확정할 수 없다.

## 자체 점검

1. 행 수·의미 불일치: search schema·dispatch·테스트에서 `strategy`, `fuzzy`, `top_k`를 모두 대조했다.
2. 조항 간 직접 모순: shared execution tool의 canonical `json_text`를 변경하려던 초안은 범위 밖이라 되돌리고, memory-tool 전용 `_payload_text`로 분리했다.
3. 같은 단어의 다른 의미: `strategy`와 upstream `mode`를 동일한 세 값으로 1:1 전달한다.
4. 권위/게이트 충족성: user-requested lite/Grok owner route는 정식 reciprocal authority가 아니므로 `PASS_LIMITED` ceiling을 유지한다.
5. 수치 전제의 진실성: `top_k=1..20`, field=2,000 chars, search=64 KiB, recall=256 KiB는 계약 테스트로 일부 검증했고 full stdio/wheel 검증은 남아 있다.

## 네 축

- ① 넘침: 없음. 처음에는 `json_text` fallback을 넓혀 execution MCP tool까지 영향을 줄 뻔했으나, 이식 범위 밖이라 제거했다.
- ② 모자람: D4와 D5 검증은 아직 구현 diff에 포함되지 않았으며, 기획서의 다음 단계로 남긴다.
- ③ 침범: 없음. domain/store/locking 파일은 수정하지 않았다. 테스트 3개는 MCP contract에 직접 대응한다.
- ④ 상류 사후 정합: `UNVERIFIED` — untracked plan의 승인 시각이 없다.

고친 것: [축 ①] `src/memkraft/mcp.py` `json_text` → 기존 execution-protocol canonicalization을 보존하고 memory-tool 전용 JSON renderer로 분리.

안 고친 것: [축 ④] as-of → 없는 승인 시각을 만들지 않는다.
