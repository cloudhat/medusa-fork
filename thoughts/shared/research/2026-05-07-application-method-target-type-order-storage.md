---
date: 2026-05-07T00:00:00+09:00
researcher: SAN KIM
git_commit: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
branch: develop
repository: medusa-fork
topic: "ApplicationMethod.target_type === 'order' 일 때 주문 측 저장 위치"
tags: [research, codebase, promotion, order, application-method, adjustment]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
---

# Research: ApplicationMethod.target_type === "order" 케이스의 주문 측 저장 위치

**Date**: 2026-05-07 KST
**Researcher**: SAN KIM
**Git Commit**: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
**Branch**: develop
**Repository**: medusa-fork

## Research Question

Promotion 모듈의 `ApplicationMethod` 엔티티가 가진 `ApplicationMethodTargetType` 값이 `order` 일 때, 해당 프로모션이 주문에 적용된 결과는 주문 관련 어떤 엔티티(테이블)에 저장되는가?

## Summary

`ApplicationMethodTargetType` 은 `ORDER | SHIPPING_METHODS | ITEMS` 세 값을 갖는 enum으로 [packages/core/utils/src/promotion/index.ts:17-21](packages/core/utils/src/promotion/index.ts#L17-L21) 에 정의되어 있다. 그러나 주문 도메인에는 "주문 단위 조정(order-level adjustment)"을 저장하는 별도 테이블이 존재하지 않는다.

`target_type=ORDER` 인 프로모션은 프로모션 컴퓨트 엔진에서 **`allocation=ACROSS` 로 강제된 ITEMS 경로**로 처리되어, 적격 라인 아이템들에 금액이 분배된 `ADD_ITEM_ADJUSTMENT` 액션들로 변환된다. 그 결과는 최종적으로 다음 한 테이블에만 행으로 저장된다.

- **`order_line_item_adjustment`** (엔티티 `OrderLineItemAdjustment`)

즉, ORDER 타겟이라도 주문 자체(`Order`)나 별도의 "order_adjustment" 같은 테이블이 아니라, **각 주문 라인 아이템 단위의 조정 행들(여러 건)** 로 분산 저장된다. (참고: SHIPPING_METHODS 타겟의 경우는 `order_shipping_method_adjustment` 에 저장되며, 이는 ORDER 타겟과 무관한 별도 경로.)

## Detailed Findings

### 1. enum 정의와 promotion 측 엔티티

- `ApplicationMethodTargetType` enum: [packages/core/utils/src/promotion/index.ts:17-21](packages/core/utils/src/promotion/index.ts#L17-L21) — 값 `ORDER="order"`, `SHIPPING_METHODS`, `ITEMS`.
- `ApplicationMethod` 모델의 `target_type` 컬럼: [packages/modules/promotion/src/models/application-method.ts:18-20](packages/modules/promotion/src/models/application-method.ts#L18-L20) — enum 사용 + 인덱스 `IDX_application_method_target_type`.
- DTO 타입: [packages/core/types/src/promotion/common/application-method.ts:13](packages/core/types/src/promotion/common/application-method.ts#L13), `target_type` 사용 위치 라인 43/111/184/245.

### 2. 컴퓨트 분기: target_type=ORDER → ITEM 조정으로 변환

- [packages/modules/promotion/src/services/promotion-module.ts:889-923](packages/modules/promotion/src/services/promotion-module.ts#L889-L923) 의 STANDARD 프로모션 처리:
  - `isTargetOrder = applicationMethod.target_type === ApplicationMethodTargetType.ORDER` 로 판단.
  - `isTargetOrder` 인 경우 `getComputedActionsForItems` 를 호출하되 `allocationOverride = ApplicationMethodAllocation.ACROSS` 를 강제 — 즉 ITEMS 경로와 동일 함수, 분배 모드만 ACROSS 로 고정.
  - `isTargetShipping` 은 별도 분기.
- [packages/modules/promotion/src/utils/compute-actions/line-items.ts:175-183](packages/modules/promotion/src/utils/compute-actions/line-items.ts#L175-L183): `isTargetLineItems` 와 `isTargetOrder` 모두 `ComputedActions.ADD_ITEM_ADJUSTMENT` 를 emit. 액션 페이로드는 `item_id`, `amount`, `code` 등.
- `ComputedActions` enum 자체에 `ADD_ORDER_ADJUSTMENT` 같은 값은 존재하지 않음: [packages/core/utils/src/promotion/index.ts:46-53](packages/core/utils/src/promotion/index.ts#L46-L53). 가능한 액션은 `ADD_ITEM_ADJUSTMENT`, `ADD_SHIPPING_METHOD_ADJUSTMENT` (및 REMOVE 짝) 뿐.

### 3. 주문 측 조정 엔티티 / 테이블

주문 모듈에는 조정 모델이 **두 개뿐**이며, 주문 레벨 조정 모델은 없다.

- [packages/modules/order/src/models/line-item-adjustment.ts](packages/modules/order/src/models/line-item-adjustment.ts) — `OrderLineItemAdjustment`, `OrderLineItem.adjustments` 의 mappedBy 대상. 필드: `id, version, promotion_id, code, amount, raw_amount, is_tax_inclusive, description, provider_id, metadata, deleted_at`.
- [packages/modules/order/src/models/shipping-method-adjustment.ts](packages/modules/order/src/models/shipping-method-adjustment.ts) — `OrderShippingMethodAdjustment`, 테이블 `order_shipping_method_adjustment`.
- `Order` 엔티티 자체에는 `adjustments` 관계가 없다 (확인: [packages/modules/order/src/models/index.ts](packages/modules/order/src/models/index.ts) 의 export 목록).

### 4. 마이그레이션 (DDL)

- 테이블 생성: [packages/modules/order/src/migrations/Migration20240205120029.ts:103-106](packages/modules/order/src/migrations/Migration20240205120029.ts#L103-L106)
  - `order_line_item_adjustment` 컬럼: `id, description, promotion_id, code, amount, raw_amount, provider_id, created_at, updated_at, item_id`.
  - `order_shipping_method_adjustment` 컬럼: 동일 + `shipping_method_id`.
- 추가 컬럼: [packages/modules/order/src/migrations/Migration20240828141048.ts:5-8](packages/modules/order/src/migrations/Migration20240828141048.ts#L5-L8) (`deleted_at`, `metadata`).
- 보정: [packages/modules/order/src/migrations/Migration20240905084530.ts:5-6](packages/modules/order/src/migrations/Migration20240905084530.ts#L5-L6).

### 5. DTO

- [packages/core/types/src/order/common.ts:282](packages/core/types/src/order/common.ts#L282) `OrderLineItemAdjustmentDTO` (필드 `promotion_id` line 291).
- [packages/core/types/src/order/common.ts:299](packages/core/types/src/order/common.ts#L299) `OrderShippingMethodAdjustmentDTO`.
- [packages/core/types/src/order/common.ts:316](packages/core/types/src/order/common.ts#L316) `OrderAdjustmentLineDTO` (공통).
- [packages/core/types/src/order/mutations.ts:95-96](packages/core/types/src/order/mutations.ts#L95-L96) `CreateOrderAdjustmentDTO`, `UpdateOrderAdjustmentDTO`.

### 6. 워크플로우 경로: 컴퓨트 결과 → 주문 테이블 행 작성

#### 6.1 카트 단계에서 1차 적재

1. [packages/core/core-flows/src/cart/workflows/update-cart-promotions.ts:133](packages/core/core-flows/src/cart/workflows/update-cart-promotions.ts#L133) `getActionsToComputeFromPromotionsStep` 이 promotion 모듈의 `computeActions` 호출.
2. [packages/core/core-flows/src/cart/steps/prepare-adjustments-from-promotion-actions.ts:141-173](packages/core/core-flows/src/cart/steps/prepare-adjustments-from-promotion-actions.ts#L141-L173) 에서 `action.action` 으로 분기:
   - `ADD_ITEM_ADJUSTMENT` → `lineItemAdjustmentsToCreate`
   - `ADD_SHIPPING_METHOD_ADJUSTMENT` → `shippingMethodAdjustmentsToCreate`
3. [update-cart-promotions.ts:151,153](packages/core/core-flows/src/cart/workflows/update-cart-promotions.ts#L151) `createLineItemAdjustmentsStep`, `createShippingMethodAdjustmentsStep` 가 `cart_line_item_adjustment`, `cart_shipping_method_adjustment` 에 INSERT.

#### 6.2 카트 → 주문 변환 시 이관

- [packages/core/core-flows/src/cart/workflows/complete-cart.ts:402-488](packages/core/core-flows/src/cart/workflows/complete-cart.ts#L402-L488)
  - 라인 아이템: `prepareLineItemData` 가 `adjustments: item.adjustments ?? []` 로 매핑.
  - 배송: `prepareAdjustmentsData(sm.adjustments ?? [])` 매핑.
  - [packages/core/core-flows/src/cart/utils/prepare-line-item-data.ts:205-213](packages/core/core-flows/src/cart/utils/prepare-line-item-data.ts#L205-L213) — `code, amount, promotion_id, is_tax_inclusive` 만 골라서 옮김.
  - 최종 `createOrdersStep` 호출 시 `items.adjustments`, `shipping_methods.adjustments` 가 nested 로 전달되어 `OrderLineItemAdjustment` / `OrderShippingMethodAdjustment` 행으로 INSERT 됨.

#### 6.3 주문 편집/교환 프리뷰 (확정된 주문에 후속 적용)

- [packages/core/core-flows/src/order/workflows/compute-adjustments-for-preview.ts:80-207](packages/core/core-flows/src/core-flows/src/order/workflows/compute-adjustments-for-preview.ts)
  - 라인 104–113: 카트의 `getActionsToComputeFromPromotionsStep`, `prepareAdjustmentsFromPromotionActionsStep` 를 재사용.
  - 라인 130–148: `ChangeActionType.ITEM_ADJUSTMENTS_REPLACE` 의 order-change-action 으로 변환.
  - 라인 150–172: `ChangeActionType.SHIPPING_ADJUSTMENTS_REPLACE`.
  - 라인 178: `createOrderChangeActionsWorkflow` 로 기록 → 변경 확정 시 `OrderLineItemAdjustment` 행에 반영.

## Code References

- `packages/core/utils/src/promotion/index.ts:17-21` — `ApplicationMethodTargetType` enum
- `packages/core/utils/src/promotion/index.ts:46-53` — `ComputedActions` enum (ADD_ORDER_ADJUSTMENT 부재)
- `packages/modules/promotion/src/models/application-method.ts:18-20` — `target_type` 컬럼
- `packages/modules/promotion/src/services/promotion-module.ts:889-923` — target_type 분기 (ORDER → ITEMS+ACROSS)
- `packages/modules/promotion/src/utils/compute-actions/line-items.ts:175-183` — ADD_ITEM_ADJUSTMENT emit
- `packages/modules/order/src/models/line-item-adjustment.ts` — `OrderLineItemAdjustment`
- `packages/modules/order/src/models/shipping-method-adjustment.ts` — `OrderShippingMethodAdjustment`
- `packages/modules/order/src/migrations/Migration20240205120029.ts:103-106` — 두 테이블 DDL
- `packages/core/types/src/order/common.ts:282,299,316` — DTO
- `packages/core/core-flows/src/cart/steps/prepare-adjustments-from-promotion-actions.ts:141-173` — action → adjustment 매핑
- `packages/core/core-flows/src/cart/workflows/complete-cart.ts:402-488` — cart → order 이관
- `packages/core/core-flows/src/order/workflows/compute-adjustments-for-preview.ts:80-207` — 주문 편집 시 재계산

## Architecture Documentation

- 어댑팅 모델: 프로모션은 항상 "라인 아이템 또는 배송 수단" 두 표면 중 하나에만 물리 저장된다. ORDER 타겟은 별도 저장 표면이 아니라 **분배 정책(allocation=ACROSS)** 으로 표현된다.
- 카트와 주문이 동일한 두 종류의 조정 모델을 평행하게 가지며 (`*_line_item_adjustment`, `*_shipping_method_adjustment`), 주문 생성 시 카트의 `adjustments` 배열이 그대로 매핑되어 새 행으로 복제된다. `promotion_id` 외래 정보는 문자열 컬럼으로만 보존되며 RDB FK 는 걸려 있지 않다 (마이그레이션 DDL 기준).
- 주문 확정 후 변경(편집/교환)은 `Order Change` 액션(`ITEM_ADJUSTMENTS_REPLACE`, `SHIPPING_ADJUSTMENTS_REPLACE`)을 거쳐 같은 두 테이블의 새 버전 행으로 반영된다.

## Related Research

- thoughts/shared/research/2026-05-07-order-item-version-management.md
- thoughts/shared/plans/2026-05-07-order-edit-exchange-journey-docs.md

## Open Questions

- ORDER 타겟의 분배 결과를 "주문 단위 합산 표시"용으로 집계하는 별도 캐시/뷰가 존재하는지(현재 조사 범위에서는 발견되지 않음 — 모름).
