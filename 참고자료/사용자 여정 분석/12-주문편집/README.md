# 12. 주문 편집 (Order Edit)

관리자가 확정된 주문의 아이템·배송 방법을 수정하는 단계. 배송 전에 아이템을 추가·수량 변경·제거하거나 배송 방법을 교체할 수 있다.

[← 여정 전체 목록](../README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `POST` | `/admin/order-edits` | [beginOrderEditOrderWorkflow](./flow-beginOrderEditWorkflow.md) |
| `POST` | `/admin/order-edits/:id/items` | [orderEditAddNewItemWorkflow](./flow-orderEditAddNewItemWorkflow.md) |
| `POST` | `/admin/order-edits/:id/items/item/:item_id` | [orderEditUpdateItemQuantityWorkflow](./flow-orderEditUpdateItemQuantityWorkflow.md) |
| `DELETE` | `/admin/order-edits/:id/items/:action_id` | [removeItemOrderEditActionWorkflow](./flow-removeItemOrderEditActionWorkflow.md) |
| `POST` | `/admin/order-edits/:id/shipping-method` | [createOrderEditShippingMethodWorkflow](./flow-createOrderEditShippingMethodWorkflow.md) |
| `DELETE` | `/admin/order-edits/:id/shipping-method/:action_id` | [removeOrderEditShippingMethodWorkflow](./flow-removeOrderEditShippingMethodWorkflow.md) |
| `POST` | `/admin/order-edits/:id/request` | [requestOrderEditRequestWorkflow](./flow-requestOrderEditWorkflow.md) |
| `POST` | `/admin/order-edits/:id/confirm` | [confirmOrderEditRequestWorkflow](./flow-confirmOrderEditRequestWorkflow.md) |
| `DELETE` | `/admin/order-edits/:id` | [cancelBeginOrderEditWorkflow](./flow-cancelOrderEditWorkflow.md) |

---

## 흐름 유형

| 유형 | 진입 워크플로우 체인 |
|------|---------------------|
| 표준 흐름 | `beginOrderEditOrderWorkflow` → (아이템·배송 수정) → `requestOrderEditRequestWorkflow` → `confirmOrderEditRequestWorkflow` |
| 취소 | `cancelBeginOrderEditWorkflow` |

---

## 단계별 흐름

### Step 1: [beginOrderEditOrderWorkflow](./flow-beginOrderEditWorkflow.md)

**파일**: [packages/core/core-flows/src/order/workflows/order-edit/begin-order-edit.ts](../../../../packages/core/core-flows/src/order/workflows/order-edit/begin-order-edit.ts)

| Step | 모듈 | 동작 |
|------|------|------|
| `acquireLockStep` | LOCKING | 주문 ID 락 획득 |
| `useQueryGraphStep` | Remote Query | 주문 조회 |
| `beginOrderEditValidationStep` | — | 주문 취소 여부 확인 |
| `createOrderChangeStep` | ORDER | OrderChange 생성 (`change_type: "edit"`) |
| `releaseLockStep` | LOCKING | 락 해제 |

### Step 2: [orderEditAddNewItemWorkflow](./flow-orderEditAddNewItemWorkflow.md) (선택)

**파일**: [packages/core/core-flows/src/order/workflows/order-edit/order-edit-add-new-item.ts](../../../../packages/core/core-flows/src/order/workflows/order-edit/order-edit-add-new-item.ts)

편집 세션에 새 아이템을 추가한다. `ITEM_ADD` action이 생성되고 프로모션 adjustment가 재계산된다.

| Step | 모듈 | 동작 |
|------|------|------|
| `acquireLockStep` | LOCKING | 락 획득 |
| `useQueryGraphStep` (×2) | Remote Query | order·orderChange 조회 |
| `orderEditAddNewItemValidationStep` | — | 취소·활성 상태 확인 |
| `addOrderLineItemsWorkflow` | ORDER | LineItem 생성 |
| `updateOrderTaxLinesWorkflow` | TAX | 세금 라인 갱신 |
| `createOrderChangeActionsWorkflow` | ORDER | `ChangeActionType.ITEM_ADD` action 생성 |
| `computeAdjustmentsForPreviewWorkflow` | PROMOTION | 프로모션 adjustment 재계산 |
| `previewOrderChangeStep` | ORDER | 변경 미리보기 반환 |
| `releaseLockStep` | LOCKING | 락 해제 |

### Step 2-1: [orderEditUpdateItemQuantityWorkflow](./flow-orderEditUpdateItemQuantityWorkflow.md) (선택)

**파일**: [packages/core/core-flows/src/order/workflows/order-edit/order-edit-update-item-quantity.ts](../../../../packages/core/core-flows/src/order/workflows/order-edit/order-edit-update-item-quantity.ts)

원주문에 있던 아이템의 수량·가격을 수정한다. `quantity: 0`으로 설정하면 아이템을 제거할 수 있다.

| Step | 모듈 | 동작 |
|------|------|------|
| `acquireLockStep` | LOCKING | 락 획득 |
| `useQueryGraphStep` (×2) | Remote Query | order·orderChange 조회 |
| `orderEditUpdateItemQuantityValidationStep` | — | 취소·활성 상태 확인 |
| `createOrderChangeActionsWorkflow` | ORDER | `ChangeActionType.ITEM_UPDATE` action 생성 (quantity_diff 포함) |
| `computeAdjustmentsForPreviewWorkflow` | PROMOTION | 프로모션 adjustment 재계산 |
| `previewOrderChangeStep` | ORDER | 변경 미리보기 반환 |
| `releaseLockStep` | LOCKING | 락 해제 |

### Step 2-2: [removeItemOrderEditActionWorkflow](./flow-removeItemOrderEditActionWorkflow.md) (선택)

**파일**: [packages/core/core-flows/src/order/workflows/order-edit/remove-order-edit-item-action.ts](../../../../packages/core/core-flows/src/order/workflows/order-edit/remove-order-edit-item-action.ts)

편집 세션 중 **추가한** 아이템(`ITEM_ADD`)이나 **수정한** 아이템(`ITEM_UPDATE`) action을 되돌린다. 원주문의 아이템을 직접 삭제하지 않는다.

| Step | 모듈 | 동작 |
|------|------|------|
| `acquireLockStep` | LOCKING | 락 획득 |
| `useQueryGraphStep` (×2) | Remote Query | order·orderChange 조회 |
| `removeOrderEditItemActionValidationStep` | — | `ITEM_ADD`/`ITEM_UPDATE` action 여부 확인 |
| `deleteOrderChangeActionsStep` | ORDER | action 삭제 |
| `computeAdjustmentsForPreviewWorkflow` | PROMOTION | 프로모션 adjustment 재계산 |
| `previewOrderChangeStep` | ORDER | 변경 미리보기 반환 |
| `releaseLockStep` | LOCKING | 락 해제 |

### Step 3: [createOrderEditShippingMethodWorkflow](./flow-createOrderEditShippingMethodWorkflow.md) (선택)

**파일**: [packages/core/core-flows/src/order/workflows/order-edit/create-order-edit-shipping-method.ts](../../../../packages/core/core-flows/src/order/workflows/order-edit/create-order-edit-shipping-method.ts)

편집 세션에 배송 방법을 추가한다. `setPricingContext` hook으로 커스텀 가격 컨텍스트를 주입할 수 있다.

| Step | 모듈 | 동작 |
|------|------|------|
| `acquireLockStep` | LOCKING | 락 획득 |
| `useRemoteQueryStep` (×2) | Remote Query | order·shippingOption·orderChange 조회 |
| `createOrderEditShippingMethodValidationStep` | — | 취소·활성 상태 확인 |
| `createOrderShippingMethods` | ORDER | OrderShippingMethod 생성 |
| `updateOrderTaxLinesWorkflow` | TAX | 배송 세금 라인 갱신 |
| `createOrderChangeActionsWorkflow` | ORDER | `ChangeActionType.SHIPPING_ADD` action 생성 |
| `previewOrderChangeStep` | ORDER | 변경 미리보기 반환 |
| `releaseLockStep` | LOCKING | 락 해제 |

### Step 3-1: [removeOrderEditShippingMethodWorkflow](./flow-removeOrderEditShippingMethodWorkflow.md) (선택)

**파일**: [packages/core/core-flows/src/order/workflows/order-edit/remove-order-edit-shipping-method.ts](../../../../packages/core/core-flows/src/order/workflows/order-edit/remove-order-edit-shipping-method.ts)

편집 세션에서 배송 방법을 제거한다. `SHIPPING_ADD` action이 아닌 action은 제거할 수 없다.

| Step | 모듈 | 동작 |
|------|------|------|
| `acquireLockStep` | LOCKING | 락 획득 |
| `useQueryGraphStep` | Remote Query | orderChange 조회 |
| `removeOrderEditShippingMethodValidationStep` | — | `SHIPPING_ADD` action 여부 확인 |
| `parallelize` | — | — |
| `deleteOrderChangeActionsStep` | ORDER | action 삭제 |
| `deleteOrderShippingMethods` | ORDER | OrderShippingMethod 삭제 |
| `previewOrderChangeStep` | ORDER | 변경 미리보기 반환 |
| `releaseLockStep` | LOCKING | 락 해제 |

### Step 4: [requestOrderEditRequestWorkflow](./flow-requestOrderEditWorkflow.md)

**파일**: [packages/core/core-flows/src/order/workflows/order-edit/request-order-edit.ts](../../../../packages/core/core-flows/src/order/workflows/order-edit/request-order-edit.ts)

편집 내용을 확정 대기 상태로 전환한다. OrderChange 상태를 `PENDING → REQUESTED`로 변경한다.

| Step | 모듈 | 동작 |
|------|------|------|
| `acquireLockStep` | LOCKING | 락 획득 |
| `useQueryGraphStep` (×2) | Remote Query | order·orderChange 조회 |
| `requestOrderEditRequestValidationStep` | — | 취소·활성 상태 확인 |
| `updateOrderChangesStep` | ORDER | OrderChange `status: REQUESTED`, `requested_at` 설정 |
| `emitEventStep` | — | `order-edit.requested` 이벤트 발행 |
| `previewOrderChangeStep` | ORDER | 변경 미리보기 반환 |
| `releaseLockStep` | LOCKING | 락 해제 |

### Step 5: [confirmOrderEditRequestWorkflow](./flow-confirmOrderEditRequestWorkflow.md)

**파일**: [packages/core/core-flows/src/order/workflows/order-edit/confirm-order-edit-request.ts](../../../../packages/core/core-flows/src/order/workflows/order-edit/confirm-order-edit-request.ts)

편집을 최종 확정한다. OrderChange가 적용되고 재고 예약이 갱신되며 결제 컬렉션이 업데이트된다.

| 순번 | Step | 모듈 | 동작 |
|------|------|------|------|
| 1 | `useQueryGraphStep` (×2) | Remote Query | order·orderChange 조회 |
| 2 | `confirmOrderEditRequestValidationStep` | — | 취소·활성 상태 확인 |
| 3 | `previewOrderChangeStep` | ORDER | 편집 미리보기 스냅샷 |
| 4 | `confirmOrderChanges` | ORDER | OrderChange 확정 (adjustment 새 버전 복사) |
| 5 | `useQueryGraphStep` | Remote Query | 확정 후 최신 order 재조회 |
| 6 | `deleteReservationsByLineItemsStep` | INVENTORY | 기존 재고 예약 삭제 |
| 7 | `reserveInventoryStep` | INVENTORY | 신규 재고 예약 |
| 8 | `createOrUpdateOrderPaymentCollectionWorkflow` | PAYMENT | 결제 컬렉션 갱신 |
| 9 | `emitEventStep` | — | `order-edit.confirmed` 이벤트 발행 |
| 10 | `releaseLockStep` | LOCKING | 락 해제 |

---

## 편집 취소 흐름

### [cancelBeginOrderEditWorkflow](./flow-cancelOrderEditWorkflow.md)

**파일**: [packages/core/core-flows/src/order/workflows/order-edit/cancel-begin-order-edit.ts](../../../../packages/core/core-flows/src/order/workflows/order-edit/cancel-begin-order-edit.ts)

편집 세션 전체를 취소한다. `SHIPPING_ADD` action에 연결된 OrderShippingMethod도 함께 삭제된다.

| Step | 모듈 | 동작 |
|------|------|------|
| `acquireLockStep` | LOCKING | 락 획득 |
| `useQueryGraphStep` (×2) | Remote Query | order·orderChange 조회 |
| `cancelBeginOrderEditValidationStep` | — | 취소·활성 상태 확인 |
| `parallelize` | — | — |
| `deleteOrderChangesStep` | ORDER | OrderChange 삭제 |
| `deleteOrderShippingMethods` | ORDER | 편집 세션의 ShippingMethod 삭제 |
| `emitEventStep` | — | `order-edit.canceled` 이벤트 발행 |
| `releaseLockStep` | LOCKING | 락 해제 |

---

## 프로모션 재계산

주문 편집 흐름에서 아이템을 추가(`ITEM_ADD`)하거나, 수량을 변경(`ITEM_UPDATE`)하거나, 추가한 아이템 action을 제거할 때마다 `computeAdjustmentsForPreviewWorkflow`가 호출되어 프로모션 adjustment를 재계산한다. 이 점이 반품 흐름과의 핵심 차이다.

| 시나리오 | 프로모션 재계산 |
|----------|----------------|
| 아이템 추가 | 재계산 O |
| 수량 변경 | 재계산 O |
| action 제거 | 재계산 O |
| 배송 방법 추가/제거 | 재계산 X |
| 편집 확정(confirm) | 재계산 X (스냅샷 사용) |

### OrderLineItemAdjustment DB 조작 방식

재계산 결과는 `order_line_item_adjustment` 테이블에 즉시 저장되지 않는다. 각 단계에서 실제 DB 조작은 다음과 같다.

| 단계 | 연산 | 테이블 |
|------|------|--------|
| 프로모션 재계산 중 | `create` (`ITEM_ADJUSTMENTS_REPLACE` 타입 액션 저장) | `order_change_action` |
| carry_over_promotions=false 시 | `softDelete` (기존 `ITEM_ADJUSTMENTS_REPLACE` 액션 삭제) | `order_change_action` |
| 편집 확정(confirm) 시 | `create` (새 `version` 번호 레코드 생성) | `order_line_item_adjustment` |
| revert 시 | `softDelete` (현재 version 레코드 삭제) | `order_line_item_adjustment` |

confirm 시의 CREATE는 기존 레코드를 수정하지 않고 새 `version` 값을 가진 레코드를 추가하는 버전 누적 방식이다. 코드 주석(order-module-service.ts:3689)에 "there is no removal or upsert"라고 명시되어 있다.

`updated_at` 컬럼은 존재하지만, Medusa 내부 플로우에서는 adjustment 레코드를 UPDATE하지 않는다. `upsertOrderLineItemAdjustments` · `setOrderLineItemAdjustments` 두 메서드가 UPDATE 경로를 제공하지만, 현재 코드베이스 내 어떤 워크플로우·API 라우트에서도 호출하지 않는다. 외부 커스터마이징에서 `id` 필드를 포함한 데이터를 전달할 때만 UPDATE가 발생한다.

---

## 관련 엔티티

| 엔티티                       | 파일                                                                                                            | 주요 필드                                                         |
| ------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `OrderChange`             | [order/models/order-change.ts](../../../../packages/modules/order/src/models/order-change.ts)                 | `change_type: "edit"`, `status` (PENDING→REQUESTED→CONFIRMED) |
| `OrderChangeAction`       | [order/models/order-change-action.ts](../../../../packages/modules/order/src/models/order-change-action.ts)   | `action` (ITEM_ADD, ITEM_UPDATE, SHIPPING_ADD)                |
| `OrderLineItem`           | [order/models/line-item.ts](../../../../packages/modules/order/src/models/line-item.ts)                       | `quantity`, `unit_price`, `version`                           |
| `OrderLineItemAdjustment` | [order/models/line-item-adjustment.ts](../../../../packages/modules/order/src/models/line-item-adjustment.ts) | `amount`, `promotion_id`, `version`                           |

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `ORDER` | OrderChange·OrderChangeAction 생성·관리; LineItem 생성; adjustment 버전 관리 |
| `PROMOTION` | 아이템 변경 시 adjustment 재계산 (`computeAdjustmentsForPreviewWorkflow`) |
| `TAX` | 새 아이템·배송 방법 세금 라인 갱신 |
| `INVENTORY` | 확정 시 재고 예약 삭제 후 재생성 |
| `PAYMENT` | 확정 시 결제 컬렉션 금액 갱신 |
| `LOCKING` | 주문 ID 단위 동시 요청 직렬화 |
