---
date: 2026-05-07T18:24:57+0900
researcher: SAN KIM
git_commit: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
branch: develop
repository: medusa-fork
topic: "OrderLineItem, OrderItem, ReturnItem 의 라이프사이클 기준 관계"
tags: [research, codebase, order, order-item, order-line-item, return, return-item, lifecycle]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
---

# Research: OrderLineItem, OrderItem, ReturnItem 의 라이프사이클 기준 관계

**Date**: 2026-05-07T18:24:57+0900
**Researcher**: SAN KIM
**Git Commit**: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
**Branch**: develop
**Repository**: medusa-fork

## Research Question

`OrderLineItem`, `OrderItem`, `ReturnItem` 세 엔티티가 주문→반품 라이프사이클의 각 단계에서 어떻게 생성·갱신·소멸하는지, 그리고 서로를 어떻게 참조하는지 코드 기준으로 정리한다.

## Summary

세 엔티티는 라이프사이클 동작 방식이 서로 다르다.

| 엔티티 | 변경 방식 | 버전 필드 | 라이프사이클 동안 행 개수 |
|---|---|---|---|
| `OrderLineItem` | **불변(immutable)** — 한 번 만들어지면 갱신/추가 없음 | 없음 | 주문 라인당 1개 |
| `OrderItem` | **append-only 버전 스냅샷** — 변경 시 새 row INSERT | `version` | 라인당 N+1개 (변경 N회) |
| `ReturnItem` | **in-place mutable** — 동일 row 를 UPDATE | 없음 | 반품 요청 라인당 1개 |

라이프사이클 흐름:

1. **주문 생성** — 라인당 `OrderLineItem` 1행 + `OrderItem` 1행(`version=1`) 동시 INSERT.
2. **반품 요청** — `Return` 1행 + `ReturnItem` N행 INSERT, `OrderChange`(`version=order.version+1`) 생성·즉시 confirm. `applyChangesToOrder` 가 `RETURN_ITEM` 액션을 처리해 `return_requested_quantity` 가 증가한 **새 `OrderItem` 스냅샷 행**을 INSERT, `Order.version`++.
3. **반품 수령** — 또 한 번의 `OrderChange` confirm 으로 새 `OrderItem` 스냅샷이 만들어지며 `return_received_quantity` 증가 + `return_requested_quantity` 감소. 동일 트랜잭션에서 **기존 `ReturnItem` row 가 UPDATE** 되어 `received_quantity`/`damaged_quantity` 누적. `Return.status` = `RECEIVED` | `PARTIALLY_RECEIVED`.
4. **취소** — `CANCEL_RETURN_ITEM` 액션으로 또 새 `OrderItem` 스냅샷, `Return.status = CANCELED`. `ReturnItem` 행은 삭제되지 않고 그대로 남는다.

참조 관계의 **핵심**: `ReturnItem.item_id` 는 **`OrderLineItem.id`** 를 가리킨다. 버전드 `OrderItem` 을 직접 참조하지 않는다. `OrderItem.item_id` 도 `OrderLineItem.id` 를 가리키므로, 세 엔티티는 `OrderLineItem` 을 허브로 하는 별 모양 관계다.

```
                ┌─────────────────┐
                │  OrderLineItem  │  (불변 카탈로그 스냅샷)
                │   id = ordli_*  │
                └────────┬────────┘
                         │ item_id
        ┌────────────────┼────────────────┐
        │                                 │
┌───────▼───────┐                  ┌──────▼──────┐
│   OrderItem   │ × N (version별)   │ ReturnItem  │ × 반품요청라인수
│  id = orditem │                  │ id = retitem│
│   version=1   │                  │  (version X)│
│   version=2   │                  └──────┬──────┘
│   ...         │                         │ return_id
└───────────────┘                  ┌──────▼──────┐
                                   │   Return    │
                                   │ status, ... │
                                   └─────────────┘
```

## Detailed Findings

### 1. 엔티티 구조

#### 1.1 `OrderLineItem` — 불변 상품 스냅샷

[packages/modules/order/src/models/line-item.ts](packages/modules/order/src/models/line-item.ts)

- `version` 필드 **없음**.
- `title`, `variant_id`, `product_id`, `unit_price`, `tax_lines`, `adjustments`, `is_giftcard` 등 **카탈로그 스냅샷**.
- 한 번 INSERT 된 후에는 라이프사이클 동안 갱신되지 않는다.
- 상품 식별/표시용 데이터의 단일 원천. `OrderItem`, `ReturnItem` 모두 이 행을 참조한다.

#### 1.2 `OrderItem` — 버전별 카운터 스냅샷

[packages/modules/order/src/models/order-item.ts:8-54](packages/modules/order/src/models/order-item.ts#L8-L54)

| 필드 | 의미 |
|---|---|
| `id` (`orditem_*`) | PK |
| `order_id` | FK → `Order` |
| `item_id` | FK → `OrderLineItem` |
| `version` (default 1) | 이 행이 속한 주문 version |
| `quantity` | 주문 수량 |
| `fulfilled_quantity` | 출고 수량 |
| `return_requested_quantity` | 반품 요청 수량 |
| `return_received_quantity` | 정상 입고 수량 |
| `return_dismissed_quantity` | 파손 입고 수량 |
| `delivered_quantity`, `shipped_quantity`, `written_off_quantity` | 기타 상태 카운터 |

인덱스: `(order_id, version)` 비유일 partial index. `(order_id, version, item_id)` unique 제약 **없음**.

#### 1.3 `ReturnItem` — 반품 요청 라인

[packages/modules/order/src/models/return-item.ts](packages/modules/order/src/models/return-item.ts)

| 필드 | 타입 | 기본값 | 비고 |
|---|---|---|---|
| `id` (`retitem_*`) | PK | auto | |
| `quantity` | BigNumber | — | 반품 요청 수량 |
| `received_quantity` | BigNumber | `0` | 누적 정상 입고 수량 |
| `damaged_quantity` | BigNumber | `0` | 누적 파손 입고 수량 |
| `note`, `metadata` | text/json | nullable | |
| `reason_id` | FK → `ReturnReason` | nullable | |
| `return_id` | FK → `Return` | required | `belongsTo Return` (mappedBy `items`) |
| `item_id` | FK → `OrderLineItem` | required | **`OrderLineItem.id` 를 참조 — `OrderItem` 이 아님** |

`version` 필드 **없음**. 라이프사이클 내내 동일 row 가 UPDATE 된다.

#### 1.4 `Return` — 반품 루트

[packages/modules/order/src/models/return.ts](packages/modules/order/src/models/return.ts)

- `status: ReturnStatus` (`OPEN`/`REQUESTED`/`RECEIVED`/`PARTIALLY_RECEIVED`/`CANCELED`).
- `order_version`: 반품 생성 시점의 `Order.version` 스냅샷.
- `requested_at`, `received_at`, `canceled_at`: 단계별 타임스탬프.
- `items: hasMany ReturnItem` — `cascade: { delete: ["items", ...] }` 로 부모 삭제 시 자식 ReturnItem 도 hard-delete.

### 2. 단계 1 — 주문 생성

**워크플로 진입**: [packages/core/core-flows/src/order/steps/create-orders.ts](packages/core/core-flows/src/order/steps/create-orders.ts) → `OrderModuleService.createOrders`.

**서비스 흐름** ([order-module-service.ts:748-843](packages/modules/order/src/services/order-module-service.ts#L748-L843)):

1. `Order` 생성 (`version = 1` default — [order.ts:17](packages/modules/order/src/models/order.ts#L17)).
2. `createOrderLineItemsBulk_` ([order-module-service.ts:1138-1169](packages/modules/order/src/services/order-module-service.ts#L1138-L1169)) 가 라인당 두 행을 동시에 만든다:
   - `OrderLineItem` row (카탈로그 스냅샷)
   - `OrderItem` row: `{ order_id, version: 1, item_id: <OrderLineItem.id>, quantity, fulfilled_quantity: 0, return_requested_quantity: 0, ... }`

이 시점 결과:

```
OrderLineItem(ordli_A, title, variant_id, unit_price)
OrderItem(orditem_X, order_id, item_id=ordli_A, version=1, quantity=Q, ...counters=0)
ReturnItem  → 없음
```

### 3. 단계 2 — 반품 요청

두 경로가 존재하며 결과 상태는 동일하다.

#### 3.1 경로 A — `createReturn` 직접 액션 (스토어프론트)

[packages/modules/order/src/services/actions/create-return.ts:132-165](packages/modules/order/src/services/actions/create-return.ts#L132-L165)

1. `Return` row INSERT — `status = REQUESTED`, `order_version = order.version` ([create-return.ts:18-27](packages/modules/order/src/services/actions/create-return.ts#L18-L27)).
2. `ReturnItem` row 들 INSERT — 각 라인마다 `em.create(ReturnItem, { return_id, item_id: <OrderLineItem.id>, quantity, ... })` ([create-return.ts:29-53](packages/modules/order/src/services/actions/create-return.ts#L29-L53)). 동시에 `ChangeActionType.RETURN_ITEM` 액션을 메모리상 `actions[]` 에 push.
3. `OrderChange` 생성 — `version = order.version + 1` ([order-module-service.ts:2522-2536](packages/modules/order/src/services/order-module-service.ts#L2522-L2536)).
4. **즉시 `confirmOrderChange`** ([create-return.ts:161](packages/modules/order/src/services/actions/create-return.ts#L161)).

#### 3.2 경로 B — 어드민 2-phase 워크플로

- [`beginReturnOrderWorkflow`](packages/core/core-flows/src/order/workflows/return/begin-return.ts) — `Return` 셸 + `OrderChange(type=return_request)` 만 생성. ReturnItem 아직 없음.
- [`requestItemReturnWorkflow`](packages/core/core-flows/src/order/workflows/return/request-item-return.ts) — `RETURN_ITEM` `OrderChangeAction` row 들을 추가. 여전히 ReturnItem 없음.
- [`confirmReturnRequestWorkflow`](packages/core/core-flows/src/order/workflows/return/confirm-return-request.ts):
  - [`createReturnItemsFromActionsStep`](packages/core/core-flows/src/order/steps/return/create-return-items-from-actions.ts) — 액션의 `details.reference_id`(=OrderLineItem.id), `quantity` 를 매핑해 `orderModuleService.createReturnItems()` 호출. ⇒ ReturnItem row 들이 비로소 INSERT.
  - `updateReturnsStep` — `Return.status = REQUESTED`, `requested_at = now()`.
  - `confirmOrderChanges` — confirm 트리거.

#### 3.3 confirm 처리 — `OrderItem` 새 스냅샷 INSERT

[apply-order-changes.ts:85](packages/modules/order/src/utils/apply-order-changes.ts#L85):

```ts
id: orderItem.version === version ? orderItem.id : undefined
```

기존 `OrderItem.version=1` ≠ 새 `version=2` 이므로 `id=undefined` → upsert 가 INSERT 로 처리. `RETURN_ITEM` 핸들러 ([return-item.ts:11-24](packages/modules/order/src/utils/actions/return-item.ts#L11-L24)) 가 메모리상 deep clone 위에서 `return_requested_quantity += action.details.quantity` 갱신한 값이 새 row 에 박힌다. `Order.version` 도 2 로 UPDATE.

#### 3.4 단계 2 종료 시점 상태

```
OrderLineItem(ordli_A)                            ← 변경 없음
OrderItem(orditem_X, version=1, return_requested_quantity=0)   ← 그대로 남음
OrderItem(orditem_Y, version=2, return_requested_quantity=Q')  ← 새 INSERT
Return(return_R, status=REQUESTED, order_version=1)
ReturnItem(retitem_R1, return_id=return_R, item_id=ordli_A,
           quantity=Q', received_quantity=0, damaged_quantity=0)
```

### 4. 단계 3 — 반품 수령

두 경로 모두 (1) 새 `OrderChange` confirm 으로 `OrderItem` 새 스냅샷을 만들고, (2) 기존 `ReturnItem` row 를 in-place UPDATE 한다.

#### 4.1 경로 A — `receiveReturn` 직접 액션

[packages/modules/order/src/services/actions/receive-return.ts:79-117](packages/modules/order/src/services/actions/receive-return.ts#L79-L117)

1. `RECEIVE_RETURN_ITEM` 액션 생성 → `OrderChange(version=order.version+1, type=RETURN_RECEIVE)` → 즉시 confirm.
2. `RECEIVE_RETURN_ITEM` 핸들러 ([receive-return-item.ts:11-32](packages/modules/order/src/utils/actions/receive-return-item.ts#L11-L32)):
   - `return_received_quantity += quantity`
   - `return_requested_quantity -= quantity`
   - 결과 → 새 `OrderItem` row(version=3) INSERT.
3. `updateReturnItems` ([receive-return.ts:47-65](packages/modules/order/src/services/actions/receive-return.ts#L47-L65)) — `ReturnItem.received_quantity += quantity` 누적 후 `this.updateReturnItems(...)` 로 **동일 row UPDATE**.
4. `Return.status` 전이 ([receive-return.ts:67-77](packages/modules/order/src/services/actions/receive-return.ts#L67-L77)):
   - 모든 ReturnItem 의 `received_quantity == quantity` → `RECEIVED`, `received_at = now()`.
   - 일부만 → `PARTIALLY_RECEIVED`.

#### 4.2 경로 B — 어드민 워크플로

- [`beginReceiveReturnWorkflow`](packages/core/core-flows/src/order/workflows/return/begin-receive-return.ts) — `OrderChange(type=return_receive)` 셸 생성.
- `receiveItemReturnRequestWorkflow` — `RECEIVE_RETURN_ITEM` 액션 추가.
- `dismissItemReturnRequestWorkflow` — `RECEIVE_DAMAGED_RETURN_ITEM` 액션 추가 (파손 입고).
- [`confirmReturnReceiveWorkflow`](packages/core/core-flows/src/order/workflows/return/confirm-receive-return-request.ts):
  - [confirm-receive-return-request.ts:257-349](packages/core/core-flows/src/order/workflows/return/confirm-receive-return-request.ts#L257-L349) — 두 액션 타입을 함께 집계해 `reference_id` 키별로 `received_quantity`/`damaged_quantity` 합산.
    - `received_quantity` ← 두 타입 모두에서 누적.
    - `damaged_quantity` ← `RECEIVE_DAMAGED_RETURN_ITEM` 만 누적.
  - [`updateReturnItemsStep`](packages/core/core-flows/src/order/steps/return/update-return-items.ts) — 위 합산값으로 ReturnItem UPDATE (보상 트랜잭션 시 직전 값 복원).
  - `updateReturnsStep` — 상태 전이.
  - `confirmOrderChanges` — `OrderItem` 새 스냅샷 INSERT 트리거.
  - `adjustInventoryLevelsStep` — 재고 복원.

#### 4.3 단계 3 종료 시점 상태 (전량 정상 수령 가정)

```
OrderLineItem(ordli_A)                                       ← 변경 없음
OrderItem(version=1, ...)                                    ← 잔존
OrderItem(version=2, return_requested_quantity=Q')           ← 잔존
OrderItem(version=3, return_requested_quantity=0,
                     return_received_quantity=Q')            ← 새 INSERT
Return(return_R, status=RECEIVED, received_at=now())          ← 동일 row UPDATE
ReturnItem(retitem_R1, quantity=Q', received_quantity=Q',
           damaged_quantity=0)                                ← 동일 row UPDATE
```

### 5. 단계 4 — 취소

[packages/modules/order/src/services/actions/cancel-return.ts:36-110](packages/modules/order/src/services/actions/cancel-return.ts#L36-L110)

- `ReturnItem.received_quantity > 0` 이 하나라도 있으면 검증 단계에서 차단 ([core-flows cancel-return.ts:75-87](packages/core/core-flows/src/order/workflows/return/cancel-return.ts#L75-L87)).
- 각 ReturnItem 마다 `CANCEL_RETURN_ITEM` 액션 생성 → `OrderChange` 생성·즉시 confirm.
- `Return.canceled_at`, `Return.status = CANCELED` UPDATE.
- **ReturnItem row 는 삭제되지 않고 그대로 남는다** (cascade 는 부모 `Return` 자체가 삭제될 때만 동작).

### 6. ReturnItem 의 참조 관계 — `OrderItem` 이 아닌 `OrderLineItem`

이 부분은 라이프사이클 해석에서 자주 혼동되는 지점이다.

- [return-item.ts:27-29](packages/modules/order/src/models/return-item.ts#L27-L29) — `item: model.belongsTo(() => OrderLineItem, { mappedBy: "return_items" })`.
- [create-return.ts:44-51](packages/modules/order/src/services/actions/create-return.ts#L44-L51) — `em.create(ReturnItem, { ..., item_id: item.id, ... })`. 여기서 `item.id` 는 **OrderLineItem id**.
- `RETURN_ITEM`/`RECEIVE_RETURN_ITEM` 액션의 `details.reference_id` 도 OrderLineItem id 를 담는다 ([create-return-items-from-actions.ts:24-33](packages/core/core-flows/src/order/steps/return/create-return-items-from-actions.ts#L24-L33)).

`ReturnItem` 에서 버전별 `OrderItem` 으로 가려면 `ReturnItem.item_id (=OrderLineItem.id)` ↔ `OrderItem.item_id` 양쪽에 같은 키가 박혀 있다는 사실을 이용해 조인해야 한다. 직접 FK 는 없다.

### 7. 변경 방식 비교 요약

| 동작 | OrderLineItem | OrderItem | ReturnItem |
|---|---|---|---|
| 주문 생성 | INSERT | INSERT (version=1) | — |
| 반품 요청 | — | **새 INSERT (version+1)** | INSERT |
| 반품 수령 | — | **새 INSERT (version+1)** | **동일 row UPDATE** |
| 파손 입고 | — | **새 INSERT (version+1)** | **동일 row UPDATE** (`damaged_quantity`) |
| 반품 취소 | — | **새 INSERT (version+1)** (CANCEL_RETURN_ITEM) | (잔존, 변경 없음) |
| `revertLastChange` | — | 최신 버전 행 hard-delete | 함께 cascade (`Return` 삭제 시) |

`OrderItem` 의 INSERT 분기는 [apply-order-changes.ts:85](packages/modules/order/src/utils/apply-order-changes.ts#L85) 의 `id: orderItem.version === version ? orderItem.id : undefined` 로 결정된다.

### 8. 라이프사이클 다이어그램 (요청→정상 수령)

```
T0  ─┬─ OrderLineItem(ordli_A)            (이후 변경 없음)
     └─ OrderItem(version=1, qty=Q)

T1 (반품 요청 confirm)
     ├─ OrderChange(version=2)            confirm → applyChangesToOrder
     ├─ OrderItem(version=2,
     │            return_requested_quantity=Q')   ← INSERT
     ├─ Order.version: 1 → 2
     ├─ Return(return_R, status=REQUESTED, order_version=1)   ← INSERT
     └─ ReturnItem(retitem_R1, quantity=Q',
                    received_quantity=0)          ← INSERT

T2 (반품 수령 confirm)
     ├─ OrderChange(version=3)            confirm → applyChangesToOrder
     ├─ OrderItem(version=3,
     │            return_requested_quantity=0,
     │            return_received_quantity=Q')    ← INSERT
     ├─ Order.version: 2 → 3
     ├─ Return.status: REQUESTED → RECEIVED       ← UPDATE
     ├─ Return.received_at = now()                ← UPDATE
     └─ ReturnItem(retitem_R1).received_quantity = Q'  ← UPDATE (동일 row)
```

## Code References

- `packages/modules/order/src/models/line-item.ts` — OrderLineItem (version 없음, 카탈로그 스냅샷)
- `packages/modules/order/src/models/order-item.ts:8-54` — OrderItem (version, 모든 quantity 카운터)
- `packages/modules/order/src/models/return-item.ts` — ReturnItem (version 없음, item_id → OrderLineItem)
- `packages/modules/order/src/models/return.ts` — Return (status, order_version, requested_at/received_at/canceled_at, cascade items)
- `packages/modules/order/src/services/order-module-service.ts:748-843` — createOrders_
- `packages/modules/order/src/services/order-module-service.ts:1138-1169` — createOrderLineItemsBulk_ (OrderLineItem + OrderItem 동시 생성)
- `packages/modules/order/src/services/order-module-service.ts:2480-2538` — createOrderChange_ (`version = order.version + 1`)
- `packages/modules/order/src/services/order-module-service.ts:2810-2847` — confirmOrderChange_
- `packages/modules/order/src/services/order-module-service.ts:3590-3708` — applyOrderChanges_
- `packages/modules/order/src/services/actions/create-return.ts:18-27` — Return INSERT
- `packages/modules/order/src/services/actions/create-return.ts:29-53` — ReturnItem INSERT + RETURN_ITEM 액션 적재
- `packages/modules/order/src/services/actions/create-return.ts:132-165` — 전체 흐름 + 즉시 confirm
- `packages/modules/order/src/services/actions/receive-return.ts:47-65` — updateReturnItems (received_quantity in-place UPDATE)
- `packages/modules/order/src/services/actions/receive-return.ts:67-77` — Return.status 전이
- `packages/modules/order/src/services/actions/receive-return.ts:79-117` — receiveReturn 흐름
- `packages/modules/order/src/services/actions/cancel-return.ts:36-110` — 취소 흐름
- `packages/modules/order/src/utils/apply-order-changes.ts:85` — version 분기로 INSERT vs UPDATE 결정
- `packages/modules/order/src/utils/apply-order-changes.ts:191` — Order.version UPDATE
- `packages/modules/order/src/utils/actions/return-item.ts:11-24` — RETURN_ITEM 핸들러
- `packages/modules/order/src/utils/actions/receive-return-item.ts:11-32` — RECEIVE_RETURN_ITEM 핸들러
- `packages/core/core-flows/src/order/steps/create-orders.ts` — createOrdersStep
- `packages/core/core-flows/src/order/steps/return/create-return-items-from-actions.ts:17-55` — 액션→ReturnItem 매핑 INSERT
- `packages/core/core-flows/src/order/steps/return/update-return-items.ts:33-58` — ReturnItem UPDATE 스텝 (보상 포함)
- `packages/core/core-flows/src/order/workflows/return/begin-return.ts` — Return 셸 + OrderChange 생성
- `packages/core/core-flows/src/order/workflows/return/request-item-return.ts:137-221` — RETURN_ITEM 액션 적재
- `packages/core/core-flows/src/order/workflows/return/confirm-return-request.ts:194-360` — ReturnItem 생성 + 상태 전이 + confirm
- `packages/core/core-flows/src/order/workflows/return/confirm-receive-return-request.ts:202-387` — received/damaged 합산 + 상태 전이 + confirm + 재고 복원
- `packages/core/utils/src/order/status.ts:38-59` — ReturnStatus enum
- `packages/core/utils/src/order/order-change-action.ts` — ChangeActionType enum (RETURN_ITEM, RECEIVE_RETURN_ITEM, RECEIVE_DAMAGED_RETURN_ITEM, CANCEL_RETURN_ITEM)

## Architecture Documentation

**허브-스포크 참조 구조**: `OrderLineItem` 이 허브. `OrderItem` 은 버전별 카운터 스냅샷(append-only), `ReturnItem` 은 반품 라인의 누적 수량(in-place mutable). 두 위성 엔티티는 서로 직접 FK 가 없고 `OrderLineItem.id` 라는 공통 키로만 매칭된다.

**변경 모델의 이중성**: 같은 라이프사이클 이벤트(반품 수령)에서 한쪽은 새 row INSERT(`OrderItem`), 다른 쪽은 동일 row UPDATE(`ReturnItem`) 라는 비대칭 패턴. `OrderItem` 은 "주문의 시간선" 을 보존하기 위한 append-only 설계, `ReturnItem` 은 "반품 라인의 현재 진행도" 를 표현하는 단일 row 설계.

**`OrderChange` 가 모든 mutation 의 게이트**: 반품 요청·수령·취소 어떤 단계든 `OrderChange` + `OrderChangeAction` + `confirmOrderChange` 파이프라인을 거쳐야 `OrderItem` 이 갱신된다. `ReturnItem` 의 in-place UPDATE 는 이 confirm 의 부수효과로 같은 트랜잭션에서 함께 일어난다.

**참조 키 일관성**: `RETURN_ITEM`/`RECEIVE_RETURN_ITEM` 등 모든 OrderChangeAction 의 `details.reference_id` 는 일관되게 `OrderLineItem.id`. 액션 처리기는 이 id 로 메모리상 currentOrder 에서 해당 라인을 찾아 카운터를 갱신한다.

## Related Research

- [2026-05-07-order-item-version-management.md](2026-05-07-order-item-version-management.md) — OrderItem 버전 관리 구조와 주문 조회 쿼리 (반품 시나리오 중심)
- [2026-05-07-confirm-return-receive-promotion-buy-rules.md](2026-05-07-confirm-return-receive-promotion-buy-rules.md)

## Open Questions

- `ReturnItem.received_quantity > Return.items[].quantity` 가 되는 케이스(과수령)가 코드 레벨에서 어떻게 차단되는지는 본 조사에서 확정적으로 검증하지 못함 (`receive-return.ts` 는 누적 add 만 수행하며 상한 검증 위치는 별도 확인 필요).
- `OrderItem` 과 `ReturnItem` 의 동시성 가드 (예: 같은 OrderChange 가 병렬 confirm 될 때) 는 본 조사 범위 밖.
