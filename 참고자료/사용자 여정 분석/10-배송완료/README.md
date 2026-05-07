# 10. 배송 완료

물류사가 배송을 완료하면 관리자가 배송 완료를 확인하는 단계.

[← 여정 전체 목록](../README.md) | [다음: 11 반품·부분환불](../11-반품-부분환불/README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `POST` | `/admin/orders/:id/fulfillments/:fulfillment_id/mark-as-delivered` | `markOrderFulfillmentAsDeliveredWorkflow` |

---

## markOrderFulfillmentAsDeliveredWorkflow

**파일**: [packages/core/core-flows/src/order/workflows/mark-order-fulfillment-as-delivered.ts](../../../../packages/core/core-flows/src/order/workflows/mark-order-fulfillment-as-delivered.ts)

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `useQueryGraphStep` (fulfillment) | Query | fulfillment id 조회 |
| 2 | `useQueryGraphStep` (order) | Query | 주문 + fulfillments + 아이템 조회 |
| 3 | `orderFulfillmentDeliverablilityValidationStep` | — | 취소 여부, fulfillment 소속 여부 검증 |
| 4 | `acquireLockStep` (orderId) | `LOCKING` | 주문 단위 락 |
| 5 | `markFulfillmentAsDeliveredWorkflow.runAsStep` | `FULFILLMENT`, `LOCKING` | `Fulfillment.delivered_at = now` 설정 |
| 6 | `releaseLockStep` (orderId) | `LOCKING` | 주문 락 해제 |
| 7 | `registerOrderDeliveryStep` | `ORDER` | 주문 이력에 delivery 등록 |
| 8 | `emitEventStep` | `EVENT_BUS` | `order.delivery_created` 이벤트 |

### markFulfillmentAsDeliveredWorkflow 내부

**파일**: [packages/core/core-flows/src/fulfillment/workflows/mark-fulfillment-as-delivered.ts](../../../../packages/core/core-flows/src/fulfillment/workflows/mark-fulfillment-as-delivered.ts)

1. `acquireLockStep` (fulfillmentId) — 풀필먼트 단위 락 추가
2. `useRemoteQueryStep` — `delivered_at`, `canceled_at` 조회
3. `validateFulfillmentDeliverabilityStep` — `canceled_at`이 있으면 에러, `delivered_at`이 이미 있으면 에러
4. `updateFulfillmentWorkflow.runAsStep` — `Modules.FULFILLMENT` → `Fulfillment.delivered_at = now`
5. `releaseLockStep` (fulfillmentId)

---

## 인벤토리 변경 없음

이 단계에서 재고 수량 변경은 발생하지 않는다. 재고 차감은 [09. 풀필먼트 생성](../09-풀필먼트-배송처리/README.md) 단계에서 완료됐다.

---

## Fulfillment 상태 전이

```
생성 (packed_at 설정)
  └──→ 배송 시작 (shipped_at 설정)
        └──→ 배송 완료 (delivered_at 설정)
                ← 이 단계에서 도달

취소 (canceled_at 설정) ← shipped_at 없을 때만 가능
```

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `FULFILLMENT` | `Fulfillment.delivered_at` 설정 |
| `ORDER` | 주문 이력에 delivery 등록 (`registerDelivery`) |
| `LOCKING` | Order 락 + Fulfillment 락 (이중 락) |
