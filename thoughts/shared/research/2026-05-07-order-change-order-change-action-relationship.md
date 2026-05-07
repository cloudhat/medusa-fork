---
date: 2026-05-07T00:00:00+09:00
researcher: SAN KIM
git_commit: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
branch: develop
repository: medusa-fork
topic: "OrderChange와 OrderChangeAction의 관계"
tags: [research, codebase, order, order-change, order-change-action, order-line-item-adjustment]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
last_updated_note: "OrderLineItemAdjustment 추가, OrderChange/Action 개념 관계 보강"
---

# Research: OrderChange와 OrderChangeAction의 관계

**Date**: 2026-05-07 KST  
**Researcher**: SAN KIM  
**Git Commit**: `1c0e69e9cb59b5954175bbcd8b7e382aae127dea`  
**Branch**: develop  
**Repository**: medusa-fork

## Research Question

OrderChange, OrderChangeAction의 관계를 조사해줘

## Summary

`OrderChange`는 Order에 가해질 변경 사항의 컨테이너이고, `OrderChangeAction`은 그 컨테이너 안에 담기는 개별 변경 항목이다. OrderChange 하나에 OrderChangeAction 여러 개가 포함된다(1:N). OrderChange가 confirm되는 시점에 소속 Action들이 order 상태에 실제로 반영되고, 각 Action의 `applied` 플래그가 `true`로 전환된다.

## Detailed Findings

### 1. 엔티티 모델 정의

**파일 위치**
- [packages/modules/order/src/models/order-change.ts](packages/modules/order/src/models/order-change.ts)
- [packages/modules/order/src/models/order-change-action.ts](packages/modules/order/src/models/order-change-action.ts)

#### OrderChange 주요 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | `model.id({ prefix: "ordch" })` | PK, ULID |
| `order_id` | 관계 FK | belongsTo Order |
| `version` | `model.number()` | 이 변경이 확정될 때 Order에 부여될 버전 번호 (`order.version + 1`) |
| `status` | `model.enum(OrderChangeStatus)` | 기본값 `PENDING` |
| `change_type` | `model.text().nullable()` | `OrderChangeType` 값 (return_request, exchange, claim, edit 등 7종) |
| `return_id / claim_id / exchange_id` | `model.text().nullable()` | 연관 엔티티 참조 (텍스트, FK 아님) |
| `carry_over_promotions` | `model.boolean().nullable()` | 2.12.0 추가. 프로모션 이월 여부 |
| `requested_by/at`, `confirmed_by/at`, `declined_by/at/reason`, `canceled_by/at` | text/dateTime, nullable | 상태 전환 이력 추적 필드 |
| `actions` | hasMany → OrderChangeAction | cascade delete 설정 |

#### OrderChangeAction 주요 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | `model.id({ prefix: "ordchact" })` | PK, ULID |
| `order_change_id` | 관계 FK (nullable) | belongsTo OrderChange, nullable |
| `order_id` | `model.text()` | NOT NULL. 속한 Order ID |
| `ordering` | `model.autoincrement()` | DB 자동증가. 액션 실행 순서 |
| `version` | `model.number().nullable()` | 소속 OrderChange의 version과 동기화 |
| `action` | `model.text()` | NOT NULL. `ChangeActionType` 값 (25종) |
| `details` | `model.json().default({})` | 액션별 세부 파라미터 JSON |
| `amount` | `model.bigNumber().nullable()` | 금액 변동 |
| `applied` | `model.boolean().default(false)` | confirm 후 `true`로 전환 |
| `reference / reference_id` | `model.text().nullable()` | 참조 엔티티 타입/ID |

#### 관계 선언 (모델 수준)

```typescript
// order-change.ts — OrderChange 쪽
actions: model.hasMany<() => typeof OrderChangeAction>(() => OrderChangeAction),
// cascade delete 설정
.cascades({ delete: ["actions"] })

// order-change-action.ts — OrderChangeAction 쪽
order_change: model
  .belongsTo<() => typeof OrderChange>(() => OrderChange, { mappedBy: "actions" })
  .nullable(),
```

`OrderChangeAction.order_change`는 nullable이므로, OrderChange 없이 독립적으로 생성될 수 있다.

### 2. 인스턴스 생성 시 자동 필드 복사 (OnInit 훅)

`order-module-service.ts:145–166`에 MikroORM `@OnInit` / `@BeforeCreate` 훅이 등록되어 있다. `OrderChangeAction` 인스턴스 생성 시 `order_change`가 있으면 아래 필드를 자동으로 복사한다.

- `version` ← `order_change.version`
- `order_id` ← `order_change.order_id`
- `claim_id` ← `order_change.claim_id`
- `exchange_id` ← `order_change.exchange_id`
- `return_id` ← `order_change.return_id` (claim_id, exchange_id가 없을 경우)

### 3. DB 인덱스 패턴

두 테이블 모두 Partial Index 패턴(`WHERE deleted_at IS NULL` 또는 `IS NOT NULL`)을 사용한다.

**order_change 테이블 주요 인덱스**

| 인덱스명 | 컬럼 |
|----------|------|
| `IDX_order_change_order_id` | `order_id` |
| `IDX_order_change_version` | `(order_id, version)` |
| `IDX_order_change_status` | `status` |
| `IDX_order_change_return/claim/exchange_id` | nullable 참조 ID들 |

**order_change_action 테이블 주요 인덱스**

| 인덱스명 | 컬럼 |
|----------|------|
| `IDX_order_change_action_order_change_id` | `order_change_id` |
| `IDX_order_change_action_order_id` | `order_id` |
| `IDX_order_change_action_ordering` | `ordering` |

### 4. OrderChangeStatus 전환 흐름

```
PENDING ──► REQUESTED ──► CONFIRMED
    │             │
    └──────────► CANCELED
    └──────────► DECLINED
```

모든 전환은 `PENDING` 또는 `REQUESTED` 상태에서만 가능하다. `getAndValidateOrderChange_`에서 상태를 검증하고, 그 외 상태이면 `MedusaError.Types.INVALID_DATA`를 던진다.

| 메서드 | 결과 status | 세팅되는 날짜 필드 |
|--------|------------|-------------------|
| `confirmOrderChange` | CONFIRMED | `confirmed_at` |
| `cancelOrderChange` | CANCELED | `canceled_at` |
| `declineOrderChange` | DECLINED | `declined_at` |
| `registerOrderChange` | CONFIRMED (즉시) | `confirmed_at` |

### 5. ChangeActionType 전체 목록

`packages/core/utils/src/order/order-change-action.ts`에 정의된 25종:

| 그룹 | 값 |
|------|-----|
| 아이템 변경 | `ITEM_ADD`, `ITEM_REMOVE`, `ITEM_UPDATE` |
| 반품 | `RETURN_ITEM`, `RECEIVE_RETURN_ITEM`, `CANCEL_RETURN_ITEM`, `RECEIVE_DAMAGED_RETURN_ITEM` |
| 이행 | `FULFILL_ITEM`, `SHIP_ITEM`, `DELIVER_ITEM`, `CANCEL_ITEM_FULFILLMENT` |
| 배송 | `SHIPPING_ADD`, `SHIPPING_REMOVE`, `SHIPPING_UPDATE` |
| 손상 처리 | `WRITE_OFF_ITEM`, `REINSTATE_ITEM` |
| 기타 | `TRANSFER_CUSTOMER`, `UPDATE_ORDER_PROPERTIES`, `CREDIT_LINE_ADD`, `PROMOTION_ADD`, `PROMOTION_REMOVE`, `ITEM_ADJUSTMENTS_REPLACE`, `SHIPPING_ADJUSTMENTS_REPLACE` |

### 6. 서비스 메서드 — OrderChange에서 OrderChangeAction으로의 데이터 흐름

#### createOrderChange_ (order-module-service.ts:2479–2539)

1. 해당 `order_id`에 PENDING/REQUESTED 상태의 OrderChange가 이미 있으면 에러 → **한 Order에 active OrderChange는 동시에 하나**
2. `order.version + 1`을 신규 OrderChange의 `version`으로 세팅
3. `CreateOrderChangeDTO.actions` 배열에 action 데이터를 담으면 OrderChange 생성과 함께 OrderChangeAction도 함께 생성

#### addOrderAction_ (order-module-service.ts:3546–3588)

1. `order_change_id`가 있는 action들에 대해 `getAndValidateOrderChange_` 호출 (PENDING/REQUESTED 검증)
2. `ordChange.order_id`, `ordChange.version`을 각 action 데이터에 주입
3. `orderChangeActionService_.create()` 호출

#### confirmOrderChange_ → applyOrderChanges_ (order-module-service.ts:2810–2848, 3590–3708)

confirm 시 실행되는 핵심 흐름:

1. OrderChange를 `CONFIRMED`로 update
2. `applyOrderChanges_` 호출:
   - `applied: true`인 action 건너뜀
   - `applyChangesToOrder(orders, actionsMap)` — 변경 계산
   - DB에 동시 저장:
     - `orderService_.update()` — order.version 업데이트
     - `orderChangeActionService_.update({ applied: true })` — action 적용 표시
     - `orderItemService_.upsert()` — OrderItem 버전 생성
     - `orderSummaryService_.upsert()` — 새 summary 저장
     - `orderShippingService_.upsert()` — 배송 버전 생성
     - `orderCreditLineService_.upsert()` — credit line 버전 생성
     - `lineItemAdjustmentService_.create()` / `shippingMethodAdjustmentService_.create()`

#### previewOrderChange (order-module-service.ts:2541–2603)

- `applyChangesToOrder()`를 `addActionReferenceToObject: true` 옵션으로 호출하여 DB 저장 없이 계산만 수행
- `ordering` 오름차순으로 action을 정렬하여 순서대로 적용

#### registerOrderChange (order-module-service.ts:2928–2972)

`createOrderChange` + `confirmOrderChange`를 한 번에 처리하는 단축 경로. 기존 active OrderChange 존재 여부를 체크하지 않고 CONFIRMED 상태로 즉시 생성한다. 내부적으로 `ChangeActionType.UPDATE_ORDER_PROPERTIES` 타입의 action 하나를 `applied: true`로 함께 생성한다.

#### undoLastChange_ vs revertLastChange_

| 메서드 | OrderChange | OrderChangeAction | OrderItem/Summary/Shipping 처리 |
|--------|-------------|-------------------|---------------------------------|
| `undoLastChange_` | status → PENDING | `applied: false`로 복원 | soft delete |
| `revertLastChange_` | soft delete | soft delete | soft delete, Return도 처리 |

### 7. OrderLineItemAdjustment — 프로모션 할인 스냅샷

**파일**: [참고자료/prisma 변환/schema.order.prisma:418](참고자료/prisma%20변환/schema.order.prisma)  
**실제 모델**: [packages/modules/order/src/models/line-item-adjustment.ts](packages/modules/order/src/models/line-item-adjustment.ts)

#### 필드 정의

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | String PK | 조정 고유 ID |
| `version` | Int (기본값 1) | 이 조정이 속하는 주문 버전 |
| `item_id` | String FK | 소속 OrderLineItem ID |
| `promotion_id` | String? | 연결된 프로모션 ID (Remote Link → Promotion 모듈) |
| `code` | String? | 프로모션 코드 |
| `amount` | Decimal | 할인 금액 (양수) |
| `raw_amount` | Json | amount의 정밀도 보존용 원본 JSON |
| `is_tax_inclusive` | Boolean (기본값 false) | 할인 금액에 세금 포함 여부 |
| `description` | String? | 할인 설명 |
| `provider_id` | String? | 할인 공급자 ID |

#### OrderLineItem과의 관계

```
OrderLineItem (1) ──────(N)──► OrderLineItemAdjustment
                              (item_id FK, version별 스냅샷)
```

- `OrderLineItem`은 상품 정보(가격, 수량 등)의 불변 스냅샷
- `OrderLineItemAdjustment`는 그 아이템에 적용된 프로모션 할인의 버전별 스냅샷
- 하나의 `OrderLineItem`에 여러 조정(복수 프로모션 중첩)이 붙을 수 있음

#### OrderChange confirm 시 생성 시점

`applyOrderChanges_`(order-module-service.ts:3590)에서 `confirmOrderChange` 호출 시:

```
confirmOrderChange_
  └── applyOrderChanges_
        └── lineItemAdjustmentService_.create(lineItemAdjustmentsToCreate)
```

- 새로운 `version` 번호로 `OrderLineItemAdjustment` 레코드를 **새로 생성**한다
- 기존 버전의 조정 레코드는 삭제하지 않고 그대로 남는다 (버전 이력 보존)
- `ShippingMethodAdjustment`도 동일한 방식으로 처리된다 (`shippingMethodAdjustmentService_.create`)

#### carry_over_promotions 필드와의 관계

`OrderChange.carry_over_promotions`(2.12.0 추가)가 이 동작을 제어한다.

| `carry_over_promotions` 값 | 동작 |
|---------------------------|------|
| `true` | 이전 버전의 프로모션 할인을 새 버전에 그대로 이월 |
| `false` / `null` | 새 버전에서 프로모션 재계산 |

#### 관련 ChangeActionType

`ITEM_ADJUSTMENTS_REPLACE`와 `SHIPPING_ADJUSTMENTS_REPLACE` action 타입이 조정 항목을 직접 교체한다.

| action | 동작 |
|--------|------|
| `ITEM_ADJUSTMENTS_REPLACE` | 기존 라인 아이템 조정을 `details`의 새 조정 목록으로 교체 |
| `SHIPPING_ADJUSTMENTS_REPLACE` | 배송 방법 조정을 교체 |
| `PROMOTION_ADD` | 프로모션 추가 (조정 항목 생성) |
| `PROMOTION_REMOVE` | 프로모션 제거 (조정 항목 삭제) |

#### 반품 예시에서의 동작

반품 confirm (`confirmReturnRequestWorkflow`) 시:
- `RETURN_ITEM` action → `return_requested_quantity` 업데이트 + OrderItem 새 버전 생성
- 반품 아이템의 `OrderLineItemAdjustment`는 **새 버전으로 복사**되어 할인 내역이 유지됨
- 환불 금액 계산 시 해당 버전의 조정 금액을 반영하여 프로모션 할인 적용 후 실지급액 기준으로 환불

### 8. 워크플로우 수준 패턴

#### begin-* 워크플로우 (OrderChange 생성)

Return, Exchange, Claim, Order Edit 시작 시 공통 패턴:

```
create{Return/Exchange/Claim}Step
  → transform (change_type + *_id 조합)
    → createOrderChangeStep
```

Order Edit의 경우 `acquireLockStep` / `releaseLockStep`으로 감싸진다.

#### request-*-item / *-add-item 워크플로우 (OrderChangeAction 추가)

```
조회 단계 (order, orderChange, return/exchange 조회)
  → transform (ChangeActionType + details 조합)
    → createOrderChangeActionsWorkflow.runAsStep()
      → previewOrderChangeStep (반환값으로 사용)
```

#### remove-*-action 워크플로우 (OrderChangeAction 제거)

1. action 타입 검증
2. `deleteOrderChangeActionsStep({ ids: [action_id] })`
3. 남은 SHIPPING_ADD action 제거 여부를 `when()`으로 분기

#### confirm-*-request 워크플로우 (OrderChange 확정)

1. PENDING/REQUESTED 상태의 OrderChange 조회
2. `orderChange.actions`를 `ChangeActionType`별로 분기하여 실제 엔티티 생성
3. `confirmOrderChanges` 스텝 호출 (compensation: `undoLastChange`)

## Code References

- [packages/modules/order/src/models/order-change.ts](packages/modules/order/src/models/order-change.ts) — OrderChange 모델 정의
- [packages/modules/order/src/models/order-change-action.ts](packages/modules/order/src/models/order-change-action.ts) — OrderChangeAction 모델 정의
- [packages/modules/order/src/services/order-module-service.ts](packages/modules/order/src/services/order-module-service.ts) — 서비스 메서드 (createOrderChange_:2479, addOrderAction_:3546, confirmOrderChange_:2810, applyOrderChanges_:3590, previewOrderChange:2541, registerOrderChange:2928)
- [packages/core/utils/src/order/order-change.ts](packages/core/utils/src/order/order-change.ts) — `OrderChangeStatus`, `OrderChangeType` enum
- [packages/core/utils/src/order/order-change-action.ts](packages/core/utils/src/order/order-change-action.ts) — `ChangeActionType` enum
- [packages/core/types/src/order/common.ts](packages/core/types/src/order/common.ts) — `OrderChangeDTO`:2132, `OrderChangeActionDTO`:2277, `OrderPreviewDTO`:3044, `OrderChangeReturn`:2979
- [packages/core/types/src/order/mutations.ts](packages/core/types/src/order/mutations.ts) — `CreateOrderChangeDTO`:892, `CreateOrderChangeActionDTO`:1170
- [packages/core/types/src/order/service.ts](packages/core/types/src/order/service.ts) — `IOrderModuleService` 메서드 정의
- [packages/core/core-flows/src/order/steps/create-order-change.ts](packages/core/core-flows/src/order/steps/create-order-change.ts)
- [packages/core/core-flows/src/order/steps/confirm-order-changes.ts](packages/core/core-flows/src/order/steps/confirm-order-changes.ts)
- [packages/core/core-flows/src/order/steps/delete-order-change-actions.ts](packages/core/core-flows/src/order/steps/delete-order-change-actions.ts)
- [packages/core/core-flows/src/order/workflows/create-order-change-actions.ts](packages/core/core-flows/src/order/workflows/create-order-change-actions.ts)
- [packages/core/core-flows/src/order/workflows/return/begin-return.ts](packages/core/core-flows/src/order/workflows/return/begin-return.ts)
- [packages/core/core-flows/src/order/workflows/exchange/begin-order-exchange.ts](packages/core/core-flows/src/order/workflows/exchange/begin-order-exchange.ts)
- [packages/core/core-flows/src/order/workflows/return/request-item-return.ts](packages/core/core-flows/src/order/workflows/return/request-item-return.ts)
- [packages/core/core-flows/src/order/workflows/return/confirm-return-request.ts](packages/core/core-flows/src/order/workflows/return/confirm-return-request.ts)
- [packages/modules/order/src/models/line-item-adjustment.ts](packages/modules/order/src/models/line-item-adjustment.ts) — OrderLineItemAdjustment 모델 정의
- [참고자료/prisma 변환/schema.order.prisma:418](참고자료/prisma%20변환/schema.order.prisma) — OrderLineItemAdjustment Prisma 스키마

## Architecture Documentation

### OrderChange와 OrderChangeAction의 개념적 역할

| 개념 | 역할 |
|------|------|
| `OrderChange` | 결재 문서. "이 주문에 변경을 가하겠다"는 선언 자체. 기안(PENDING) → 승인(CONFIRMED) / 반려(DECLINED) / 취소(CANCELED) |
| `OrderChangeAction` | 결재 문서 안에 적힌 변경 항목 목록. 티셔츠 1개 반품, 배송비 추가 등 |
| `confirmOrderChange` | 결재 버튼. 호출 순간 모든 항목이 order에 일괄 반영됨 |

**OrderChange 상태 전환은 OrderChangeAction과 무관하다.** action이 몇 개 쌓였는지, 어떤 action 타입인지와 관계없이 `confirmOrderChange()` API 호출 한 번으로 CONFIRMED로 전환된다. OrderChangeAction은 상태 전환을 트리거하는 것이 아니라 CONFIRMED 시점에 일괄 적용되는 페이로드다.

```
OrderChange.status: PENDING
├── action 1: RETURN_ITEM   (applied: false)
└── action 2: SHIPPING_ADD  (applied: false)

  ↓ confirmOrderChange() 호출

OrderChange.status: CONFIRMED
├── action 1: RETURN_ITEM   (applied: true)  ┐ 동시에
└── action 2: SHIPPING_ADD  (applied: true)  ┘ 일괄 반영
```

### 핵심 불변 조건

1. **한 Order에 active OrderChange는 동시에 하나** — `createOrderChange_`에서 PENDING/REQUESTED 상태의 중복을 차단
2. **OrderChangeAction.applied** — confirm 전에는 `false`, confirm 후에는 `true`. `applyOrderChanges_`는 `applied: true`인 action을 건너뜀
3. **ordering 필드** — DB autoincrement. `previewOrderChange`에서 `ordering` 오름차순 정렬 후 순서대로 적용
4. **OrderChangeAction.order_change_id는 nullable** — OrderChange 없이 독립 action도 존재 가능
5. **OrderChange cascade delete** — OrderChange 삭제 시 소속 OrderChangeAction도 함께 삭제

### OrderChange.version 역할

- 생성 시: `order.version + 1`로 세팅
- confirm 시: `order.version`이 해당 값으로 업데이트됨
- `OrderItem`, `OrderShippingMethod` 등 버전 관리 엔티티들이 이 version 번호로 스냅샷을 생성

### previewOrderChange vs applyOrderChanges_

| 구분 | previewOrderChange | applyOrderChanges_ |
|------|--------------------|--------------------|
| DB 저장 | 없음 | 있음 |
| applied 플래그 | 변경 없음 | `true`로 업데이트 |
| 호출 시점 | action 추가/제거 후 preview | confirmOrderChange 내부 |
| `addActionReferenceToObject` | `true` (action을 item에 첨부) | 기본값 |

## Related Research

- [2026-05-07-order-line-item-order-item-return-item-lifecycle.md](2026-05-07-order-line-item-order-item-return-item-lifecycle.md)
- [2026-05-07-order-fulfillment-domain-connection.md](2026-05-07-order-fulfillment-domain-connection.md)
- [2026-05-07-order-item-version-management.md](2026-05-07-order-item-version-management.md)
- [2026-05-07-application-method-target-type-order-storage.md](2026-05-07-application-method-target-type-order-storage.md)

## Open Questions

- `OrderChangeAction.order_change_id`가 nullable인 경우의 실제 사용 사례 (독립 action이 생성되는 구체적 경로)
- `registerOrderChange`에서 기존 active OrderChange 존재 여부를 체크하지 않는 이유 (의도적 설계인지 여부)
- `undoLastChange_`와 `revertLastChange_` 중 어느 경로를 선택하는 기준
