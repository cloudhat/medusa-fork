# 04. 배송 옵션 조회·선택

사용자가 배송 방법 목록을 보고 하나를 선택하는 단계.

[← 여정 전체 목록](../README.md) | [다음: 05 프로모션 적용](../05-프로모션-적용/README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `GET` | `/store/shipping-options` | `listShippingOptionsForCartWorkflow` |
| `POST` | `/store/carts/:id/shipping-methods` | `addShippingMethodToCartWorkflow` |

---

## listShippingOptionsForCartWorkflow (목록 조회)

**파일**: [packages/core/core-flows/src/cart/workflows/list-shipping-options-for-cart.ts](../../../../packages/core/core-flows/src/cart/workflows/list-shipping-options-for-cart.ts)

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `useQueryGraphStep` | Query | 장바구니 조회 (item.variant.inventory_items까지 포함) |
| 2 | `validatePresenceOfStep` | — | sales_channel_id, region_id, currency_code 존재 확인 |
| 3 | `useQueryGraphStep` | Query | SalesChannel → StockLocation → FulfillmentSet ID 탐색 (캐시 활성화) |
| 4 | `useRemoteQueryStep` | Remote Query | `shipping_options` 엔티티 조회. `calculated_price.*`, `rules.*` 포함 |
| 5 | `getTranslatedShippingOptionsStep` | — | locale 번역 |

**조회 필터 구성**:
- `fulfillment_set_id`: SalesChannel → StockLocation → FulfillmentSet 경로로 추출
- `address`: 장바구니의 `shipping_address` (country_code, province, city, postal_code) → GeoZone 매칭
- `calculated_price.context`: currency_code, region_id, customer_id

반환 값에 `insufficient_inventory` 플래그가 포함되어 재고 부족 옵션을 표시할 수 있다.

---

## addShippingMethodToCartWorkflow (배송 방법 선택)

**파일**: [packages/core/core-flows/src/cart/workflows/add-shipping-method-to-cart.ts](../../../../packages/core/core-flows/src/cart/workflows/add-shipping-method-to-cart.ts)

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `acquireLockStep` | `LOCKING` | cart_id 락 획득 |
| 2 | `useRemoteQueryStep` | Remote Query | 장바구니 조회 |
| 3 | `validateCartStep` | — | 완료 여부 검증 |
| 4 | `validate` (hook) | — | 커스텀 검증 지점 |
| 5 | `listShippingOptionsForCartWithPricingWorkflow` | `FULFILLMENT`, `PRICING` | 선택 옵션의 가격 계산된 배송 옵션 목록 조회 |
| 6 | `validateCartShippingOptionsStep` | `FULFILLMENT` | 옵션 유효성 검증 |
| 7 | `validateCartShippingOptionsPriceStep` | — | 가격 존재 여부 검증 |
| 8 | `validateAndReturnShippingMethodsDataStep` | `FULFILLMENT` | 배송 프로바이더 측 data 검증 |
| 9 | `parallelize` | — | 아래 2개 병렬 실행 |
| 9a | `removeShippingMethodFromCartStep` | `CART` | 기존 배송 방법 소프트 삭제 |
| 9b | `addShippingMethodToCartStep` | `CART` | 새 배송 방법 추가 |
| 10 | `refreshCartItemsWorkflow` | 여러 모듈 | 세금·프로모션·결제 컬렉션 재계산 |
| 11 | `parallelize` | `EVENT_BUS`, `LOCKING` | `emitEventStep` + `releaseLockStep` 병렬 실행 |

**주의**: 기존 배송 방법은 새 배송 방법 추가 시 소프트 삭제된다 (분할 배송 미지원).

### 가격 타입별 처리 (flat vs calculated)

`listShippingOptionsForCartWithPricingWorkflow` 내부에서 `price_type`에 따라 분기된다.

| 타입 | 처리 방식 |
|------|----------|
| `flat` | Pricing 모듈의 PriceSet에서 `calculated_price` 직접 조회 |
| `calculated` | `calculateShippingOptionsPricesStep` → `Modules.FULFILLMENT`의 프로바이더 가격 계산 API 호출 |

---

## Fulfillment 모듈 배송 옵션 구조

**파일**: [packages/modules/fulfillment/src/models/](../../../../packages/modules/fulfillment/src/models/)

```
FulfillmentSet (fuset_...)
  └── ServiceZone (serzo_...)    ← 서비스 가능 지역
        ├── GeoZone              ← country_code, province, city, postal_code 조건
        └── ShippingOption (so_...)
              ├── price_type (flat | calculated)
              ├── ShippingProfile  ← 상품 배송 프로파일
              ├── FulfillmentProvider
              └── ShippingOptionRule  ← 적용 조건 규칙
```

**SalesChannel ↔ FulfillmentSet 연결**: Remote Link (`sales_channel_location`, `location_fulfillment_set`)로 관리된다.

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `CART` | 배송 방법 추가·삭제 |
| `FULFILLMENT` | 배송 옵션 조회, 프로바이더 데이터 검증, 가격 계산 |
| `PRICING` | flat 타입 배송비 가격 조회 |
| `LOCKING` | 동시 수정 방지 |
