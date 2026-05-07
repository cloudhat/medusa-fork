# 06. 세금 계산

배송 주소·배송 방법이 확정된 후 장바구니에 세금 라인이 계산·저장되는 단계.

[← 여정 전체 목록](../README.md) | [다음: 07 결제 세션 생성](../07-결제세션-생성/README.md)

---

## 트리거 시점

세금 계산은 명시적 API 호출 없이 `refreshCartItemsWorkflow` 내에서 자동으로 수행된다.

| 상황 | 호출되는 세금 워크플로우 |
|------|------------------------|
| `force_refresh=true` (아이템 전체 재계산) | `updateTaxLinesWorkflow` |
| 특정 아이템·배송 방법만 갱신 | `upsertTaxLinesWorkflow` |
| 명시적 세금 계산 요청 | `POST /store/carts/:id/taxes` → `updateTaxLinesWorkflow` |

---

## [updateTaxLinesWorkflow](./flow-updateTaxLinesWorkflow.md) (전체 재계산)

**파일**: [packages/core/core-flows/src/cart/workflows/update-tax-lines.ts](../../../../packages/core/core-flows/src/cart/workflows/update-tax-lines.ts)

장바구니의 모든 라인 아이템과 배송 방법에 대한 세금 라인을 새로 덮어쓴다.

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | (조건) `useQueryGraphStep` | Query | cart 객체가 없을 때 cart_id로 장바구니 조회 |
| 2 | `validateCartStep` | — | 완료 여부 검증 |
| 3 | `acquireLockStep` | `LOCKING` | cart_id 락 (validateCartStep 이후에 획득) |
| 4 | `getItemTaxLinesStep` | `TAX` | 세금 라인 계산 |
| 5 | `getTranslatedTaxLinesStep` | — | locale 번역 |
| 6 | `setTaxLinesForItemsStep` | `CART` | 기존 세금 라인 전체 교체 (`setLineItemTaxLines`, `setShippingMethodTaxLines`) |
| 7 | `releaseLockStep` | `LOCKING` | 락 해제 |

---

## [upsertTaxLinesWorkflow](./flow-upsertTaxLinesWorkflow.md) (부분 갱신)

**파일**: [packages/core/core-flows/src/cart/workflows/upsert-tax-lines.ts](../../../../packages/core/core-flows/src/cart/workflows/upsert-tax-lines.ts)

지정된 아이템·배송 방법의 세금 라인만 upsert (기존 것은 유지).

Step 5에서 `setTaxLinesForItemsStep` 대신 `upsertTaxLinesForItemsStep`을 사용한다는 점만 다르다.

---

## getItemTaxLinesStep 내부 동작

**파일**: [packages/core/core-flows/src/tax/steps/get-item-tax-lines.ts](../../../../packages/core/core-flows/src/tax/steps/get-item-tax-lines.ts)

1. `force_tax_calculation || region.automatic_taxes`가 false → 계산 스킵
2. `shipping_address.country_code`가 없으면 계산 스킵
3. `Modules.TAX` resolve → `taxService.getTaxLines(items, context)` 호출
4. 선물 카드(`is_giftcard`) 아이템은 필터링하여 세금 미적용

---

## TaxModuleService.getTaxLines() 내부 동작

**파일**: [packages/modules/tax/src/services/tax-module-service.ts:408](../../../../packages/modules/tax/src/services/tax-module-service.ts)

1. `country_code` / `province_code`로 `TaxRegion` 조회
2. 국가 수준 TaxRegion이 없으면 빈 배열 반환
3. `TaxRate` 조회: `tax_region_id` 조건 + `is_default: true` 또는 해당 `product_id` / `product_type_id` / `shipping_option_id`에 매칭되는 규칙
4. `TaxRateRule` 우선순위: 특정 상품 규칙 > 상품 타입 규칙 > 기본 세율
5. 등록된 TaxProvider에 위임 (`provider.getTaxLines(...)`)

---

## Tax 모듈 엔티티

**파일**: [packages/modules/tax/src/models/](../../../../packages/modules/tax/src/models/)

| 엔티티 | 주요 필드 |
|--------|----------|
| `TaxRegion` | `country_code`, `province_code`, `provider` |
| `TaxRate` | `rate` (float), `code`, `name`, `is_default`, `is_combinable` |
| `TaxRateRule` | `reference` (product/product_type/shipping_option), `reference_id` |
| `TaxProvider` | 등록된 세금 계산 프로바이더 ID |

### TaxRegion 계층

```
TaxRegion (parent_id=null, country_code="kr")   ← 국가 수준
  └── TaxRegion (parent_id=..., province_code="gyeonggi")   ← 도/주 수준
```

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `TAX` | 세금 라인 계산 (TaxRegion + TaxRate 매칭, 프로바이더 위임) |
| `CART` | 계산된 세금 라인 저장 (`LineItemTaxLine`, `ShippingMethodTaxLine`) |
| `LOCKING` | 동시 수정 방지 |

---

## 세금 계산 순서 (refreshCartItems 기준)

`refreshCartItemsWorkflow` 내에서 세금 계산은 **프로모션 적용보다 먼저** 실행된다.

```
세금 계산 (updateTaxLines / upsertTaxLines)
  ↓
프로모션 재적용 (updateCartPromotions, action=REPLACE)
  ↓
결제 컬렉션 갱신 (refreshPaymentCollection)
```
