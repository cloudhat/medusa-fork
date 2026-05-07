# updateLineItemInCartWorkflow

장바구니의 특정 라인 아이템을 수정(수량·단가 변경)하는 워크플로우. 수량이 0이면 해당 아이템을 삭제로 처리한다.

[← 단계 README](./README.md)

**소스**: [packages/core/core-flows/src/cart/workflows/update-line-item-in-cart.ts](../../../../packages/core/core-flows/src/cart/workflows/update-line-item-in-cart.ts)
**호출 API**: `PUT /store/carts/:id/line-items/:line_id`

## 입력 / 출력

| 항목 | 타입 | 설명 |
|------|------|------|
| cart_id | string | 장바구니 ID |
| item_id | string | 수정할 라인 아이템 ID |
| update.quantity? | number | 새 수량 (0이면 삭제) |
| update.unit_price? | number | 커스텀 단가 |
| output | void | |

## Flowchart

```mermaid
flowchart TD
    Start([PUT /store/carts/:id/line-items/:line_id])

    subgraph Lock["🔒 cart_id lock (timeout 2s, TTL 10s)"]
        A["acquireLockStep"]
        B["useQueryGraphStep\n장바구니 전체 조회"]
        C["transform\n아이템 조회 및 variant_id 추출\n아이템 없으면 NOT_FOUND 에러"]
        D["validateCartStep\ncompleted_at 있으면 에러"]
        E(["validate (hook)\n커스텀 검증"])
        F(["setPricingContext (hook)\n가격 계산 컨텍스트 주입"])
        G{"should-remove-item\nquantity === 0?"}
        H[["deleteLineItemsWorkflow\n아이템 삭제"]]
        I{"should-fetch-variants\nvariant 존재 && 삭제 아닌 경우?"}
        J["useQueryGraphStep\nvariant 가격 조회"]
        K["validateVariantPricesStep\n가격 유효성 검증"]
        L[["confirmVariantInventoryWorkflow\n(INVENTORY) 재고 확인"]]
        M["updateLineItemsStepWithSelector\n(CART) 라인 아이템 업데이트"]
        N[["refreshCartItemsWorkflow\n세금·프로모션·결제 재계산"]]

        subgraph P1["parallelize"]
            O["releaseLockStep\n락 해제"]
            P["emitEventStep\ncart.updated 이벤트"]
        end
    end

    End([라인 아이템 수정 완료])

    Start --> A --> B --> C --> D --> E --> F --> G
    G -->|"true (quantity=0)"| H --> P1
    G -->|"false"| I
    I -->|"true"| J --> K --> L --> M --> N --> P1
    I -->|"false (커스텀 단가)"| M
    P1 --> End
```

## Step 설명

| 순번 | Step | 모듈 | 보상(rollback) |
|------|------|------|----------------|
| 1 | `acquireLockStep` | LOCKING | `releaseLockStep` |
| 2 | `useQueryGraphStep` | Query | 없음 |
| 3 | `transform` (아이템 조회) | — | 없음 |
| 4 | `validateCartStep` | — | 없음 |
| 5 | `validate` (hook) | — | 없음 |
| 6 | `setPricingContext` (hook) | — | 없음 |
| 7 | `deleteLineItemsWorkflow` | CART, LOCKING | 서브워크플로우 내부 보상 (조건부) |
| 8 | `useQueryGraphStep` (variants) | Query | 없음 (조건부) |
| 9 | `validateVariantPricesStep` | — | 없음 (조건부) |
| 10 | `confirmVariantInventoryWorkflow` | INVENTORY | 없음 (조건부) |
| 11 | `updateLineItemsStepWithSelector` | CART | 이전 값으로 복원 |
| 12 | `refreshCartItemsWorkflow` | 여러 모듈 | 서브워크플로우 내부 보상 |
| 13a | `releaseLockStep` | LOCKING | 없음 |
| 13b | `emitEventStep` | EVENT_BUS | 없음 |

## 보상(Compensation) 흐름

- **수량 0 분기**: `deleteLineItemsWorkflow`가 자체 보상 로직 처리.
- **`updateLineItemsStepWithSelector` 실패**: CART 모듈이 이전 라인 아이템 상태로 복원.
- 락은 성공/실패 무관하게 `releaseLockStep`으로 해제.

## 호출하는 서브워크플로우

- [deleteLineItemsWorkflow](./flow-deleteLineItemsWorkflow.md) — 수량 0일 때 아이템 삭제 처리
- [refreshCartItemsWorkflow](./flow-refreshCartItemsWorkflow.md) — 세금·프로모션·결제 컬렉션 재계산
- [confirmVariantInventoryWorkflow](./flow-addToCartWorkflow.md) — 재고 확인
