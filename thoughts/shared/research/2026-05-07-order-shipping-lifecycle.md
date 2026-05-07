---
date: 2026-05-07T00:00:00+09:00
researcher: SAN KIM
git_commit: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
branch: develop
repository: medusa-fork
topic: "OrderShippingMethod, OrderShippingMethodAdjustment, OrderShipping, OrderLineItem 라이프사이클 연관 관계"
tags: [research, order, shipping-method, line-item, lifecycle, rma]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
---

# Research: OrderShippingMethod · OrderShipping · OrderShippingMethodAdjustment · OrderLineItem 라이프사이클 연관 관계

**Date**: 2026-05-07 KST  
**Researcher**: SAN KIM  
**Git Commit**: `1c0e69e9cb59b5954175bbcd8b7e382aae127dea`  
**Branch**: develop

## Research Question

`OrderShippingMethod`, `OrderShippingMethodAdjustment`, `OrderShipping`, `OrderLineItem`을 라이프사이클 관점에서 어떤 연관이 있는지. 상품 단위로 다른 배송비가 적용 가능한 구조인지.

## Summary

배송 방법(OrderShippingMethod)과 상품(OrderLineItem)은 **모델 수준에서 직접 연결되지 않는다.** 두 그래프는 `Order`를 공통 부모로 가지며 독립적으로 분기한다. 상품별 배송비 분기는 `ShippingProfile` ID 일치 검증을 통한 간접 매핑으로만 이루어지며, `FulfillmentItem.line_item_id`에서 최초로 실물 연결이 기록된다.

배송 방법은 `OrderShipping`(버전·맥락 래퍼) + `OrderShippingMethod`(실제 배송 데이터) 2단 구조로 저장된다. `OrderShippingMethodAdjustment`는 배송비에 적용된 프로모션 할인 스냅샷이다.

---

## Detailed Findings

### 1. 엔티티 역할 정의

| 엔티티 | prefix | 역할 |
|---|---|---|
| `OrderShippingMethod` | `ordsm_` | 배송비 금액·이름·옵션 정보를 저장하는 순수 데이터 레코드 |
| `OrderShipping` | `ordspmv_` | `OrderShippingMethod`를 Order/Return/Exchange/Claim에 연결하는 버전 관리 래퍼 |
| `OrderShippingMethodAdjustment` | `ordsmadj_` | 배송비에 적용된 프로모션 할인 스냅샷 |
| `OrderLineItem` | `ordli_` | 주문 시점 상품 카탈로그 데이터를 비정규화한 불변 스냅샷 |
| `OrderItem` | `orditem_` | `OrderLineItem`을 참조하며 버전별 수량 상태를 추적 |

---

### 2. 엔티티 관계 구조

```
Order
├── items (hasMany) ──────────────────────────────────────────────────────┐
│   └── OrderItem (order_id FK)                                           │
│       └── item (hasOne, item_id FK) → OrderLineItem (스냅샷)            │
│           ├── OrderLineItemTaxLine (세율 스냅샷)                         │
│           └── OrderLineItemAdjustment (상품 할인 스냅샷)                 │
│                                                                          │
└── shipping_methods (hasMany) ────────────────────────────────────────── │
    └── OrderShipping (order_id FK, version 포함)                         │
        ├── return_id (nullable)                                           │
        ├── exchange_id (nullable)                                         │
        ├── claim_id (nullable)                                            │
        └── shipping_method (hasOne, shipping_method_id FK)               │
            → OrderShippingMethod                                          │
                ├── OrderShippingMethodTaxLine (세율 스냅샷)               │
                └── OrderShippingMethodAdjustment (배송 할인 스냅샷)       │
                                                                           │
                    ←── 두 그래프는 여기서 만나지 않는다 ────────────────────┘
```

**사실**: `OrderShippingMethod`, `OrderShipping`, `OrderItem`, `OrderLineItem` 중 어느 모델에도 상대방을 가리키는 FK나 관계 데코레이터가 없다.

**참고 파일**:
- [packages/modules/order/src/models/shipping-method.ts](packages/modules/order/src/models/shipping-method.ts)
- [packages/modules/order/src/models/order-shipping-method.ts](packages/modules/order/src/models/order-shipping-method.ts)
- [packages/modules/order/src/models/line-item.ts](packages/modules/order/src/models/line-item.ts)
- [packages/modules/order/src/models/order-item.ts](packages/modules/order/src/models/order-item.ts)

---

### 3. OrderShippingMethodAdjustment 역할

`OrderShippingMethodAdjustment`는 배송비에 적용된 프로모션 할인 1건을 저장한다.

- `shipping_method_id` FK로 `OrderShippingMethod`에 귀속
- `version` 필드: 어느 OrderChange 버전의 조정인지 추적. `(version, shipping_method_id)` 복합 유니크 제약이 있어 같은 버전에 중복 조정이 생성되지 않는다
- `promotion_id`, `code`, `amount`, `provider_id` 필드로 프로모션 출처 추적
- Cart 단계에서 프로모션이 배송비에 적용된 경우, 주문 생성 시 `prepareAdjustmentsData()` 함수로 변환되어 `OrderShippingMethod`와 함께 일괄 생성된다

**참고 파일**: [packages/modules/order/src/models/shipping-method-adjustment.ts](packages/modules/order/src/models/shipping-method-adjustment.ts)

---

### 4. OrderShipping의 다중 소유 패턴

`OrderShipping`은 4가지 맥락 중 하나에 귀속된다.

| 필드 | 값 있음 | 의미 |
|---|---|---|
| `order_id` 만 | return/exchange/claim_id 모두 null | 일반 주문 배송 방법 |
| `return_id` 설정 | - | 반품 발송 배송 방법 |
| `exchange_id` 설정 | - | 교환 발송 배송 방법 |
| `claim_id` 설정 | - | 클레임 발송 배송 방법 |

- `order_id`는 항상 필수. 어느 주문에 속하는지 기록
- `version` 필드로 OrderChange 버전별 배송 방법 이력 추적

**참고 파일**: [packages/modules/order/src/models/order-shipping-method.ts](packages/modules/order/src/models/order-shipping-method.ts)

---

### 5. 라이프사이클: 생성 흐름

#### 5-A. 주문 생성 시 (Cart → Order)

Cart 완료(`completeCartWorkflow`) 시 Cart의 `shipping_methods` 배열이 Order용으로 변환된다.

```typescript
// packages/core/core-flows/src/cart/workflows/complete-cart.ts:417-429
const shippingMethods = (cart.shipping_methods ?? []).map((sm) => {
  return {
    name: sm.name,
    description: sm.description,
    amount: sm.raw_amount ?? sm.amount,
    is_tax_inclusive: sm.is_tax_inclusive,
    shipping_option_id: sm.shipping_option_id,
    data: sm.data,
    metadata: sm.metadata,
    tax_lines: prepareTaxLinesData(sm.tax_lines ?? []),
    adjustments: prepareAdjustmentsData(sm.adjustments ?? []),
  }
})
```

이 데이터는 `createOrdersStep`으로 전달되고, OrderModule 서비스 내부에서 `{ shipping_method: { ...sm } }` 형태로 감싸 `OrderShipping` + `OrderShippingMethod` 2단 구조로 저장된다.

```typescript
// packages/modules/order/src/services/order-module-service.ts:770-776
const shippingMethods = shipping_methods?.map((sm: any) => {
  return { shipping_method: { ...sm } }
})
ord.shipping_methods = shippingMethods
```

**사실**: 이 변환에서 `item_id` 또는 `line_item_id` 필드는 존재하지 않는다.

#### 5-B. RMA 배송 방법 생성 (공통 패턴)

반품·교환·클레임·주문수정 시 배송 방법은 동일한 3단계 패턴으로 생성된다.

1. `prepareShippingMethod(relatedEntityField?)` 유틸로 DTO 구성
2. `createOrderShippingMethods` 스텝으로 `OrderShippingMethod` 생성
3. `createOrderChangeActionsWorkflow`로 `OrderChangeAction(SHIPPING_ADD)` 등록

```typescript
// packages/core/core-flows/src/order/utils/prepare-shipping-method.ts:4-36
const obj = {
  shipping_option_id: option.id,
  amount: isCustomPrice ? data.customPrice : option.calculated_price.calculated_amount,
  is_custom_amount: isCustomPrice,
  is_tax_inclusive: ...,
  data: option.data ?? {},
  name: option.name,
  version: orderChange.version,
  order_id: data.relatedEntity.order_id,
  // return_id / claim_id / exchange_id: relatedEntityField에 따라 조건부 설정
}
```

**사실**: `obj`에 `line_item_id` 또는 `item_id` 필드가 없다.

---

### 6. 라이프사이클: 삭제 흐름

삭제는 `OrderChangeAction`을 키로 역추적하여 소프트 삭제한다.

1. OrderChange에서 `action_id`로 `OrderChangeAction` 조회
2. `action.action === SHIPPING_ADD` 검증
3. `associatedAction.reference_id`로 `OrderShippingMethod` ID 획득
4. `deleteOrderChangeActionsStep` + `deleteOrderShippingMethods` 병렬 실행 (소프트 삭제)

보상 함수에서는 `restoreOrderShippingMethods`로 복원.

---

### 7. 상품별 배송비 적용 구조 분석

#### 7-A. 현재 구조

배송 방법은 주문 전체(또는 반품·교환·클레임 단위)에 적용되며, 개별 상품(OrderLineItem) 단위로 다른 배송비를 직접 매핑하는 FK 구조는 존재하지 않는다.

#### 7-B. ShippingProfile을 통한 간접 매핑

상품과 배송 방법 간의 연결은 `ShippingProfile`을 통한 검증 계층에서만 이루어진다.

- `Product.shipping_profile.id` ↔ `ShippingOption.shipping_profile_id` 일치 여부를 Cart 완료 시 검증

```typescript
// packages/core/core-flows/src/cart/steps/validate-shipping.ts:78-110
const optionProfileMap = new Map(
  shippingOptions.map((option) => [option.id, option.shipping_profile_id])
)
const requiredShippingPorfiles = cartItemsWithShipping.map(
  (item) => item.variant.product?.shipping_profile?.id
)
const availableShippingPorfiles = cartShippingMethods.map((method) =>
  optionProfileMap.get(method.shipping_option_id!)
)
// missingShippingPorfiles가 있으면 오류 발생
```

- Fulfillment 생성 시에도 같은 ShippingProfile 일치 검증이 재수행된다

```typescript
// packages/core/core-flows/src/order/workflows/create-fulfillment.ts:183-192
if (
  orderItem.requires_shipping &&
  orderItem.variant?.product?.shipping_profile?.id !==
    shippingOption.shipping_profile_id
) {
  throw new MedusaError(...)
}
```

#### 7-C. Fulfillment 생성 시 최초 연결

`line_item_id`가 ShippingMethod와 연결되는 지점은 `FulfillmentItem` 생성 시점이 유일하다.

```typescript
// packages/modules/fulfillment/src/models/fulfillment-item.ts:6-27
export const FulfillmentItem = model.define("fulfillment_item", {
  id: model.id({ prefix: "fulit" }).primaryKey(),
  line_item_id: model.text().nullable(),   // 이 시점에 처음으로 기록됨
  fulfillment: model.belongsTo(() => Fulfillment, { mappedBy: "items" }),
})
```

`Fulfillment`는 `ShippingOption`과 연결되고, `ShippingOption`은 `ShippingProfile`과 연결된다. 따라서 `FulfillmentItem → Fulfillment → ShippingOption → ShippingProfile`의 경로로 간접 추적은 가능하다.

---

### 8. 전체 흐름 다이어그램

```
[Cart 단계]
Product.shipping_profile_id ──┐
                              ↓ 검증(validate-shipping)
ShippingOption.shipping_profile_id
        ↓ 선택
Cart.ShippingMethod (casm_*)
        ↓ complete-cart 변환 (item_id 없이 변환됨)
[주문 생성]
OrderShipping (ordspmv_*)  ←── version, return/exchange/claim_id
    └── OrderShippingMethod (ordsm_*)
        ├── amount, name, shipping_option_id
        ├── OrderShippingMethodTaxLine (세율 스냅샷)
        └── OrderShippingMethodAdjustment (프로모션 할인 스냅샷, version 별 unique)

[별개 트리]
Order → OrderItem → OrderLineItem (상품 스냅샷)

[Fulfillment 생성]
FulfillmentItem.line_item_id ← OrderLineItem.id  (최초 연결점)
FulfillmentItem → Fulfillment → ShippingOption → ShippingProfile
```

---

## Code References

- [packages/modules/order/src/models/shipping-method.ts](packages/modules/order/src/models/shipping-method.ts) — `OrderShippingMethod` 엔티티
- [packages/modules/order/src/models/order-shipping-method.ts](packages/modules/order/src/models/order-shipping-method.ts) — `OrderShipping` 엔티티 (pivot)
- [packages/modules/order/src/models/shipping-method-adjustment.ts](packages/modules/order/src/models/shipping-method-adjustment.ts) — `OrderShippingMethodAdjustment` 엔티티
- [packages/modules/order/src/models/line-item.ts](packages/modules/order/src/models/line-item.ts) — `OrderLineItem` 엔티티
- [packages/modules/order/src/models/order-item.ts](packages/modules/order/src/models/order-item.ts) — `OrderItem` 엔티티
- [packages/core/core-flows/src/cart/workflows/complete-cart.ts:417-429](packages/core/core-flows/src/cart/workflows/complete-cart.ts) — Cart→Order ShippingMethod 변환
- [packages/modules/order/src/services/order-module-service.ts:770-776](packages/modules/order/src/services/order-module-service.ts) — 2단 구조 저장
- [packages/core/core-flows/src/order/utils/prepare-shipping-method.ts](packages/core/core-flows/src/order/utils/prepare-shipping-method.ts) — RMA 배송 방법 DTO 구성 유틸
- [packages/core/core-flows/src/order/steps/create-order-shipping-methods.ts](packages/core/core-flows/src/order/steps/create-order-shipping-methods.ts) — 생성 스텝
- [packages/core/core-flows/src/order/steps/delete-order-shipping-methods.ts](packages/core/core-flows/src/order/steps/delete-order-shipping-methods.ts) — 삭제 스텝
- [packages/core/core-flows/src/cart/steps/validate-shipping.ts:78-110](packages/core/core-flows/src/cart/steps/validate-shipping.ts) — ShippingProfile 검증
- [packages/core/core-flows/src/order/workflows/create-fulfillment.ts:183-192](packages/core/core-flows/src/order/workflows/create-fulfillment.ts) — Fulfillment 생성 시 ShippingProfile 재검증
- [packages/modules/fulfillment/src/models/fulfillment-item.ts](packages/modules/fulfillment/src/models/fulfillment-item.ts) — `FulfillmentItem.line_item_id` (최초 연결점)

## Related Research

- [2026-05-07-order-fulfillment-domain-connection.md](2026-05-07-order-fulfillment-domain-connection.md)
- [2026-05-07-order-line-item-order-item-return-item-lifecycle.md](2026-05-07-order-line-item-order-item-return-item-lifecycle.md)

## Open Questions

- Cart 모듈에서 `addShippingMethodToCartStep` 이전에 `removeShippingMethodFromCartStep`이 항상 실행되는데, 이는 하나의 Cart에 동시에 여러 ShippingMethod가 공존할 수 없는 설계를 의도한 것인지, 아니면 업데이트 패턴의 편의를 위한 것인지 추가 확인 필요.
- `ShippingProfile` 기반 검증이 Fulfillment 생성 시 재수행되는 이유가 중복 방어인지, 다른 데이터 경로에서 Fulfillment가 생성될 수 있기 때문인지 확인 필요.
