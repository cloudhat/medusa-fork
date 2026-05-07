# 13. 교환 (Exchange)

고객이 받은 상품을 반납하고 다른 상품을 새로 받는 단계. 반품(inbound)과 신규 배송(outbound)을 하나의 OrderChange로 묶어 처리한다.

[← 여정 전체 목록](../README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `POST` | `/admin/exchanges` | [beginExchangeOrderWorkflow](./flow-beginOrderExchangeWorkflow.md) |
| `POST` | `/admin/exchanges/:id/inbound/items` | [orderExchangeRequestItemReturnWorkflow](./flow-exchangeRequestItemReturnWorkflow.md) |
| `POST` | `/admin/exchanges/:id/outbound/items` | [orderExchangeAddNewItemWorkflow](./flow-exchangeAddNewItemWorkflow.md) |
| `POST` | `/admin/exchanges/:id/inbound/shipping-method` | [createExchangeShippingMethodWorkflow](./flow-createExchangeShippingMethodWorkflow.md) |
| `POST` | `/admin/exchanges/:id/outbound/shipping-method` | [createExchangeShippingMethodWorkflow](./flow-createExchangeShippingMethodWorkflow.md) |
| `POST` | `/admin/exchanges/:id/request` | [confirmExchangeRequestWorkflow](./flow-confirmExchangeRequestWorkflow.md) |
| `POST` | `/admin/exchanges/:id/cancel` | [cancelOrderExchangeWorkflow](./flow-cancelExchangeWorkflow.md) |

---

## 흐름 유형

| 유형 | 진입 워크플로우 체인 |
|------|---------------------|
| 표준 교환 (inbound + outbound) | `beginExchangeOrderWorkflow` → `orderExchangeRequestItemReturnWorkflow` → `orderExchangeAddNewItemWorkflow` → `createExchangeShippingMethodWorkflow` (×2) → `confirmExchangeRequestWorkflow` |
| 교환 취소 | `cancelOrderExchangeWorkflow` |

---

## 단계별 흐름

### Step 1: [beginExchangeOrderWorkflow](./flow-beginOrderExchangeWorkflow.md)

**파일**: [packages/core/core-flows/src/order/workflows/exchange/begin-order-exchange.ts](../../../../packages/core/core-flows/src/order/workflows/exchange/begin-order-exchange.ts)

| Step | 모듈 | 동작 |
|------|------|------|
| `useRemoteQueryStep` | Remote Query | 주문 조회 |
| `beginOrderExchangeValidationStep` | — | 주문 취소 여부 확인 |
| `createOrderExchangesStep` | ORDER | OrderExchange 레코드 생성 |
| `createOrderChangeStep` | ORDER | OrderChange 생성 (`change_type: "exchange"`) |

### Step 2: [orderExchangeRequestItemReturnWorkflow](./flow-exchangeRequestItemReturnWorkflow.md)

**파일**: [packages/core/core-flows/src/order/workflows/exchange/exchange-request-item-return.ts](../../../../packages/core/core-flows/src/order/workflows/exchange/exchange-request-item-return.ts)

반납할 inbound 아이템을 지정한다. Return 레코드가 없으면 자동 생성하고 `RETURN_ITEM` action을 기록한다. 이후 `computeAdjustmentsForPreviewWorkflow`로 프로모션 adjustment를 재계산한다.

| Step | 모듈 | 동작 |
|------|------|------|
| `useRemoteQueryStep` (×3) | Remote Query | orderExchange·order·orderChange 조회 |
| `when(return_id 없음)` → `createReturnsStep` | ORDER | Return 레코드 자동 생성 |
| `when(return_id 없음)` → `updateOrderChangesStep` | ORDER | OrderChange에 return_id 연결 |
| `exchangeRequestItemReturnValidationStep` | — | 취소·활성·재고위치 확인 |
| `createOrderChangeActionsWorkflow` | ORDER | `ChangeActionType.RETURN_ITEM` action 생성 |
| `computeAdjustmentsForPreviewWorkflow` | PROMOTION | 프로모션 adjustment 재계산 |
| `refreshExchangeShippingWorkflow` | ORDER | 배송비 재계산 |
| `previewOrderChangeStep` | ORDER | 변경 미리보기 반환 |

### Step 3: [orderExchangeAddNewItemWorkflow](./flow-exchangeAddNewItemWorkflow.md)

**파일**: [packages/core/core-flows/src/order/workflows/exchange/exchange-add-new-item.ts](../../../../packages/core/core-flows/src/order/workflows/exchange/exchange-add-new-item.ts)

고객에게 새로 발송할 outbound 아이템을 지정한다. `ITEM_ADD` action을 기록하고 프로모션 adjustment를 재계산한다.

| Step | 모듈 | 동작 |
|------|------|------|
| `useRemoteQueryStep` (×3) | Remote Query | orderExchange·order·orderChange 조회 |
| `exchangeAddNewItemValidationStep` | — | 취소·활성 상태 확인 |
| `addOrderLineItemsWorkflow` | ORDER | LineItem 생성 |
| `updateOrderTaxLinesWorkflow` | TAX | 세금 라인 갱신 |
| `createOrderChangeActionsWorkflow` | ORDER | `ChangeActionType.ITEM_ADD` action 생성 |
| `computeAdjustmentsForPreviewWorkflow` | PROMOTION | 프로모션 adjustment 재계산 |
| `refreshExchangeShippingWorkflow` | ORDER | 배송비 재계산 |
| `previewOrderChangeStep` | ORDER | 변경 미리보기 반환 |

### Step 4: [createExchangeShippingMethodWorkflow](./flow-createExchangeShippingMethodWorkflow.md) (선택)

**파일**: [packages/core/core-flows/src/order/workflows/exchange/create-exchange-shipping-method.ts](../../../../packages/core/core-flows/src/order/workflows/exchange/create-exchange-shipping-method.ts)

inbound(반납) 또는 outbound(신규 배송) 배송 방법을 추가한다. 동일 워크플로우를 inbound·outbound 각각 호출한다.

| Step | 모듈 | 동작 |
|------|------|------|
| `useRemoteQueryStep` (×3) | Remote Query | order·orderExchange·orderChange 조회 |
| `createExchangeShippingMethodValidationStep` | — | 취소·활성 상태 확인 |
| `fetchShippingOptionForOrderWorkflow` | FULFILLMENT | 배송 옵션 조회 및 가격 계산 |
| `createOrderShippingMethods` | ORDER | OrderShippingMethod 생성 |
| `updateOrderTaxLinesWorkflow` | TAX | 배송 세금 라인 갱신 |
| `createOrderChangeActionsWorkflow` | ORDER | `ChangeActionType.SHIPPING_ADD` action 생성 |
| `previewOrderChangeStep` | ORDER | 변경 미리보기 반환 |

### Step 5: [confirmExchangeRequestWorkflow](./flow-confirmExchangeRequestWorkflow.md)

**파일**: [packages/core/core-flows/src/order/workflows/exchange/confirm-exchange-request.ts](../../../../packages/core/core-flows/src/order/workflows/exchange/confirm-exchange-request.ts)

교환을 최종 확정한다. inbound 아이템은 ReturnItem으로, outbound 아이템은 OrderExchangeItem으로 확정된다.

| 순번 | Step | 모듈 | 동작 |
|------|------|------|------|
| 1 | `useRemoteQueryStep` (×3) | Remote Query | orderExchange·order·orderChange 조회 |
| 2 | `confirmExchangeRequestValidationStep` | — | 취소·활성 상태 확인 |
| 3 | `previewOrderChangeStep` | ORDER | 확정 전 미리보기 스냅샷 |
| 4 | `parallelize` | — | — |
| 4a | `createOrderExchangeItemsFromActionsStep` | ORDER | outbound → OrderExchangeItem 생성 |
| 4b | `createReturnItemsFromActionsStep` | ORDER | inbound → ReturnItem 생성 |
| 5 | `confirmIfExchangeItemsArePresent` | — | inbound·outbound 각각 1개 이상 확인 |
| 6 | `confirmOrderChanges` | ORDER | OrderChange 확정 |
| 7 | `(조건) updateReturnsStep` | ORDER | Return `status: REQUESTED` |
| 8 | `(조건) reserveInventoryStep` | INVENTORY | outbound 아이템 재고 예약 |
| 9 | `(조건) createReturnFulfillmentWorkflow` | FULFILLMENT | inbound 반납 Fulfillment 생성 |
| 10 | `(조건) createRemoteLinkStep` | Link | `ORDER.return_id ↔ FULFILLMENT.fulfillment_id` |
| 11 | `createOrUpdateOrderPaymentCollectionWorkflow` | PAYMENT | 결제 컬렉션 갱신 |
| 12 | `emitEventStep` | — | `order.exchange_created` 이벤트 발행 |

---

## 교환 취소 흐름

### [cancelOrderExchangeWorkflow](./flow-cancelExchangeWorkflow.md)

**파일**: [packages/core/core-flows/src/order/workflows/exchange/cancel-exchange.ts](../../../../packages/core/core-flows/src/order/workflows/exchange/cancel-exchange.ts)

확정된 교환을 취소한다. 연결된 Return도 함께 취소되며, outbound 아이템의 재고 예약이 해제된다.

| Step | 모듈 | 동작 |
|------|------|------|
| `useRemoteQueryStep` (×2) | Remote Query | orderExchange·orderReturn 조회 |
| `cancelExchangeValidateOrder` | — | 미취소 Fulfillment 존재 시 오류 |
| `parallelize` | — | — |
| `cancelOrderExchangeStep` | ORDER | OrderExchange `canceled_at` 설정 |
| `deleteReservationsByLineItemsStep` | INVENTORY | outbound 아이템 재고 예약 해제 |
| `(조건) cancelReturnWorkflow` | ORDER | 연결된 Return 취소 |

---

## 프로모션 재계산

교환 흐름에서 inbound 아이템 지정(`RETURN_ITEM` action)과 outbound 아이템 추가(`ITEM_ADD` action) 시마다 `computeAdjustmentsForPreviewWorkflow`가 호출된다. `carry_over_promotions` 플래그에 따라 기존 주문의 프로모션을 outbound 아이템에도 적용할지 결정한다.

| 시나리오 | 프로모션 재계산 |
|----------|----------------|
| inbound 아이템 지정 | 재계산 O |
| outbound 아이템 추가 | 재계산 O |
| 배송 방법 추가 | 재계산 X |
| 교환 확정(confirm) | 재계산 X (스냅샷 사용) |

---

## 관련 엔티티

| 엔티티 | 파일 | 주요 필드 |
|--------|------|----------|
| `OrderExchange` | [order/models/exchange.ts](../../../../packages/modules/order/src/models/exchange.ts) | `order_id`, `return_id`, `canceled_at` |
| `OrderExchangeItem` | [order/models/exchange-item.ts](../../../../packages/modules/order/src/models/exchange-item.ts) | `item_id`, `quantity` (outbound) |
| `Return` | [order/models/return.ts](../../../../packages/modules/order/src/models/return.ts) | `status`, `exchange_id` (inbound) |
| `ReturnItem` | [order/models/return-item.ts](../../../../packages/modules/order/src/models/return-item.ts) | `quantity`, `return_id` |

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `ORDER` | OrderExchange·OrderChange·ReturnItem·ExchangeItem 생성·관리 |
| `PROMOTION` | inbound·outbound 아이템 변경 시 adjustment 재계산 |
| `TAX` | 새 outbound 아이템·배송 방법 세금 라인 갱신 |
| `INVENTORY` | outbound 아이템 재고 예약; 취소 시 예약 해제 |
| `FULFILLMENT` | inbound 반납 Fulfillment 생성 |
| `PAYMENT` | 확정 시 결제 컬렉션 금액 갱신 |
