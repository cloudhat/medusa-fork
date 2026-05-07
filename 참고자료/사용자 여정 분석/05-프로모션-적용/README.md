# 05. 프로모션·할인 적용

사용자가 쿠폰 코드를 입력하거나 자동 프로모션이 장바구니에 적용되는 단계.

[← 여정 전체 목록](../README.md) | [다음: 06 세금 계산](../06-세금계산/README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `POST` | `/store/carts/:id/promotions` | `addPromotionToCartWorkflow` |
| `DELETE` | `/store/carts/:id/promotions` | `removePromotionsFromCartWorkflow` |

내부적으로 두 워크플로우 모두 `updateCartPromotionsWorkflow`를 action(`ADD` / `REMOVE` / `REPLACE`)으로 호출한다.

---

## updateCartPromotionsWorkflow

**파일**: [packages/core/core-flows/src/cart/workflows/update-cart-promotions.ts](../../../../packages/core/core-flows/src/cart/workflows/update-cart-promotions.ts)

### action 종류

| action | 의미 |
|--------|------|
| `ADD` | 기존 코드 유지 + 신규 코드 추가 |
| `REMOVE` | 기존 코드에서 해당 코드 제거 |
| `REPLACE` | 기존 코드 전부 제거 후 신규 코드로 대체 (`refreshCartItemsWorkflow`에서 사용) |

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `acquireLockStep` | `LOCKING` | cart_id 락 획득 |
| 2 | `validateCartStep` | — | 완료 여부 검증 |
| 3 | `getPromotionCodesToApply` | Query | 유효한 프로모션 코드 목록 결정 |
| 4 | `getActionsToComputeFromPromotionsStep` | `PROMOTION` | `promotionService.computeActions()` 호출 → 할인 액션 계산 |
| 5 | `prepareAdjustmentsFromPromotionActionsStep` | Query | 액션을 create/remove 목록으로 변환 |
| 6 | `parallelize` | — | 아래 5개 병렬 실행 |
| 6a | `removeLineItemAdjustmentsStep` | `CART` | 라인 아이템 기존 조정 소프트 삭제 |
| 6b | `removeShippingMethodAdjustmentsStep` | `CART` | 배송 방법 기존 조정 소프트 삭제 |
| 6c | `createLineItemAdjustmentsStep` | `CART` | 라인 아이템 신규 조정 생성 |
| 6d | `createShippingMethodAdjustmentsStep` | `CART` | 배송 방법 신규 조정 생성 |
| 6e | `updateCartPromotionsStep` | Link | Cart ↔ Promotion Remote Link 갱신 |
| 7 | `releaseLockStep` | `LOCKING` | 락 해제 |

---

## promotionService.computeActions() 동작

**파일**: [packages/modules/promotion/src/services/promotion-module.ts:631](../../../../packages/modules/promotion/src/services/promotion-module.ts)

1. 기존 조정(adjustment)에서 코드 수집 → 전부 REMOVE 액션으로 등록
2. `is_automatic: true` 프로모션도 자동 포함 (옵션으로 비활성화 가능)
3. `status: ACTIVE` + 캠페인 기간(`starts_at ≤ now < ends_at`) 조건 필터링
4. 각 프로모션에 대해:
   - 캠페인 예산 초과 여부 확인
   - `promotion.limit` 초과 여부 확인
   - 장바구니 컨텍스트에 대한 규칙(`PromotionRule`) 검증
   - `BUYGET` 타입 → `getComputedActionsForBuyGet()`
   - `STANDARD` + 아이템 타겟 → `getComputedActionsForItems()`
   - `STANDARD` + 배송 타겟 → `getComputedActionsForShippingMethods()`
5. 최종 반환: `ComputeActions[]` (`addItemAdjustment`, `removeItemAdjustment`, `addShippingMethodAdjustment`, ...)

---

## Promotion 모듈 엔티티

**파일**: [packages/modules/promotion/src/models/](../../../../packages/modules/promotion/src/models/)

| 엔티티 | 주요 필드 |
|--------|----------|
| `Promotion` | `code`, `is_automatic`, `type` (STANDARD/BUYGET), `status`, `limit`, `used` |
| `ApplicationMethod` | `value`, `type` (percentage/fixed/fixed_rate), `target_type` (items/order/shipping_methods), `allocation` |
| `Campaign` | `starts_at`, `ends_at`, `budget` |
| `CampaignBudget` | `type` (spend/usage/use_by_attribute), `limit`, `used` |
| `PromotionRule` | `attribute`, `operator`, `values` — 적용 조건 정의 |

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `PROMOTION` | 프로모션 코드 유효성 확인, 할인 액션 계산 (`computeActions`) |
| `CART` | LineItemAdjustment, ShippingMethodAdjustment 생성·삭제 |
| Link | Cart ↔ Promotion 연관 관계 관리 (`remoteLink.create/dismiss`) |
| `LOCKING` | 동시 수정 방지 |

주문 완료 시 `registerUsageStep`으로 `promotionModule.registerUsage()`가 호출되어 프로모션 사용 횟수·예산이 차감된다.
