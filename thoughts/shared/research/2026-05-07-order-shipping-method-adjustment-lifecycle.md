---
date: 2026-05-07T00:00:00+09:00
researcher: SAN KIM
git_commit: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
branch: develop
repository: medusa-fork
topic: "OrderShippingMethodAdjustment 엔티티 라이프사이클"
tags: [research, codebase, order, shipping-method-adjustment, adjustment, promotion, order-change]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
---

# Research: OrderShippingMethodAdjustment 엔티티 라이프사이클

**Date**: 2026-05-07 KST  
**Researcher**: SAN KIM  
**Git Commit**: `1c0e69e9cb59b5954175bbcd8b7e382aae127dea`  
**Branch**: develop

## Research Question

`OrderShippingMethodAdjustment` 엔티티의 라이프사이클을 조사해줘. 이 엔티티와 연결된 엔티티도 함께 맥락 관점에서 설명해줘. 생성/수정/삭제 시점, 연결된 엔티티(OrderShippingMethod, OrderLineItemAdjustment 등), DB 스키마, 서비스 메서드, 워크플로우에서의 사용 흐름을 모두 포함해서 조사해줘.

## Summary

`OrderShippingMethodAdjustment`는 주문의 배송 방법에 적용된 할인/프로모션 조정값 하나를 나타내는 엔티티다. `version` 필드로 주문 변경 이력을 추적하며, 동일한 배송 방법에 여러 버전의 조정값이 공존할 수 있다 (soft delete로 구버전 보존).

**생성** 경로는 두 가지다:
1. **카트 완료 시** — Cart 모듈의 `CartShippingMethodAdjustment`가 Order 모듈로 복사되어 최초 레코드가 만들어진다.
2. **OrderChange 확정 시** — `confirmOrderChange` → `applyOrderChanges_` → `applyChangesToOrder` 경로에서 `SHIPPING_ADJUSTMENTS_REPLACE` 액션이 처리되며 새 버전의 레코드가 생성된다.

**삭제**는 soft delete 기반이며, `revertLastChange` 호출 시 현재 버전의 레코드가 soft delete된다.

## Detailed Findings

### 1. 엔티티 모델 (DB 스키마)

**파일**: [packages/modules/order/src/models/shipping-method-adjustment.ts](packages/modules/order/src/models/shipping-method-adjustment.ts)

| 컬럼 | 타입 | 제약 |
|---|---|---|
| `id` | text | PK, prefix `ordsmadj_` |
| `version` | integer | NOT NULL, default 1 |
| `description` | text | NULL |
| `promotion_id` | text | NULL |
| `code` | text | NULL |
| `amount` | numeric | NOT NULL |
| `raw_amount` | jsonb | NOT NULL (BigNumber 원본) |
| `provider_id` | text | NULL |
| `shipping_method_id` | text | NOT NULL (FK) |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |
| `deleted_at` | timestamptz | NULL |

**테이블명**: `order_shipping_method_adjustment`

**인덱스**:
- `IDX_order_shipping_method_adjustment_shipping_method_id` — `shipping_method_id` 단순 인덱스
- `IDX_order_shipping_method_adjustment_version_shipping_method` — `(version, shipping_method_id)` 복합 unique (조건: `deleted_at IS NULL`)

**`amount` 이중 컬럼 구조**: `model.bigNumber()` 선언 하나가 DB에 `amount (numeric)`과 `raw_amount (jsonb)` 두 컬럼을 생성한다. `numeric`은 실수 연산용, `jsonb`는 `{ value: string, precision?: number }` 형태의 원본 데이터다.

---

### 2. 엔티티 연결 구조

```
Order
└─ OrderShipping (피벗, order_shipping_method 테이블)
   └─ OrderShippingMethod  (order.ts → hasMany → OrderShipping → hasOne → OrderShippingMethod)
      ├─ OrderShippingMethodAdjustment  (hasMany, cascade delete)
      └─ OrderShippingMethodTaxLine     (hasMany, cascade delete)
```

- [packages/modules/order/src/models/order.ts](packages/modules/order/src/models/order.ts): `shipping_methods` → `hasMany(() => OrderShipping)`
- [packages/modules/order/src/models/order-shipping-method.ts](packages/modules/order/src/models/order-shipping-method.ts): `order`, `return`, `exchange`, `claim` 중 하나에 선택적 belongsTo
- [packages/modules/order/src/models/shipping-method.ts](packages/modules/order/src/models/shipping-method.ts):
  - `adjustments`: `hasMany(() => OrderShippingMethodAdjustment, { mappedBy: "shipping_method" })`
  - `.cascades({ delete: ["tax_lines", "adjustments"] })` — OrderShippingMethod 삭제 시 adjustments cascade soft-delete

`OrderShippingMethodAdjustment`는 `OrderShippingMethod`에만 직접 belongsTo한다. Order ID나 version을 자체적으로 들고 있지 않고, `version` 필드로 어느 시점의 변경에 속하는지 식별한다.

---

### 3. 인접 Adjustment 엔티티와의 비교

주문 모듈의 adjustment 엔티티는 3가지 수준이 있다.

| 항목 | OrderShippingMethodAdjustment | OrderLineItemAdjustment |
|---|---|---|
| ID prefix | `ordsmadj` | `ordliadj` |
| version | O (default 1) | O (default 1) |
| description | O | O |
| promotion_id | O | O |
| code | O | O |
| amount | O (bigNumber) | O (bigNumber) |
| provider_id | O | O |
| is_tax_inclusive | 없음 | O (default false) |
| FK 대상 | `OrderShippingMethod` | `OrderLineItem` |
| 복합 unique 인덱스 | O (version, shipping_method_id) | 없음 |

주문 레벨 전용 adjustment 엔티티(`OrderAdjustment` 등)는 존재하지 않는다. [packages/modules/order/src/models/index.ts](packages/modules/order/src/models/index.ts)에 해당 export가 없다.

두 엔티티 모두 공통 베이스 클래스를 상속하지 않고 `model.define()`을 각자 직접 호출하는 방식으로 정의된다.

---

### 4. 서비스 메서드

**파일**: [packages/modules/order/src/services/order-module-service.ts](packages/modules/order/src/services/order-module-service.ts)

퍼블릭 API는 `OrderModuleService`가 담당하고, 실제 DB 연산은 내부 서비스 `this.orderShippingMethodAdjustmentService_`(MedusaInternalService 기반)가 처리한다.

#### createOrderShippingMethodAdjustments (line 1867)

오버로드 3개:
- `(adjustments: CreateOrderShippingMethodAdjustmentDTO[])` — 검증 없이 직접 생성
- `(adjustment: CreateOrderShippingMethodAdjustmentDTO)` — 단일 생성
- `(orderId: string, adjustments: [...])` — orderId로 주문 조회 후 `shipping_method_id` 소속 검증 → 생성

#### setOrderShippingMethodAdjustments (line 1794)

시그니처: `(orderId: string, adjustments: (Create|Update)[])` 

내부 흐름:
1. `retrieveOrder(orderId, { relations: ["shipping_methods.adjustments"] })`
2. 기존 adjustment ID 집합과 입력 집합 비교
3. 입력에 없는 기존 adjustment → `delete(toDelete)`
4. 입력 전체 → `upsert(adjustments)`

"전체 교체(replace-all)" 의미를 가진다.

#### upsertOrderShippingMethodAdjustments (line 1763)

검증 없이 바로 `orderShippingMethodAdjustmentService_.upsert(adjustments)` 호출.

#### deleteOrderShippingMethodAdjustments

`generateMethodForModels`에 의해 자동 생성. `IOrderModuleService`에 3가지 오버로드 선언 (service.ts line 2020-2055):
- ID 배열, 단일 ID, selector 필터 방식

---

### 5. version 필드 관리 메커니즘

`version`은 DB나 ORM이 자동 증분하지 않는다. `OrderModuleService`가 직접 값을 주입한다.

**OrderChange 생성 시** ([packages/modules/order/src/services/order-module-service.ts](packages/modules/order/src/services/order-module-service.ts) line 2534):
- 새 OrderChange의 `version = order.version + 1`로 설정

**조정값 생성 시** ([packages/modules/order/src/utils/apply-order-changes.ts](packages/modules/order/src/utils/apply-order-changes.ts) line 61, 179-188):
```
const version = actionsMap[order.id]?.[0]?.version ?? order.version

shippingMethodAdjustmentsToCreate.push({
  shipping_method_id: associatedMethodId,
  version,    // ← OrderChangeAction에서 가져온 version
  amount, description, promotion_id, code
})
```
`version > order.version`인 경우에만 새 조정값을 생성한다.

**롤백 시** ([packages/modules/order/src/services/order-module-service.ts](packages/modules/order/src/services/order-module-service.ts) line 3330-3385):
- 현재 버전의 `shipping_method_id`들로 list 조회 → `softDelete`
- `orderService_.update({ version: order.version - 1 })`로 Order version 감소

---

### 6. 워크플로우 사용 흐름

#### 6-1. 카트 단계 (프로모션 적용)

`CartShippingMethodAdjustment`는 Cart 모듈에서 별도 관리되며, Order 모듈의 엔티티와는 구분된다.

**updateCartPromotionsWorkflow** ([packages/core/core-flows/src/cart/workflows/update-cart-promotions.ts](packages/core/core-flows/src/cart/workflows/update-cart-promotions.ts)):

```
getActionsToComputeFromPromotionsStep  (Promotion Module 계산)
  → prepareAdjustmentsFromPromotionActionsStep
      (ADD_SHIPPING_METHOD_ADJUSTMENT → shippingMethodAdjustmentsToCreate)
      (REMOVE_SHIPPING_METHOD_ADJUSTMENT → shippingMethodAdjustmentIdsToRemove)
  → parallelize(
      removeShippingMethodAdjustmentsStep   (cartModuleService.softDelete)
      createShippingMethodAdjustmentsStep   (cartModuleService.addShippingMethodAdjustments)
    )
```

#### 6-2. 카트 → 주문 변환 (Cart Completion)

**completeCartWorkflow** ([packages/core/core-flows/src/cart/workflows/complete-cart.ts](packages/core/core-flows/src/cart/workflows/complete-cart.ts) line 417-429):

```
cart.shipping_methods[].adjustments
  → prepareAdjustmentsData()   (code, amount, description, promotion_id, provider_id 추출)
  → createOrdersStep({ shipping_methods: [{ adjustments: [...] }] })
  → OrderModuleService.createOrders_()
  → order_shipping_method_adjustment 레코드 생성 (version=1, 카트의 조정값 복사)
```

이 시점에 `OrderShippingMethodAdjustment`의 최초 레코드가 생성된다.

#### 6-3. 주문 변경 프리뷰 (Order Edit / Exchange)

**computeAdjustmentsForPreviewWorkflow** ([packages/core/core-flows/src/order/workflows/compute-adjustments-for-preview.ts](packages/core/core-flows/src/order/workflows/compute-adjustments-for-preview.ts)):

`carry_over_promotions=true`이고 프로모션이 있을 때:

```
previewOrderChangeStep
  → prepareOrderComputeActionContextStep
  → getActionsToComputeFromPromotionsStep
  → prepareAdjustmentsFromPromotionActionsStep
  → 각 shipping method에 대해 SHIPPING_ADJUSTMENTS_REPLACE 타입 OrderChangeAction 생성
    {
      version: orderChange.version,
      action: "SHIPPING_ADJUSTMENTS_REPLACE",
      details: { reference_id: shippingMethod.id, adjustments: [...] }
    }
```

이 단계에서는 실제 `order_shipping_method_adjustment` 레코드가 아직 생성되지 않는다. OrderChangeAction으로만 등록된 상태다.

`carry_over_promotions=false`이면 기존 `SHIPPING_ADJUSTMENTS_REPLACE` 액션들을 `deleteOrderChangeActionsStep`으로 삭제한다.

#### 6-4. 주문 변경 확정 (Confirm Order Change)

**confirmOrderChanges** → **applyOrderChanges_** → **applyChangesToOrder**:

```
applyChangesToOrder (shipping-adjustments-replace.ts)
  → existing.adjustments = action.details.adjustments ?? []  (가상 교체)

applyChangesToOrder (apply-order-changes.ts line 147-188)
  → version > order.version인 배송 방법의 adjustments를 수집
  → shippingMethodAdjustmentsToCreate 배열 구성

applyOrderChanges_ (order-module-service.ts line 3695-3700)
  → orderShippingMethodAdjustmentService_.create(shippingMethodAdjustmentsToCreate)
  → order_shipping_method_adjustment 레코드 생성 (새 version 번호 포함)
```

이 시점에 새 버전의 `OrderShippingMethodAdjustment` 레코드가 실제로 DB에 생성된다.

#### 6-5. 롤백 (Revert Last Change)

```
revertLastChange_ (order-module-service.ts line 3330-3355)
  → orderShippingMethodAdjustmentService_.list({ shipping_method_id, version: currentVersion })
  → orderShippingMethodAdjustmentService_.softDelete(ids)
  → orderService_.update({ version: order.version - 1 })
```

현재 버전의 레코드를 soft delete하고 Order의 version을 한 단계 낮춘다. soft delete된 레코드는 DB에 남아있어 이력 조회가 가능하다.

---

### 7. 비즈니스 시나리오별 생명주기 요약

| 시나리오 | 트리거 | 결과 |
|---|---|---|
| 카트 프로모션 적용 | `updateCartPromotionsWorkflow` | Cart 모듈에 `CartShippingMethodAdjustment` 생성 |
| 카트 완료 | `completeCartWorkflow` | Order 모듈에 `OrderShippingMethodAdjustment` 생성 (version=1) |
| Order Edit 프리뷰 | `computeAdjustmentsForPreviewWorkflow` | OrderChangeAction(SHIPPING_ADJUSTMENTS_REPLACE)만 생성 |
| Order Edit 확정 | `confirmOrderEditRequestWorkflow` | 새 version의 `OrderShippingMethodAdjustment` 생성 |
| Exchange 확정 | `confirmExchangeRequestWorkflow` | 동일 패턴 (exchange_id 추가 포함) |
| Order Change 롤백 | `revertLastChange_` | 현재 version 레코드 soft delete, Order version 감소 |
| OrderShippingMethod 삭제 | cascade | adjustments 전체 cascade soft-delete |

## Code References

- [packages/modules/order/src/models/shipping-method-adjustment.ts](packages/modules/order/src/models/shipping-method-adjustment.ts) — 엔티티 모델 정의
- [packages/modules/order/src/models/shipping-method.ts](packages/modules/order/src/models/shipping-method.ts) — OrderShippingMethod (hasMany adjustments, cascade delete)
- [packages/modules/order/src/models/order-shipping-method.ts](packages/modules/order/src/models/order-shipping-method.ts) — Order ↔ ShippingMethod 피벗
- [packages/modules/order/src/models/line-item-adjustment.ts](packages/modules/order/src/models/line-item-adjustment.ts) — 비교 대상: OrderLineItemAdjustment
- [packages/modules/order/src/services/order-module-service.ts](packages/modules/order/src/services/order-module-service.ts) — `createOrderShippingMethodAdjustments` (line 1867), `setOrderShippingMethodAdjustments` (line 1794), `applyOrderChanges_` (line 3591)
- [packages/modules/order/src/utils/apply-order-changes.ts](packages/modules/order/src/utils/apply-order-changes.ts) — `applyChangesToOrder` (line 61, 147-188)
- [packages/modules/order/src/utils/actions/shipping-adjustments-replace.ts](packages/modules/order/src/utils/actions/shipping-adjustments-replace.ts) — SHIPPING_ADJUSTMENTS_REPLACE 액션 핸들러
- [packages/core/core-flows/src/cart/steps/create-shipping-method-adjustments.ts](packages/core/core-flows/src/cart/steps/create-shipping-method-adjustments.ts) — Cart 조정 생성 스텝
- [packages/core/core-flows/src/cart/steps/remove-shipping-method-adjustments.ts](packages/core/core-flows/src/cart/steps/remove-shipping-method-adjustments.ts) — Cart 조정 제거 스텝
- [packages/core/core-flows/src/cart/steps/prepare-adjustments-from-promotion-actions.ts](packages/core/core-flows/src/cart/steps/prepare-adjustments-from-promotion-actions.ts) — 프로모션 액션 → 조정값 분류 스텝
- [packages/core/core-flows/src/cart/workflows/update-cart-promotions.ts](packages/core/core-flows/src/cart/workflows/update-cart-promotions.ts) — 카트 프로모션 업데이트 워크플로우
- [packages/core/core-flows/src/cart/workflows/complete-cart.ts](packages/core/core-flows/src/cart/workflows/complete-cart.ts) — 카트 완료 워크플로우 (line 417-429)
- [packages/core/core-flows/src/cart/utils/prepare-line-item-data.ts](packages/core/core-flows/src/cart/utils/prepare-line-item-data.ts) — `prepareAdjustmentsData` (line 205-213)
- [packages/core/core-flows/src/order/workflows/compute-adjustments-for-preview.ts](packages/core/core-flows/src/order/workflows/compute-adjustments-for-preview.ts) — 주문 변경 프리뷰 조정 워크플로우
- [packages/core/types/src/order/common.ts](packages/core/types/src/order/common.ts) — `OrderShippingMethodAdjustmentDTO` (line 129-149), `OrderAdjustmentLineDTO` (line 79-124)
- [packages/core/types/src/order/mutations.ts](packages/core/types/src/order/mutations.ts) — `CreateOrderAdjustmentDTO` (line 284), `UpdateOrderAdjustmentDTO` (line 324)

## Architecture Documentation

**Cart 모듈과 Order 모듈의 분리**: `CartShippingMethodAdjustment`(Cart 모듈)와 `OrderShippingMethodAdjustment`(Order 모듈)는 별개의 엔티티로 별개의 DB 테이블에 저장된다. 카트 완료 시 Cart 조정값의 필드 일부가 Order 쪽으로 복사된다.

**version 기반 이력 관리**: `(version, shipping_method_id)` 복합 unique 인덱스(soft delete 제외)로 각 배송 방법의 버전별 조정값이 중복 없이 관리된다. 주문이 변경될 때마다 이전 버전 레코드는 soft delete로 보존하고 새 버전 레코드가 삽입된다.

**OrderChangeAction → 실제 레코드**: 프리뷰 단계에서는 `SHIPPING_ADJUSTMENTS_REPLACE` 타입의 OrderChangeAction만 생성된다. 실제 `order_shipping_method_adjustment` 레코드는 OrderChange가 `confirm`될 때만 생성된다.

**BigNumber 이중 컬럼**: `amount (numeric)` + `raw_amount (jsonb)` 쌍이 표준 패턴으로 Order 모듈 전반에 걸쳐 사용된다.

## Related Research

- [2026-05-07-order-change-order-change-action-relationship.md](2026-05-07-order-change-order-change-action-relationship.md)
- [2026-05-07-order-line-item-order-item-return-item-lifecycle.md](2026-05-07-order-line-item-order-item-return-item-lifecycle.md)

## Open Questions

- `OrderLineItemAdjustment`에만 `is_tax_inclusive` 필드가 있고 `OrderShippingMethodAdjustment`에는 없는 이유 (미확인)
- 카트 완료 시 `CartShippingMethodAdjustment`의 `is_tax_inclusive` 값이 Order 쪽으로 복사되는지 여부 (미확인)
