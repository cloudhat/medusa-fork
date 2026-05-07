# 11. 반품·부분환불

고객이 상품을 반품하거나 부분 환불을 요청하는 단계.

[← 여정 전체 목록](../README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `POST` | `/admin/returns` | `beginReturnOrderWorkflow` |
| `POST` | `/admin/returns/:id/request-items` | `requestItemReturnWorkflow` |
| `POST` | `/admin/returns/:id/request` | `confirmReturnRequestWorkflow` |
| `POST` | `/admin/returns/:id/receive/confirm` | `confirmReturnReceiveWorkflow` |
| `POST` | `/admin/payments/:id/refund` | `refundPaymentWorkflow` |
| `POST` | `/store/returns` | `createAndCompleteReturnOrderWorkflow` |

---

## 반품 흐름 유형

| 유형 | 설명 | 진입 워크플로우 |
|------|------|----------------|
| 관리자 주도 반품 | 관리자가 단계별로 반품 승인 | `beginReturnOrderWorkflow` → `confirmReturnRequestWorkflow` → `confirmReturnReceiveWorkflow` |
| 고객 직접 반품 (단순) | 생성+완료 한 번에 처리 | `createAndCompleteReturnOrderWorkflow` |
| 클레임 (손상/분실) | 환불 또는 교체 처리 | `beginClaimOrderWorkflow` → `confirmClaimRequestWorkflow` |

---

## 관리자 주도 반품 흐름 (단계별)

### Step 1: beginReturnOrderWorkflow

**파일**: [packages/core/core-flows/src/order/workflows/return/begin-return.ts](../../../../packages/core/core-flows/src/order/workflows/return/begin-return.ts)

| Step | 모듈 | 동작 |
|------|------|------|
| `useRemoteQueryStep` | Remote Query | 주문 조회 |
| `beginReturnOrderValidationStep` | — | 주문 취소 여부 확인 |
| `createReturnsStep` | `ORDER` | Return 레코드 생성 (`status: OPEN`) |
| `createOrderChangeStep` | `ORDER` | OrderChange 생성 (`change_type: "return_request"`) |

### Step 2: requestItemReturnWorkflow

아이템을 반품 대상으로 추가한다. 이 단계에서는 OrderChangeAction 레코드만 생성되고, 실제 ReturnItem은 아직 생성되지 않는다.

| Step | 모듈 | 동작 |
|------|------|------|
| `createOrderChangeActionsWorkflow` | `ORDER` | `ChangeActionType.RETURN_ITEM` action 생성 |
| `refreshReturnShippingWorkflow` | `ORDER` | 반품 배송비 재계산 |

### Step 3: confirmReturnRequestWorkflow

**파일**: [packages/core/core-flows/src/order/workflows/return/confirm-return-request.ts](../../../../packages/core/core-flows/src/order/workflows/return/confirm-return-request.ts)

반품 요청을 확정한다. 반품 Fulfillment가 생성될 수 있다.

| 순번 | Step | 모듈 | 동작 |
|------|------|------|------|
| 1 | `createReturnItemsFromActionsStep` | `ORDER` | ReturnItem 레코드 생성 |
| 2 | (조건) `createReturnFulfillmentWorkflow` | `FULFILLMENT` | 반품 Fulfillment 생성 |
| 3 | (조건) `createRemoteLinkStep` | Link | `ORDER.return_id ↔ FULFILLMENT.fulfillment_id` |
| 4 | `parallelize` | — | — |
| 4a | `updateReturnsStep` | `ORDER` | `Return.status = REQUESTED`, `requested_at = now` |
| 4b | `confirmOrderChanges` | `ORDER` | OrderChange 확정 |
| 4c | `emitEventStep` | — | `order.return_requested` |
| 5 | `createOrUpdateOrderPaymentCollectionWorkflow` | `PAYMENT` | 결제 컬렉션 갱신 |

### Step 4: confirmReturnReceiveWorkflow (재고 복원)

**파일**: [packages/core/core-flows/src/order/workflows/return/confirm-receive-return-request.ts](../../../../packages/core/core-flows/src/order/workflows/return/confirm-receive-return-request.ts)

상품 실물 입고를 확정한다. **이 단계에서 재고 복원이 발생한다.**

| 순번 | Step | 모듈 | 동작 |
|------|------|------|------|
| 1 | 조회 + 계산 | Query | 수령 수량 계산, `RECEIVED`/`PARTIALLY_RECEIVED` 상태 결정 |
| 2 | `parallelize` | — | — |
| 2a | `updateReturnsStep` | `ORDER` | Return 상태·`received_at` 업데이트 |
| 2b | `updateReturnItemsStep` | `ORDER` | `received_quantity`, `damaged_quantity` 업데이트 |
| 2c | `confirmOrderChanges` | `ORDER` | OrderChange 확정 |
| 2d | **`adjustInventoryLevelsStep`** | `INVENTORY`, `LOCKING` | **재고 복원** (+n) |
| 3 | 결제 컬렉션 갱신 + 이벤트 | — | — |

**파손 입고 처리**: `RECEIVE_DAMAGED_RETURN_ITEM` action 타입은 `damaged_quantity`만 업데이트되고 재고에 추가되지 않는다. 정상 입고(`RECEIVE_RETURN_ITEM`)만 `adjustInventoryLevelsStep`에 전달된다.

---

## 환불 흐름

### refundPaymentWorkflow (단일 결제 환불)

**파일**: [packages/core/core-flows/src/payment/workflows/refund-payment.ts](../../../../packages/core/core-flows/src/payment/workflows/refund-payment.ts)

| Step | 모듈 | 동작 |
|------|------|------|
| (조건) `validateRefundPaymentExceedsCapturedAmountStep` | — | `captured_total - refunded_total - 신규amount ≥ -epsilon` 검증 |
| `refundPaymentStep` | `PAYMENT` | Refund 레코드 생성 + 결제 프로바이더 환불 API 호출 |
| `addOrderTransactionStep` | `ORDER` | 음수 금액 OrderTransaction 기록 (`reference: "refund"`) |
| (조건) `createOrderRefundCreditLinesWorkflow` | `ORDER` | 환불액 > 미수금인 경우 CreditLine 생성 |
| `emitEventStep` | — | `payment.refunded` |

### refundPaymentsWorkflow (복수 결제 환불)

**파일**: [packages/core/core-flows/src/payment/workflows/refund-payments.ts](../../../../packages/core/core-flows/src/payment/workflows/refund-payments.ts)

여러 Payment를 동시에 환불. `amount`가 항상 필수다.

| Step | 모듈 | 동작 |
|------|------|------|
| `validatePaymentsRefundStep` | — | 각 payment의 환불 가능 금액 검증 |
| `refundPaymentsStep` | `PAYMENT` | 모든 payment를 `Promise.all`로 병렬 환불 (개별 실패는 로그만) |
| `addOrderTransactionStep` | `ORDER` | 배치 OrderTransaction 기록 |

---

## 부분환불 vs 전액환불

| 구분 | 처리 |
|------|------|
| 부분환불 | `input.amount` 지정. `validateRefundPaymentExceedsCapturedAmountStep`으로 한도 검증 후 해당 금액만 Refund 생성 |
| 전액환불 | `input.amount` 생략. `refundPayment_()` 내부에서 `payment.amount` 전체를 amount로 사용 |

두 경우 모두 결제 프로바이더에 실제 환불 요청을 보내는 흐름은 동일하다.

---

## 클레임 흐름 (손상·분실)

**파일**: [packages/core/core-flows/src/order/workflows/claim/](../../../../packages/core/core-flows/src/order/workflows/claim/)

| 클레임 타입 | 처리 |
|------------|------|
| `refund` | 환불금 산정 후 `refundPaymentWorkflow` 연동 |
| `replace` | 교체 상품 재고 예약(`reserveInventoryStep`) + 반품 Fulfillment 생성 |

---

## 관련 엔티티

| 엔티티 | 파일 | 주요 필드 |
|--------|------|----------|
| `Return` | [order/models/return.ts](../../../../packages/modules/order/src/models/return.ts) | `status`, `refund_amount`, `requested_at`, `received_at` |
| `ReturnItem` | [order/models/return-item.ts](../../../../packages/modules/order/src/models/return-item.ts) | `quantity`, `received_quantity`, `damaged_quantity` |
| `Refund` | [payment/models/refund.ts](../../../../packages/modules/payment/src/models/refund.ts) | `amount`, `note`, `refund_reason` |
| `OrderClaim` | [order/models/claim.ts](../../../../packages/modules/order/src/models/claim.ts) | `type` (refund/replace), `refund_amount` |
| `OrderTransaction` | [order/models/transaction.ts](../../../../packages/modules/order/src/models/transaction.ts) | `reference` (capture/refund), `amount` (환불 시 음수) |

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `ORDER` | Return, ReturnItem, OrderChange, OrderClaim 생성·관리; OrderTransaction 기록 |
| `PAYMENT` | Refund 엔티티 생성; 외부 결제 프로바이더 환불 API 호출 |
| `FULFILLMENT` | 반품 Fulfillment 생성 (반품 배송 라벨) |
| `INVENTORY` | 재고 복원 (`adjustInventoryLevelsStep`, +n) |
| `LOCKING` | Inventory item 단위 동시성 제어 |
