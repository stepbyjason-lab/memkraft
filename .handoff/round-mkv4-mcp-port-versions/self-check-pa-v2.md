# P-A 자가 범위 점검 — 구현 v2

**상류:** `.handoff/round-mkv4-mcp-port-plan-lite.md` v2
**대상:** 현재 `src/memkraft/mcp.py` 및 MCP contract tests diff
**as-of:** 미정 — 기획서가 untracked라 승인 시각을 만들지 않는다.

## 자체 점검

1. 행 수·의미 불일치: SDK 1.x/2.x의 server registration만 분기하고, 공통 tool schemas와 `_handle_tool_call`은 하나로 유지했다.
2. 조항 간 직접 모순: `remember`의 성공 응답과 실제 저장 의미가 어긋나던 문제를 `track` 후 `update`로 맞췄다.
3. 같은 단어의 다른 의미: `strategy`는 upstream `mode` 값이고, `remember`는 새 entity를 저장한다는 MCP tool 의미로 해석했다.
4. 권위/게이트 충족성: Grok owner와 AGY support dispatch는 완료 finding/receipt를 만들지 못했다. 독립 리뷰 closure가 없다.
5. 수치 전제의 진실성: focused 26 tests, mcp 1.29 및 2.0 fresh-wheel E2E, scratch `mcp test`를 실행했다. full suite Windows baseline은 store-core lock failure로 green 증명이 없다.

## 네 축

- ① 넘침: 없음. MCP 2.x callback 지원은 upstream metadata가 이미 허용하는 `mcp>=1.0` 실제 설치 범위의 server-start failure를 고친 최소 transport 경계다.
- ② 모자람: 외부 owner closure는 미충족이다. 코드가 아니라 provider output failure이며 final claim을 낮춘다.
- ③ 침범: 없음. `mcp.py`와 MCP contract tests 이외의 domain/store/lock code를 바꾸지 않았다.
- ④ 상류 사후 정합: `UNVERIFIED` — untracked plan approval time 부재.

고친 것: [축 ②] `mcp.py` `remember` → `track` 후 `update`; `mcp.py` main → MCP SDK 1.x decorator/2.x callback dual registration.

안 고친 것: [축 ②] Grok/AGY review closure → provider가 valid finding artifact를 반환하지 않아 수리 대상이 아니다. `PASS` claim을 하지 않는다.
