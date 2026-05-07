# 02. 장바구니 생성 + 아이템 추가

사용자가 장바구니를 처음 만들고 상품을 담는 단계.

[← 여정 전체 목록](../README.md) | [다음: 03 고객식별·주소](../03-고객식별-주소입력/README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `POST` | `/store/carts` | [createCartWorkflow](./flow-createCartWorkflow.md) |
| `POST` | `/store/carts/:id/line-items` | [addToCartWorkflow](./flow-addToCartWorkflow.md) |
| `PUT` | `/store/carts/:id/line-items/:line_id` | [updateLineItemInCartWorkflow](./flow-updateLineItemInCartWorkflow.md) |
| `DELETE` | `/store/carts/:id/line-items/:line_id` | [deleteLineItemsWorkflow](./flow-deleteLineItemsWorkflow.md) |

---

## [createCartWorkflow](./flow-createCartWorkflow.md)

**파일**: [packages/core/core-flows/src/cart/workflows/create-carts.ts](../../../../packages/core/core-flows/src/cart/workflows/create-carts.ts)

### 입력

```typescript
{
  region_id?,
  sales_channel_id?,
  customer_id?,
  email?,
  currency_code?,
  items?: [{ variant_id, quantity, unit_price? }],
  promo_codes?,
  shipping_address?,
  locale?
}
```

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `parallelize` | — | 아래 3개 병렬 실행 |
| 1a | `findSalesChannelStep` | `SALES_CHANNEL`, `STORE` | 판매 채널 조회; 없으면 스토어 기본값 사용 |
| 1b | `findOneOrAnyRegionStep` | Query | 리전 조회; 없으면 스토어 default_region_id 폴백 |
| 1c | `findOrCreateCustomerStep` | `CUSTOMER` | 이메일로 고객 조회 또는 생성 |
| 2 | `validateSalesChannelStep` | — | 채널 유효성 검증 |
| 3 | `setPricingContext` (hook) | — | 가격 계산 컨텍스트 주입 (외부 커스터마이징 지점) |
| 4 | `getVariantsAndItemsWithPrices` | `PRICING`, Query | 변형 가격 계산 |
| 5 | `confirmVariantInventoryWorkflow` | `INVENTORY` | 재고 가용성 확인 |
| 6 | `getTranslatedLineItemsStep` | — | 로케일에 맞는 라인 아이템 번역 적용 |
| 7 | `createCartsStep` | `CART` | Cart 레코드 생성 |
| 8 | `updateTaxLinesWorkflow` | `TAX`, `CART` | 세금 라인 계산·저장 |
| 9 | `updateCartPromotionsWorkflow` | `PROMOTION`, `CART` | 초기 프로모션 적용 |
| 10 | `parallelize` | — | 아래 2개 병렬 실행 |
| 10a | `refreshPaymentCollectionForCartWorkflow` | `PAYMENT` | 결제 컬렉션 초기화 |
| 10b | `emitEventStep` | `EVENT_BUS` | `cart.created` 이벤트 발행 |

**보상**: `createCartsStep` 실패 시 → `service.deleteCarts(ids)` 자동 롤백

---

## [addToCartWorkflow](./flow-addToCartWorkflow.md)

**파일**: [packages/core/core-flows/src/cart/workflows/add-to-cart.ts](../../../../packages/core/core-flows/src/cart/workflows/add-to-cart.ts)

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `acquireLockStep` | `LOCKING` | cart_id 키로 락 획득 (timeout 2초, TTL 10초) |
| 2 | `useQueryGraphStep` | Query | 장바구니 전체 조회 |
| 3 | `validateCartStep` | — | completed_at 존재 시 에러 |
| 4 | `setPricingContext` (hook) | — | 가격 계산 컨텍스트 주입 |
| 5 | `when("should-calculate-prices")` → `getVariantsAndItemsWithPrices` | `PRICING`, Query | 변형 + 가격 계산 (가격 계산 필요 시에만) |
| 6 | `validateLineItemPricesStep` | — | 커스텀 단가 유효성 검증 |
| 7 | `getLineItemActionsStep` | `CART` | 기존 동일 variant 라인 아이템 조회 → create/update 분류 |
| 8 | `confirmVariantInventoryWorkflow` | `INVENTORY` | 재고 확인 |
| 9 | `getTranslatedLineItemsStep` | — | 로케일에 맞는 라인 아이템 번역 적용 |
| 10 | `parallelize` | — | 아래 2개 병렬 실행 |
| 10a | `createLineItemsStep` | `CART` | 신규 라인 아이템 생성 |
| 10b | `updateLineItemsStep` | `CART` | 기존 라인 아이템 수량 업데이트 |
| 11 | `refreshCartItemsWorkflow` | 여러 모듈 | 세금·프로모션·결제 컬렉션 재계산 (공통 서브워크플로우) |
| 12 | `parallelize` | `EVENT_BUS`, `LOCKING` | `emitEventStep` + `releaseLockStep` |

---

## [refreshCartItemsWorkflow](./flow-refreshCartItemsWorkflow.md) (공통 서브워크플로우)

**파일**: [packages/core/core-flows/src/cart/workflows/refresh-cart-items.ts](../../../../packages/core/core-flows/src/cart/workflows/refresh-cart-items.ts)

아이템 추가·수정·배송 방법 선택 후 항상 호출되는 재계산 워크플로우.

| 순번 | Step / Hook | 조건 | 주요 동작 |
|------|------------|------|----------|
| 1 | `acquireLockStep` | — | cart_id 락 (timeout 2초, TTL 10초) |
| 2 | `setPricingContext` (hook) | — | 가격 계산 컨텍스트 주입 |
| 3 | `when("force-refresh-calculate-prices")` | `force_refresh=true` | 가격 재계산 → `updateLineItemsStep` |
| 4 | `useQueryGraphStep` (refetch-cart) | — | 최신 장바구니 재조회 |
| 5 | `refreshCartShippingMethodsWorkflow` | — | 배송비 갱신 |
| 6 | `when("force-refresh-update-tax-lines")` | `force_refresh=true` | `updateTaxLinesWorkflow` (전체 세금 재계산) |
| 7 | `when("force-refresh-upsert-tax-lines")` | `!force_refresh && items/shipping_methods 있음` | `upsertTaxLinesWorkflow` (증분 세금 갱신) |
| 8 | `updateCartPromotionsWorkflow` | — | 프로모션 갱신 (`action=REPLACE`) |
| 9 | `when("should-update-item-translations")` | `locale` 지정 시 | `updateCartItemsTranslationsStep` (번역 갱신) |
| 10 | `beforeRefreshingPaymentCollection` (hook) | — | 결제 컬렉션 갱신 직전 커스터마이징 지점 |
| 11 | `refreshPaymentCollectionForCartWorkflow` | — | 결제 컬렉션 갱신 |
| 12 | `releaseLockStep` | — | cart_id 락 해제 |

---

## 개입 모듈 요약

| 모듈 | 역할 |
|------|------|
| `CART` | Cart, LineItem, Address, ShippingMethod, Adjustment, TaxLine 엔티티 관리 |
| `CUSTOMER` | 고객 조회·생성 |
| `SALES_CHANNEL` | 판매 채널 조회 |
| `PRICING` | 변형별 가격 계산 (PriceSet) |
| `INVENTORY` | 재고 가용성 확인 |
| `TAX` | 세금 라인 계산 |
| `PROMOTION` | 프로모션 코드 적용 |
| `PAYMENT` | 결제 컬렉션 초기화 |
| `LOCKING` | 동시 요청 직렬화 |

---

## Cart 엔티티 구조

**파일**: [packages/modules/cart/src/models/](../../../../packages/modules/cart/src/)

| 엔티티 | 주요 필드 |
|--------|----------|
| `Cart` | `region_id`, `customer_id`, `sales_channel_id`, `email`, `currency_code`, `locale`, `metadata`, `completed_at` |
| `LineItem` | `title`, `variant_id`, `quantity`, `unit_price`, `is_custom_price`, `is_discountable`, `is_giftcard`, `is_tax_inclusive`, `requires_shipping` |
| `Address` | `country_code`, `province`, `city`, `postal_code` |
| `ShippingMethod` | `shipping_option_id`, `amount`, `is_tax_inclusive` |
| `LineItemAdjustment` | `code`, `amount`, `promotion_id` |
| `LineItemTaxLine` | `code`, `rate`, `provider_id` |
