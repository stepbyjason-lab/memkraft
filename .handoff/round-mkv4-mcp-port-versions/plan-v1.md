# MemKraft v4 MCP 안전 계층 이식 — 약식 기획서

**상태:** 진행 중
**기준:** upstream `v4.0.2` (`33b5092946471fab810407a1ebcbeb30e12488ed`)
**작업 브랜치:** `codex/mcp-v4-port`
**경로:** `D:\Code\memkraft-v4-mcp`

## 1. 목표

upstream MemKraft `v4.0.2` 위에 현재 포크의 MCP 안전성·성능 동작만 작게 이식한다. 기본 검색을 bounded smart search로 바꾸고, 인수 검증·오류 envelope·JSON-RPC stdout 보호·Unicode 안전 payload 제한을 추가한다.

## 2. 범위 In / Out

### In

- `src/memkraft/mcp.py`의 `remember`, `search`, `recall` MCP 도구 계층
- 계약 테스트와 MCP stdio scratch E2E
- 패키지 wheel fresh-install 검증
- Grok owner 리뷰와 AGY supporting review의 원문·영수증·수렴 기록

### Out

- `C:\Users\ysmer\.memkraft\memory` 읽기·쓰기 — 사용자의 기존 기억을 보존하기 위해 제외
- live Codex/Claude MCP 설정, 전역/pipx 설치, remote push, release, PyPI — 외부 효과와 복구 범위가 생기므로 별도 승인 전까지 제외
- `store_core.py` 및 Windows 잠금 구현 — upstream의 실제 `msvcrt.locking()`을 보존하기 위해 제외
- memory data migration, 자동 동기화, 무관한 refactor — MCP 계층 이식 목표와 무관하므로 제외

## 3. 완료 조건

1. `search` 기본 호출은 `mk.search(query, mode="smart", fuzzy=False, top_k=8)`이며 `top_k`는 1..20 정수만 허용한다.
2. `strategy=smart|v2|legacy`는 명시적으로 upstream mode로 변환하며, 그 밖의 값·빈 query·잘못된 type은 안정된 `INVALID_ARGUMENT` 오류가 된다.
3. tool dispatch 중 우발 stdout이 JSON-RPC stdout으로 새지 않는다.
4. `search`와 `recall`은 UTF-8/JSON 유효성을 보존하며 result 수와 긴 text field를 제한하고, 잘렸으면 metadata로 표시한다.
5. success/error 모두 `content`, `structuredContent`, `isError` MCP 규약을 지킨다.
6. upstream suite, 신규 계약 테스트, scratch `MEMKRAFT_DIR` MCP stdio E2E, Windows 경로 smoke, wheel fresh-install이 통과한다.
7. **관측 종결문:** scratch-only 환경에서 MCP stdio `tools/list → remember → search → recall`과 오류 요청을 실행해, protocol stdout에 JSON-RPC 외 줄이 없고 한글 결과가 유효 JSON으로 되돌아온다.

## 4. 미승인 — Chair가 정한 것

- Madi 원칙상 MCP/AI 경계는 위험 3이라 약식의 일반 대상이 아니다. 사용자가 약식을 명시했으므로 이 문서는 그 요청을 기록하되, 정식 reciprocal owner가 아닌 Grok owner/AGY support 조합의 최종 보증은 `PASS_LIMITED` 이하로 공시한다.
- v4.0.2의 package version은 이번 작업에서 변경하지 않는다. 공개 fork 버전(`4.0.2.post1` 등)과 release route는 별도 승인 사항이다.
- 실사용 memory 호환성은 라이브 전환 단계의 read-only search 검증 전까지 주장하지 않는다.

## 5. 근거 — 사용자 발화 원문

> "사실상 클론해서 mcp 패치만 하는 거네. 작업은 그리 크진 않겠네?"

> "마디 약식 절차로(d:\\code\\madi\\madi-map.md 할것이고 D:\\Code\\madi/.handoff/r75e-author-pipeline-interim.md 이 문서내용보고 적용해서 진행해줘."

> "리뷰는 owner는 grok으로 서포트로 agy를 부르면 돼."

> "업데이트 해도 기존 기억내용에는 영향이 없지?"

> "새버전으로 작업 진행해줘."

## 6. 진척과 수렴 로그

### 설계 ID별 진척

| ID | 항목 | 상태 | 증거 |
|---|---|---|---|
| D1 | v4.0.2 격리 worktree | 완료 | `git worktree add -b codex/mcp-v4-port D:\\Code\\memkraft-v4-mcp v4.0.2` |
| D2 | MCP API·기존 포크 동작 대조 | 진행 중 | 다음 단계 |
| D3 | 최소 MCP 계층 구현 | 대기 | D2 이후 |
| D4 | scratch/Wheel/stdio 검증 | 대기 | D3 이후 |
| D5 | Grok owner + AGY support 리뷰 | 대기 | D4 이후 |

### iter별 수렴

iter 0 | panel=[pre-build scope: user-approved v4.0.2, Madi map, R75e interim] | findings=[] | admission=[] | 적용한 수정=[격리 worktree와 기획서 작성] | 재검증 방식=git tag·경로 확인

### P2 disposition 대장

없음.
