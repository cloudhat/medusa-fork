# orderEditUpdateItemQuantityWorkflow

원주문에 있던 아이템의 수량·가격을 수정하는 워크플로우. `ITEM_UPDATE` action을 생성하고 프로모션 adjustment를 재계산한다. `quantity: 0`으로 설정하면 아이템 제거 효과가 있다.

[← 단계 README](./README.md)

**소스**: [packages/core/core-flows/src/order/workflows/order-edit/order-edit-update-item-quantity.ts](../../../../packages/core/core-flows/src/order/workflows/order-edit/order-edit-update-item-quantity.ts)  
**호출 API**: `POST /admin/order-edits/:id/items/item/:item_id`

## 입력 / 출력

| 항목 | 타입 | 설명 |
|------|------|------|
| order_id | string | 편집 대상 주문 ID |
| items | array | 수정할 아이템 목록 (id, quantity, unit_price 등) |
| output | OrderPreviewDTO | 변경 미리보기 |

## Flowchart

```mermaid
flowchart TD
    Start([POST /admin/order-edits/:id/items/item/:item_id])
    A["acquireLockStep\n락 획득"]
    B["useQueryGraphStep\norder 조회"]
    C["useQueryGraphStep\norderChange 조회"]
    D["orderEditUpdateItemQuantityValidationStep\n취소·활성 상태 확인"]
    E["createOrderChangeActionsWorkflow\n(ORDER)\nITEM_UPDATE action 생성\n(quantity_diff 포함)"]
    F["computeAdjustmentsForPreviewWorkflow\n(PROMOTION)\n프로모션 adjustment 재계산"]
    G["previewOrderChangeStep\n변경 미리보기 반환"]
    H["releaseLockStep\n락 해제"]
    End([OrderPreviewDTO 반환])

    Start --> A --> B --> C --> D --> E --> F --> G --> H --> End
```

## Step 설명

| 순번 | Step | 모듈 | 보상(rollback) |
|------|------|------|----------------|
| 1 | `acquireLockStep` | LOCKING | 자동 해제 |
| 2 | `useQueryGraphStep` (order) | Remote Query | 없음 |
| 3 | `useQueryGraphStep` (orderChange) | Remote Query | 없음 |
| 4 | `orderEditUpdateItemQuantityValidationStep` | — | 없음 |
| 5 | `createOrderChangeActionsWorkflow` | ORDER | action 삭제 |
| 6 | `computeAdjustmentsForPreviewWorkflow` | PROMOTION | 없음 |
| 7 | `previewOrderChangeStep` | ORDER | 없음 |
| 8 | `releaseLockStep` | LOCKING | 없음 |

## 보상(Compensation) 흐름

- **`createOrderChangeActionsWorkflow` 실패**: 생성된 ITEM_UPDATE action 삭제.

## 호출하는 서브워크플로우

| 서브워크플로우 | 역할 |
|----------------|------|
| `createOrderChangeActionsWorkflow` | ITEM_UPDATE action 생성 (quantity_diff 기록) |
| `computeAdjustmentsForPreviewWorkflow` | 프로모션 조건 재평가 및 adjustment 재계산 |
