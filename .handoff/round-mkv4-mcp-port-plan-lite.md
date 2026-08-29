# MemKraft v4 MCP 안전 계층 이식 — 약식 기획서

**상태:** 구현·로컬 검증 완료, 외부 리뷰 미완료 (v3)
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
| D2 | MCP API·기존 포크 동작 대조 | 완료 | v4 canonical `mk.search(mode=...)`, v4 execution tools 보존, current fork MCP helper diff 확인 |
| D3 | 최소 MCP 계층 구현 | 완료 | `mcp.py`: argument validation, bounded canonical search, dispatch-local stdout redirect, UTF-8 payload cap, complete result wrapper |
| D4 | scratch/Wheel/stdio 검증 | 완료 | focused pytest `26 passed`; `mcp 2.0.0`과 `mcp 1.29.0` fresh-wheel stdio E2E, `memkraft mcp test` scratch 성공 |
| D5 | Grok owner + AGY support 리뷰 | 미완료 | Grok은 tool error 뒤 output 0, AGY는 탐색 계획만 반환; valid findings/self-verification/closure 없음 |

### iter별 수렴

iter 0 | panel=[pre-build scope: user-approved v4.0.2, Madi map, R75e interim] | findings=[] | admission=[] | 적용한 수정=[격리 worktree와 기획서 작성] | 재검증 방식=git tag·경로 확인

iter 1 | panel=[P-A self-check: `.handoff/round-mkv4-mcp-port-versions/self-check-pa-v1.md`] | findings=[F1: shared execution JSON renderer를 변경하려던 범위 침범] | admission=[F1→acc:A1] | 적용한 수정=[memory-tool 전용 `_payload_text`로 분리] | 재검증 방식=focused pytest 25 passed

P-C v1 | 판본=[plan-v1, plan-v2] | 감시 자리=[] | 무한확장 자리=0 | 수리 중단=없음 | 증거=`.handoff/round-mkv4-mcp-port-versions/self-check-pc-v1.md`

iter 2 | panel=[P-A self-check: `.handoff/round-mkv4-mcp-port-versions/self-check-pa-v2.md`] | findings=[F2: `mcp>=1.0`가 설치한 SDK 2.0에서 legacy decorator API 부재, F3: 새 entity remember가 update-only라 실제 저장 실패] | admission=[F2→acc:A2, F3→acc:A3] | 적용한 수정=[SDK 1.x/2.x server registration 분기, remember track→update] | 재검증 방식=focused pytest 26 passed; fresh-wheel MCP 1.29/2.0 stdio E2E

iter 3 | panel=[Grok owner requested, AGY support requested] | findings=[] | admission=[] | 적용한 수정=[] | 재검증 방식=외부 dispatch 결과: Grok output 0/tool error, AGY는 review finding 없이 탐색 계획만 반환; valid review evidence 아님

iter 4 | panel=[Grok owner retry: exact-file-only brief] | findings=[] | admission=[] | 적용한 수정=[] | 재검증 방식=Grok이 global setting parse 뒤 output 0으로 지연되어 중단; finding/self-verification/owner verdict 부재, valid review evidence 아님

iter 5 | panel=[second-opinion 0.9.11 help-verified Grok owner review] | findings=[] | admission=[] | 적용한 수정=[] | 재검증 방식=정식 dispatcher `--mode review --model grok-4.6 --effort medium --timeout 300`으로 재호출했으나 output 0, 동일 global-setting parse/error 상태로 중단; raw receipt는 repository 밖 TEMP에 보존, valid review evidence 아님

iter 6 | panel=[Grok owner: linked-worktree diff packet] | findings=[] | admission=[] | 적용한 수정=[] | 재검증 방식=changed-file list와 patch 내용을 brief에 넣고 `.git` 탐색을 금지한 `--mode review` 호출. `.git` tool error는 재발하지 않았으나 Grok CLI가 global plugin loading 뒤 300초 timeout으로 종료; output 0, finding/self-verification/owner verdict 부재, valid review evidence 아님

iter 7 | panel=[AGY support: linked-worktree diff packet] | findings=[F4: P1 surrogate encoding, F5: P1 MCP 2 constructor aliases, F6: P2 modern search fuzzy/cache forwarding] | admission=[F4→REJECTED(reproduced `errors=replace` returns `?`), F5→REJECTED(fresh MCP 2.0 `CallToolResult(isError=..., structuredContent=...)` succeeds), F6→acc:A4] | 적용한 수정=[`compat.py` smart/v2 mode가 `fuzzy`와 `cache`를 target에 전달; parameterized regression test 추가] | 재검증 방식=focused pytest 28 passed

iter 8 | panel=[post-AGY repair runtime] | findings=[] | admission=[] | 적용한 수정=[] | 재검증 방식=rebuilt v4.0.2 wheel; fresh MCP 2.0 and 1.29 scratch stdio E2E passed with fuzzy=true search and whitespace-query `INVALID_ARGUMENT`; focused pytest 28 passed

iter 9 | panel=[Grok owner repair review] | findings=[F7: P1 payload cap metadata, F8: P1 recall cap metadata, F9: P2 execution MKCJSON, F10: P2 remember persistence, F11: P2 entity type, F12: P2 search hit assertion] | admission=[F7→acc:A5, F8→acc:A6, F9→acc:A7, F10→acc:A8, F11→OUT_OF_SCOPE, F12→acc:A9] | 적용한 수정=[payload cap final-object checks, execution `json_text`, remember persistence check, positive search assertion] | 재검증 방식=focused pytest 30 passed

iter 10 | panel=[Grok owner re-review] | findings=[F13: P1 Korean josa track/update mismatch, F14: P2 recall name cap/type, F15: P3 stale tool doc] | admission=[F13→acc:A10, F14→acc:A11, F15→acc:A12] | 적용한 수정=[track returned path stem used for update/verify, recall name validation/cap, module tool list update] | 재검증 방식=focused pytest 35 passed; rebuilt wheel MCP 2.x Korean josa remember→recall E2E passed

iter 11 | panel=[Grok owner final re-review] | findings=[F16: P2 remember info write-size cap, F17: P3 schema/runtime name maxLength mismatch, F18: P3 remember/recall name display mismatch] | admission=[F16→OUT_OF_SCOPE, F17→BACKLOG, F18→ACCEPTED_RISK] | 적용한 수정=[] | 재검증 방식=owner verdict `PASS_LIMITED`, P0/P1=0; owner reviewed exact final source/test paths

iter 11 | P0/P1=0

P2 disposition | F6 | 수정됨 | `src/memkraft/compat.py` + `tests/test_mcp_safe_layer.py::test_compat_forwards_fuzzy_and_cache_to_mcp_modern_search_modes` |

P2 disposition | F16 | 수정됨 | `remember.info` 64K-character / 256KiB UTF-8 write cap, source/entity_type validation, and matching schema maxLength added with regression test. |

P3 disposition | F17 | 수정됨 | remember/recall name·source·info·entity_type schema maxLength now match runtime guards. |

P3 disposition | F18 | 수정됨 | remember returns both requested `name` and stable on-disk `canonical_name`; recall preserves requested `name` while resolving the actual stored file. |

iter 12 | panel=[Grok owner closure review] | findings=[F19: P2 persistence substring false positive, F20: P3 stale dropped-row truncation paths] | admission=[F19→acc:A13, F20→acc:A14] | 적용한 수정=[pre/post live-note byte comparison, dropped-row truncation path filtering, requested+canonical response identity] | 재검증 방식=focused pytest 38 passed

iter 13 | panel=[Grok owner true closure] | findings=[] | admission=[] | 적용한 수정=[] | 재검증 방식=owner `NO FINDINGS`, `PASS_LIMITED`; rebuilt final v4.0.2 wheel installed in isolated MCP 2.x/1.x venvs; focused pytest 38 passed

iter 13 | P0/P1=0

검증 상태: `PASS_LIMITED` — 모든 owner finding과 남은 P2/P3를 이번 라운드에서 수정했다. AGY is supporting evidence only; live config/installation/shared memory switching remains unapproved.

검증 상태: `PASS_LIMITED` — 이후 Grok owner true-closure가 `NO FINDINGS`를 반환했고, 이번 라운드의 P0/P1/P2/P3 처분을 완료했다.

iter 14 | panel=[user-approved live application] | findings=[] | admission=[] | 적용한 수정=[Codex/Claude memkraft MCP command/args를 dedicated v4 live venv로 전환; Codex stale PYTHONPATH 제거] | 재검증 방식=[두 config parser 통과, exact Codex config subprocess tools/list + shared-memory read-only search 3 results] | rollback=[.scratch/live-config-backups/ 20260829-131500 files restore + host restart]

### P2 disposition 대장

없음.
