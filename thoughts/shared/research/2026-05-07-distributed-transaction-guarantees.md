---
date: 2026-05-07T14:30:04+0900
researcher: SAN KIM
git_commit: 221ca3586f04f6a6afa99f21f2bd98770f3ead07
branch: develop
repository: medusa-fork
topic: "여러 모듈 간 작업의 최종 결과 보장 — 보상 트랜잭션 한계와 영속성 메커니즘"
tags: [research, codebase, workflows-sdk, orchestration, saga, compensation, durability]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
---

# Research: 여러 모듈 간 작업의 최종 결과 보장 — 보상 트랜잭션 한계와 영속성 메커니즘

**Date**: 2026-05-07T14:30:04+0900
**Researcher**: SAN KIM
**Git Commit**: 221ca3586f04f6a6afa99f21f2bd98770f3ead07
**Branch**: develop
**Repository**: medusa-fork

## Research Question

이 서비스(Medusa)에서 여러 모듈 간 작업의 최종적 결과(eventual consistency / 일관성)가 보장되는가? 보상 트랜잭션(Saga compensation)만으로 완벽하게 되는지에 대한 의문.

## Summary

본 절은 코드베이스의 현 상태를 사실로만 기술한다(평가/개선 제안 없음). 각 결론에 **사실 / 추정 / 모름** 라벨을 표기했다.

- **사실**: Medusa는 분산 일관성을 위해 2-Phase Commit이 아닌 **Saga 패턴(보상 트랜잭션)** 만을 사용한다. 코드베이스에 outbox, 2PC, XA 트랜잭션 구현은 없다.
- **사실**: 한 워크플로우의 step들은 **각자 독립된 DB 트랜잭션**을 연다. step A가 커밋된 뒤 step B가 실패하면 A의 DB 데이터는 보상 step의 애플리케이션 레이어 호출(`deleteOrders` 등)로 되돌린다. step A·B가 단일 ACID 트랜잭션을 공유하지 않는다.
- **사실**: 보상 함수 자체가 실패하고 `maxRetries`를 초과하면 워크플로우는 `TransactionState.FAILED` dead state로 종료된다. `REVERTED`(완전 롤백)와 명시적으로 구분된다. 보상 실패 시 자동 복구 메커니즘은 코드에서 확인되지 않는다.
- **사실**: 외부 시스템(결제 PSP)에 대한 step들 중 `capturePaymentStep`, `refundPaymentStep`은 **compensateFn이 의도적으로 누락**되어 있다. 코드 주석으로 "이미 자금이 이동했으므로 자동 보상하지 않는다"고 명시.
- **사실**: DB 커밋과 이벤트 발행 사이에 원자성을 보장하는 outbox 패턴은 없다. `@EmitEvents()`는 메서드 종료(=DB 커밋) **이후** 이벤트를 발행한다. 그 사이 프로세스가 죽으면 이벤트는 유실된다.
- **사실**: 워크플로우 실행 상태는 PostgreSQL `workflow_execution` 테이블에 영속화되며, 단 `store: true` 또는 finished/waiting 상태일 때만 저장된다. 동기 step만으로 구성된 워크플로우는 중간 상태가 DB에 기록되지 않는다.
- **사실**: in-memory 엔진은 retry/timeout 타이머가 프로세스 메모리 `Map<NodeJS.Timeout>`에만 존재 — 재기동 시 유실. redis 엔진(BullMQ)은 Redis에 영속되어 재기동 후 자동 처리.
- **추정**: 단일 인스턴스 + in-memory 엔진 환경에서는 프로세스 크래시 시점에 따라 보상이 실행되지 않거나 부분 보상이 이루어질 수 있다. 외부 호출이 영영 응답하지 않는 async step에 `timeout` 옵션이 없으면 무한히 `WAITING` 상태로 남는다.

**결론(사실+추정)**: 보상 트랜잭션만으로 "완벽한" 결과 보장은 코드 레벨에서 이루어지지 않는다. 외부 효과(PSP, 이메일)는 의도적으로 보상 범위 밖이고, 보상 자체의 실패는 dead state로 종료된다. 다만 실행 상태 영속화 + redis 엔진 + 명시적 보상 step 작성으로 실패 시나리오 대부분에 대해 "결과적 일관성을 회복할 수 있는 hook"은 제공한다.

## Detailed Findings

### 1. 분산 트랜잭션 모델 — Saga 기반

Medusa의 워크플로우는 자체 구현된 분산 트랜잭션 오케스트레이터로 동작한다. 2PC/XA가 아닌 Saga 패턴.

**핵심 컴포넌트**:
- `TransactionOrchestrator` — 스텝 실행 루프, 상태 전이 ([transaction-orchestrator.ts](packages/core/orchestration/src/transaction/transaction-orchestrator.ts))
- `DistributedTransaction` / `TransactionStep` — 트랜잭션·스텝 객체와 체크포인트 ([distribuited-transaction.ts](packages/core/orchestration/src/transaction/distribuited-transaction.ts))
- `MedusaWorkflow` — 외부 진입점 (`run()`, `registerStepSuccess()`, `registerStepFailure()`) ([medusa-workflow.ts](packages/core/workflows-sdk/src/utils/medusa-workflow.ts))

**상태 enum** ([types.ts](packages/core/orchestration/src/transaction/types.ts)):
- `TransactionStepState`: `NOT_STARTED | INVOKING | COMPENSATING | DONE | REVERTED | FAILED | DORMANT | SKIPPED | SKIPPED_FAILURE | TIMEOUT | IDLE | PERMANENT_FAILURE`
- `TransactionState`: `NOT_STARTED | INVOKING | WAITING_TO_COMPENSATE | COMPENSATING | DONE | REVERTED | FAILED | SKIPPED | DORMANT | TIMEOUT`

### 2. 보상(Compensation) 흐름

**트리거**: step이 `maxRetries`를 초과해 영구 실패하면 `setStepFailure()`가 `flow.state = WAITING_TO_COMPENSATE`로 전환 ([transaction-orchestrator.ts:860](packages/core/orchestration/src/transaction/transaction-orchestrator.ts#L860)).

**실행 순서**: `getCompensationSteps()`가 `depth` 내림차순으로 정렬 — 나중 실행된 step이 먼저 보상됨 ([transaction-orchestrator.ts:191-203](packages/core/orchestration/src/transaction/transaction-orchestrator.ts#L191-L203)). 같은 depth의 형제 step들은 병렬로 보상.

**StepResponse → 보상 입력**: `new StepResponse(output, compensateInput)`의 두 번째 인자가 보상 함수에 전달. 미지정 시 `output`이 그대로 전달 ([step-response.ts:36-44](packages/core/workflows-sdk/src/utils/composer/helpers/step-response.ts#L36-L44), [create-step-handler.ts:120-135](packages/core/workflows-sdk/src/utils/composer/helpers/create-step-handler.ts#L120-L135)).

**`noCompensation`**: `createStep`에 두 번째 인자가 없으면 자동으로 `noCompensation: true` 설정 → 보상 단계에서 즉시 `REVERTED`로 마크되고 실제 호출은 일어나지 않음 ([create-step.ts:184](packages/core/workflows-sdk/src/utils/composer/create-step.ts#L184), [transaction-orchestrator.ts:1097-1100](packages/core/orchestration/src/transaction/transaction-orchestrator.ts#L1097-L1100)).

### 3. 보상 자체가 실패할 때 (사용자 핵심 우려)

**사실** — 보상 함수가 throw 하면 동일한 `maxRetries`/`retryInterval` 정책으로 재시도된다. 기본 `maxRetries`는 `0` (`DEFAULT_RETRIES`, [transaction-orchestrator.ts:84](packages/core/orchestration/src/transaction/transaction-orchestrator.ts#L84)).

재시도가 모두 실패하면:
1. step 상태 → `FAILED` + `PERMANENT_FAILURE` ([transaction-orchestrator.ts:805-862](packages/core/orchestration/src/transaction/transaction-orchestrator.ts#L805-L862))
2. `flow.state` → `TransactionState.FAILED` (REVERTED와 구분되는 dead state) ([transaction-orchestrator.ts:362-368](packages/core/orchestration/src/transaction/transaction-orchestrator.ts#L362-L368))
3. `transaction.errors[]`에 모든 실패 기록 (`addError()`)
4. `saveCheckpoint()` → `workflow_execution` DB 테이블 upsert ([distribuited-transaction.ts:539](packages/core/orchestration/src/transaction/distribuited-transaction.ts#L539))

**자동 복구 메커니즘 없음 (사실)** — 코드에서 dead state 이후 외부 알림이나 자동 재시도 트리거는 확인 안 됨. 운영자가 수동 개입하거나 별도 모니터링 코드가 필요하다.

### 4. 모듈 간 DB 트랜잭션 경계

**사실** — `@InjectTransactionManager()`/`@InjectManager()`는 단일 모듈의 `baseRepository_` 커넥션 내에서만 동작 ([inject-transaction-manager.ts:24-69](packages/core/utils/src/modules-sdk/decorators/inject-transaction-manager.ts#L24-L69), [inject-manager.ts:22-66](packages/core/utils/src/modules-sdk/decorators/inject-manager.ts#L22-L66)).

**사실** — 워크플로우 step의 `StepExecutionContext`는 `transactionManager`를 step 경계 너머로 전달하지 않는다 ([create-step-handler.ts:12-53](packages/core/workflows-sdk/src/utils/composer/helpers/create-step-handler.ts#L12-L53)). step A가 모듈 A 트랜잭션을 열어 커밋, step B가 모듈 B 트랜잭션을 따로 열어 실행 — 두 DB 트랜잭션은 별개.

**시나리오: A 커밋 후 B 실패**
- 보상 step이 정의된 경우: A의 보상 step이 애플리케이션 레이어에서 데이터 삭제/취소 호출 (예: `createOrdersStep`의 보상은 `deleteOrders(createdIds)` — [create-orders.ts:43-50](packages/core/core-flows/src/order/steps/create-orders.ts#L43-L50)).
- 보상 step이 없는 경우: A의 데이터는 그대로 남음.

### 5. 외부 시스템 호출의 보상 한계

**사실** — 결제 관련 step들은 의도적으로 compensateFn이 없다.

```typescript
// packages/core/core-flows/src/payment/steps/capture-payment.ts
// 주석: "We don't want to compensate a capture automatically as the actual
//       funds have already been taken."
export const capturePaymentStep = createStep(
  capturePaymentStepId,
  async (input, { container }) => { ... }
  // compensateFn 없음
)
```

`refundPaymentStep`도 동일 ([refund-payment.ts](packages/core/core-flows/src/payment/steps/refund-payment.ts)).

**모름** — `paymentModule.capturePayment` 내부에 멱등성 키 검증 또는 PSP 레벨 idempotency가 있는지는 본 조사에서 추적하지 않음.

### 6. 이벤트 발행 vs DB 커밋 — outbox 부재

**사실** — `@EmitEvents()` 데코레이터는 원본 메서드 완료(=DB 커밋) **이후** `emitEvents_`를 호출 ([emit-events.ts](packages/core/utils/src/modules-sdk/decorators/emit-events.ts)). DB 커밋 → 이벤트 발행 사이에 프로세스 크래시 시 이벤트 유실.

**사실** — `eventGroupId` 기반의 staged emit:
- `LocalEventBus`: 메모리 `groupedEventsMap_` 저장. 프로세스 재시작 시 유실 ([event-bus-local.ts:86-118](packages/modules/event-bus-local/src/services/event-bus-local.ts#L86-L118))
- `RedisEventBus`: `staging:{eventGroupId}` 키에 `rpush` (TTL 600초). 프로세스 재시작 후에도 생존 ([event-bus-redis.ts:207-261](packages/modules/event-bus-redis/src/services/event-bus-redis.ts#L207-L261))

**사실** — Outbox 패턴(이벤트를 DB 트랜잭션 안에 함께 쓰는 방식)은 코드에서 확인되지 않음.

### 7. 워크플로우 상태 영속성 (Durability)

**저장 매체** — PostgreSQL `workflow_execution` 테이블 ([workflow-execution.ts:4-58](packages/modules/workflow-engine-inmemory/src/models/workflow-execution.ts#L4-L58)):

```
workflow_execution
├── id, workflow_id, transaction_id, run_id
├── execution  JSON  ← TransactionFlow 전체
├── context    JSON  ← { data, errors }
├── state      enum  ← NOT_STARTED / INVOKING / DONE / FAILED / REVERTED / WAITING_TO_COMPENSATE / ...
└── retention_time
```

**저장 시점 조건** ([workflow-orchestrator-storage.ts:182-256](packages/modules/workflow-engine-inmemory/src/utils/workflow-orchestrator-storage.ts#L182-L256)):
- `flow.state ∈ { NOT_STARTED, DONE, FAILED, REVERTED, WAITING_TO_COMPENSATE }`
- 또는 현재 실행 중인 step이 `store: true` (= `async` / `retryInterval` / `timeout` 중 하나라도 있음 — [transaction-orchestrator.ts:1663-1668](packages/core/orchestration/src/transaction/transaction-orchestrator.ts#L1663-L1668))

**추정** — 동기 step만으로 구성된 워크플로우는 중간 단계가 DB에 기록되지 않는다. 즉, 실행 도중 프로세스가 죽으면 in-memory 엔진에서는 어디까지 진행됐는지 복원 불가.

### 8. 재기동 후 재개 — 두 엔진의 차이

| 항목 | inmemory 엔진 | redis 엔진 |
|---|---|---|
| 영속 저장소 | PostgreSQL | PostgreSQL + Redis |
| 타이머(retry/timeout) | 프로세스 내 `Map<NodeJS.Timeout>` | BullMQ 큐 (Redis) |
| 재기동 후 타이머 복원 | **없음** | **있음** |
| 스케줄 워크플로우 | 프로세스 내 `Map` + `setTimeout` | BullMQ repeatable job |
| 분산 락 | `this.isLocked: Map` (단일 프로세스) | Redlock |
| Pub/Sub | 프로세스 내 static Map | Redis Pub/Sub |

코드 근거:
- inmemory 타이머: [workflow-orchestrator-storage.ts:111-113](packages/modules/workflow-engine-inmemory/src/utils/workflow-orchestrator-storage.ts#L111-L113)
- redis 타이머: [workflow-orchestrator-storage.ts:649-663](packages/modules/workflow-engine-redis/src/utils/workflow-orchestrator-storage.ts#L649-L663)
- Redlock: [redis-distributed-transaction.ts:23](packages/modules/workflow-engine-redis/src/utils/redis-distributed-transaction.ts#L23)

**재개 코드 경로**:
1. `WorkflowOrchestratorService.run()` → `TransactionOrchestrator.beginTransaction()` → `loadTransactionById()` ([transaction-orchestrator.ts:1732-1766](packages/core/orchestration/src/transaction/transaction-orchestrator.ts#L1732-L1766))
2. `keyValueStore.get(key)` → DB(`workflowExecutionService_.list()`)에서 체크포인트 조회 ([workflow-orchestrator-storage.ts:266-325](packages/modules/workflow-engine-inmemory/src/utils/workflow-orchestrator-storage.ts#L266-L325))
3. 복원된 `flow`로 미완료 step부터 `executeNext()` 재실행

### 9. Async Step과 무한 대기 가능성

**사실** — `async: true` step이 `setStepSuccess/Failure`를 받지 못하면:
- `timeout` 옵션 있음 → `scheduleStepTimeout()` 만료 시 자동 TIMEOUT → 보상 진입 ([distribuited-transaction.ts:660-665](packages/core/orchestration/src/transaction/distribuited-transaction.ts#L660-L665))
- `timeout` 옵션 없음 → 무한 `WAITING` 상태 (코드 상 자동 실패 처리 없음)

`retryIntervalAwaiting` 옵션이 있으면 WAITING 중 주기적 재시도가 가능 ([transaction-orchestrator.ts:431-444](packages/core/orchestration/src/transaction/transaction-orchestrator.ts#L431-L444)).

### 10. 멱등성 (Idempotency)

**사실** — step 호출 시 idempotency key 형식: `{workflowId}:{transactionId}:{stepAction}:{invoke|compensate}` ([transaction-orchestrator.ts:1124-1131](packages/core/orchestration/src/transaction/transaction-orchestrator.ts#L1124-L1131)).

**사실** — 동일 `transactionId`로 재실행 시 `loadTransactionById`가 기존 체크포인트 조회 → 이미 `DONE`인 step은 `canInvoke()`에서 false → 재실행되지 않음.

**한계 (사실)**:
- 동기 step만 있는 워크플로우는 체크포인트가 DB에 없어 위 메커니즘이 동작하지 않음.
- 외부 시스템(PSP, SMTP) 호출 자체의 멱등성은 step 코드 작성자가 직접 보장해야 함 (프레임워크가 강제하지 않음).

## Code References

- `packages/core/orchestration/src/transaction/transaction-orchestrator.ts:88` — `executeCompensation()` 진입점
- `packages/core/orchestration/src/transaction/transaction-orchestrator.ts:191-203` — `getCompensationSteps()` depth 역순 정렬
- `packages/core/orchestration/src/transaction/transaction-orchestrator.ts:362-368` — flow 최종 상태 결정 (FAILED vs REVERTED vs DONE)
- `packages/core/orchestration/src/transaction/transaction-orchestrator.ts:805-862` — `setStepFailure()` maxRetries 판정
- `packages/core/orchestration/src/transaction/transaction-orchestrator.ts:1097-1100` — `noCompensation` 즉시 REVERTED 처리
- `packages/core/orchestration/src/transaction/distribuited-transaction.ts:539` — `saveCheckpoint()`
- `packages/core/orchestration/src/transaction/distribuited-transaction.ts:660-665` — `scheduleStepTimeout()` (async only)
- `packages/core/utils/src/modules-sdk/decorators/inject-transaction-manager.ts:24-69` — 모듈 단위 DB 트랜잭션
- `packages/core/utils/src/modules-sdk/decorators/emit-events.ts` — DB 커밋 후 이벤트 발행
- `packages/core/core-flows/src/payment/steps/capture-payment.ts` — 보상 미정의 (의도적)
- `packages/core/core-flows/src/order/steps/create-orders.ts:43-50` — 보상에서 `deleteOrders` 호출
- `packages/modules/workflow-engine-inmemory/src/models/workflow-execution.ts:4-58` — DB 스키마
- `packages/modules/workflow-engine-inmemory/src/utils/workflow-orchestrator-storage.ts:182-256` — 저장 시점 조건
- `packages/modules/workflow-engine-redis/src/utils/workflow-orchestrator-storage.ts:649-663` — BullMQ 기반 retry 잡
- `packages/modules/workflow-engine-redis/src/utils/redis-distributed-transaction.ts:3-27` — Redlock 분산 락

## Architecture Documentation

**현 코드에 구현된 일관성 메커니즘**:
1. Saga compensation (역순/병렬, depth 기반)
2. 워크플로우 체크포인트 영속화 (조건부)
3. Idempotency key (워크플로우 + step 단위)
4. Retry / timeout / async step 처리
5. Staged event emit (`eventGroupId`)
6. Redis 엔진 한정 분산 락(Redlock) + BullMQ 기반 영속 큐

**현 코드에 없는 메커니즘 (코드 검색 결과)**:
1. 2-Phase Commit / XA 트랜잭션
2. Outbox 패턴 (이벤트와 DB 커밋의 원자성 보장)
3. 보상 실패 시 자동 알림/에스컬레이션
4. 워크플로우 dead state(`FAILED`) 자동 복구

## Related Research

- [thoughts/shared/research/2026-01-05-claude-md-research.md](thoughts/shared/research/2026-01-05-claude-md-research.md)
- [thoughts/shared/research/2026-05-07-cart-line-item-tax-line-metadata.md](thoughts/shared/research/2026-05-07-cart-line-item-tax-line-metadata.md)

## Open Questions

1. **모름** — `paymentModule.capturePayment` 등 모듈 내부에 PSP 레벨 멱등성 처리가 있는지 (본 조사 범위 밖).
2. **모름** — `workflow_execution` 테이블의 `FAILED` dead state 레코드를 모니터링/알림하는 기본 인프라(예: subscriber)의 존재 여부.
3. **모름** — `retention_time` 만료 후 dead state 레코드의 정리 정책(자동 삭제 / 보존)이 운영자에게 어떻게 노출되는지.
