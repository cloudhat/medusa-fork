---
date: 2026-05-07T00:00:00+09:00
researcher: SAN KIM
git_commit: ca8b37ab641e8f9cfb7130e8d68b33547c6abd7d
branch: develop
repository: medusa-fork
topic: "confirmReturnReceiveWorkflow에서 반품 시 buy_rules_min_quantity 재계산 여부"
tags: [research, codebase, return, promotion, buy-get, confirmReturnReceiveWorkflow, buy_rules_min_quantity]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
---

# Research: confirmReturnReceiveWorkflow에서 반품 시 buy_rules_min_quantity 재계산 여부

**Date**: 2026-05-07 KST  
**Researcher**: SAN KIM  
**Git Commit**: ca8b37ab641e8f9cfb7130e8d68b33547c6abd7d  
**Branch**: develop  
**Repository**: medusa-fork

## Research Question

`confirmReturnReceiveWorkflow` 실행 시 `ApplicationMethod.buy_rules_min_quantity` 조건이 더 이상 충족되지 않는 경우(예: 3개 구매 후 1개 반품 → 조건 미달) 할인이 재계산·취소되는지 여부를 코드 레벨에서 확인한다.

**엣지 케이스**: `buy_rules_min_quantity = 3`, 상품 3개 구매 후 1개를 반품했을 때 할인이 어떻게 처리되는가?

## Summary

**사실**: `confirmReturnReceiveWorkflow`는 반품 확정 시 프로모션 조건(buy_rules_min_quantity 포함)을 재평가하는 코드를 포함하지 않는다. 원주문에 적용된 LineItem adjustment(할인)는 그대로 유지되고, 환불 금액은 반품 아이템의 `unit_price × 수량`을 기준으로 산정된다.

**결론 (엣지 케이스)**: `buy_rules_min_quantity = 3` 조건으로 3개 구매 시 할인이 적용된 상태에서 1개를 반품하면, 남은 2개에 대한 할인이 자동으로 취소·감소되지 않는다. 원주문의 adjustment는 DB에 그대로 유지되며, 반품 아이템 1개분의 `unit_price`만큼이 환불 대상 금액으로 계산된다.

## Detailed Findings

### 1. confirmReturnReceiveWorkflow 스텝 구성

파일: [confirm-receive-return-request.ts](packages/core/core-flows/src/order/workflows/return/confirm-receive-return-request.ts)

워크플로우가 실행하는 스텝 목록:

| 스텝 | 모듈 | 동작 |
|------|------|------|
| `useRemoteQueryStep` (×3) | Remote Query | return, order, orderChange 조회 |
| `confirmReceiveReturnValidationStep` | — | 취소 여부 및 OrderChange 활성 상태 확인 |
| `updateReturnsStep` | ORDER | Return 상태 업데이트 (RECEIVED/PARTIALLY_RECEIVED) |
| `updateReturnItemsStep` | ORDER | received_quantity, damaged_quantity 업데이트 |
| `confirmOrderChanges` | ORDER | OrderChange 확정 |
| `adjustInventoryLevelsStep` | INVENTORY | 재고 복원 (+n) |
| `createOrUpdateOrderPaymentCollectionWorkflow` | PAYMENT | 결제 컬렉션 갱신 |
| `emitEventStep` | — | `order.return_received` 이벤트 발행 |

위 스텝 중 프로모션 모듈(`Modules.PROMOTION`)을 호출하거나 `buy_rules_min_quantity`를 참조하는 스텝은 없다.

### 2. confirmOrderChanges — adjustment 재계산 여부

파일: `packages/core/core-flows/src/order/steps/confirm-order-changes.ts`  
서비스: `packages/modules/order/src/services/order-module-service.ts`

호출 체인:
```
confirmOrderChanges (step)
  └─ orderModuleService.confirmOrderChange()         [line 2792]
       └─ confirmOrderChange_()                       [line 2811]
            ├─ orderChangeService_.update(CONFIRMED)  [line 2841]
            └─ applyOrderChanges_(actions)            [line 2847]
                 └─ applyChangesToOrder()
                      └─ adjustment 복사 (amount 그대로)
```

`applyChangesToOrder` 내 adjustment 처리 코드 (`packages/modules/order/src/utils/apply-order-changes.ts:103-115`):

```typescript
if (version > order.version) {
  item.adjustments?.forEach((adjustment) => {
    lineItemAdjustmentsToCreate.push({
      item_id: itemId,
      version,
      amount: adjustment.amount,          // 기존 amount를 그대로 복사
      description: adjustment.description,
      promotion_id: adjustment.promotion_id,
      code: adjustment.code,
      is_tax_inclusive: adjustment.is_tax_inclusive,
    })
  })
}
```

`amount`를 재계산하는 코드가 없다. 기존 adjustment 값을 새 버전으로 복사하는 것이 전부다.

`RECEIVE_RETURN_ITEM` action type의 operation (`packages/modules/order/src/utils/actions/receive-return-item.ts:9-69`) 은 다음만 수행한다:
- `detail.return_received_quantity` 증가
- `detail.return_requested_quantity` 감소
- `unit_price × quantity`를 반환 금액으로 계산

adjustment 필드를 읽거나 쓰는 코드가 없다.

### 3. buy_rules_min_quantity — 평가 시점

파일: `packages/modules/promotion/src/utils/compute-actions/buy-get.ts`

`buy_rules_min_quantity`는 `isValidPromotionContext` 함수(line 28-55)와 `normalizePromotionApplicationConfiguration` 함수(line 57-77)에서만 읽힌다.

```typescript
// buy-get.ts:43-54
const minimumBuyQuantity = MathBN.convert(
  promotion.application_method?.buy_rules_min_quantity ?? 0
)

if (MathBN.lte(minimumBuyQuantity, 0) || !promotion.application_method?.buy_rules?.length) {
  return false
}
```

이 함수들은 `computeActions` 진입 시점에 호출된다. `computeActions`는 장바구니 생성·수정 흐름에서 프로모션을 처음 적용할 때 실행된다. 반품 워크플로우에서는 호출되지 않는다.

### 4. 반품 흐름에서 promotionAdjustments 재계산 시도 여부

`packages/core/core-flows/src/order/workflows/return/` 내 21개 파일 전체를 확인한 결과:

- `promotion`, `@medusajs/promotion`, `computeAdjustmentsForPreview`, `getActionsToComputeFromPromotions` 를 import하는 파일이 하나도 없다.
- `revertLineItemActions`, `revertLineItemAdjustments` 유사 스텝이 정의되거나 호출되지 않는다.

`computeAdjustmentsForPreviewWorkflow`는 코드베이스에 존재하지만, 이 워크플로우를 사용하는 파일 목록:

| 파일 | 흐름 |
|------|------|
| `on-carry-promotions-flag-set.ts` | order edit |
| `exchange/update-exchange-add-item.ts` | exchange |
| `exchange/exchange-add-new-item.ts` | exchange |
| `order-edit/order-edit-add-new-item.ts` | order edit |
| `order-edit/update-order-edit-item-quantity.ts` | order edit |
| (등 order edit / exchange / claim 관련) | — |

반품(`return/`) 폴더의 어떤 파일도 이 워크플로우를 호출하지 않는다.

### 5. createOrUpdateOrderPaymentCollectionWorkflow — 금액 기준

파일: `packages/core/core-flows/src/order/workflows/create-or-update-order-payment-collection.ts:111-124`

```typescript
const amountPending = transform({ order, input }, ({ order, input }) => {
  const amountPending =
    order.summary.raw_pending_difference ?? order.summary.pending_difference
  // ...
  return amountPending
})
```

사용하는 금액 기준: `order.summary.pending_difference = order.total - 처리된 transaction 합계`

`order.total`은 원주문 생성 시 적용된 adjustment(할인)가 반영된 값이다. 이 워크플로우는 프로모션 모듈을 호출하지 않고, DB에 저장된 `pending_difference`를 그대로 사용한다.

### 6. 프로모션 모듈 — 반품 이벤트 구독 여부

`packages/modules/promotion/src/` 내에 `subscribers` 폴더가 존재하지 않는다. `packages/modules/promotion/src/index.ts`는 `PromotionModuleService`만 export하며, 이벤트 구독 코드가 없다.

`order.return_requested`(line 213)와 `order.return_received`(line 225)는 `packages/core/utils/src/core-flows/events.ts`에 정의되어 있고, `emitEventStep`으로 발행되지만, 프로모션 모듈 측에 이를 수신하는 subscriber가 없다.

## 엣지 케이스 시뮬레이션

**시나리오**: `buy_rules_min_quantity = 3`, 상품 A를 3개 주문, 구매 총액 9,000원, 적용 할인 3,000원 (각 아이템에 -1,000원 adjustment)

### 반품 전 OrderLineItem 상태

| item | unit_price | quantity | adjustment | line_total |
|------|-----------|---------|------------|-----------|
| A-1  | 3,000     | 1       | -1,000     | 2,000     |
| A-2  | 3,000     | 1       | -1,000     | 2,000     |
| A-3  | 3,000     | 1       | -1,000     | 2,000     |
| **합계** | — | — | -3,000 | **6,000** |

### 1개 반품 후 confirmReturnReceiveWorkflow 실행 결과

1. `RECEIVE_RETURN_ITEM` action: `unit_price × 1 = 3,000`원을 환불 대상 금액으로 계산
2. `confirmOrderChanges`: A-1의 adjustment(-1,000)를 그대로 새 버전으로 복사 (재계산 없음)
3. `adjustInventoryLevelsStep`: 재고 +1
4. `createOrUpdateOrderPaymentCollectionWorkflow`: `pending_difference`(= 남은 미수금) 기준으로 결제 컬렉션 갱신

**결과**: A-2, A-3에 남아있는 각 -1,000원 adjustment는 자동으로 취소되지 않는다. `buy_rules_min_quantity = 3` 조건을 충족하지 못하게 되었음에도 원주문의 할인 adjustment는 DB에 그대로 유지된다.

환불 금액 산정은 반품 아이템의 `unit_price`(3,000원)만 기준으로 하며, 해당 아이템에 적용됐던 adjustment(-1,000원)가 환불 금액에서 차감되는지 여부는 `RECEIVE_RETURN_ITEM` operation 코드에 따라 결정된다.

> **추정(미확인)**: `RECEIVE_RETURN_ITEM` operation(`receive-return-item.ts:32`)이 `unit_price × quantity`를 반환하는데, 이것이 adjustment 적용 전인지 후인지는 환불 금액 최종 산정 로직(`createOrUpdateOrderPaymentCollectionWorkflow`에서의 `pending_difference`)에 따라 달라진다. 이 부분은 현재 데이터로는 단정할 수 없으며 추가 조사가 필요하다.

## Code References

- [confirm-receive-return-request.ts](packages/core/core-flows/src/order/workflows/return/confirm-receive-return-request.ts) — 워크플로우 전체 정의
- `packages/modules/order/src/utils/apply-order-changes.ts:103-115` — adjustment 복사 로직
- `packages/modules/order/src/utils/actions/receive-return-item.ts:9-69` — RECEIVE_RETURN_ITEM operation
- `packages/modules/promotion/src/utils/compute-actions/buy-get.ts:28-77` — buy_rules_min_quantity 평가 함수
- `packages/core/core-flows/src/order/workflows/create-or-update-order-payment-collection.ts:111-124` — 결제 컬렉션 금액 기준
- `packages/core/utils/src/core-flows/events.ts:213,225` — return 이벤트 정의

## Architecture Documentation

`confirmReturnReceiveWorkflow`가 실행되는 시점에 프로모션 관련 로직이 개입하는 경로는 코드베이스에 존재하지 않는다. 프로모션 적용은 장바구니/주문 생성 시 `computeActions → applyPromotions` 경로에서 1회 수행되고, 그 결과인 LineItemAdjustment 레코드가 DB에 저장된다. 이후 주문 변경(반품, 교환 등)이 발생해도 이 adjustment는 `applyChangesToOrder`가 새 버전으로 복사할 뿐 금액을 재산출하지 않는다.

프로모션 재계산(`computeAdjustmentsForPreviewWorkflow`)은 order edit과 exchange 흐름에서만 명시적으로 호출된다.

## Open Questions

1. `RECEIVE_RETURN_ITEM` operation이 반환하는 금액이 adjustment 적용 전(unit_price) 기준인지, 적용 후 기준인지 `refundPaymentWorkflow`와의 연결 흐름에서 추가 확인 필요
2. 커스터마이징 시 반품 후 프로모션을 재평가하려면 `confirmReturnReceiveWorkflow`의 hook 또는 subscriber에서 `computeAdjustmentsForPreviewWorkflow`를 호출해야 하는지 구조적 확인 필요
