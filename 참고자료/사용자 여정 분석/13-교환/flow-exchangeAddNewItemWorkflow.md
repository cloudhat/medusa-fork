# orderExchangeAddNewItemWorkflow

교환에서 고객에게 새로 발송할 outbound 아이템을 추가하는 워크플로우. `ITEM_ADD` action을 기록하고 프로모션 adjustment를 재계산한다.

[← 단계 README](./README.md)

**소스**: [packages/core/core-flows/src/order/workflows/exchange/exchange-add-new-item.ts](../../../../packages/core/core-flows/src/order/workflows/exchange/exchange-add-new-item.ts)  
**호출 API**: `POST /admin/exchanges/:id/outbound/items`

## 입력 / 출력

| 항목 | 타입 | 설명 |
|------|------|------|
| exchange_id | string | 교환 ID |
| items | array | 발송할 아이템 목록 (variant_id, quantity 등) |
| output | OrderPreviewDTO | 변경 미리보기 |

## Flowchart

```mermaid
flowchart TD
    Start([POST /admin/exchanges/:id/outbound/items])
    A["useRemoteQueryStep\norderExchange 조회"]
    B["useRemoteQueryStep\norder 조회"]
    C["useRemoteQueryStep\norderChange 조회"]
    D["exchangeAddNewItemValidationStep\n취소·활성 상태 확인"]
    E["addOrderLineItemsWorkflow\n(ORDER)\nLineItem 생성"]
    F["updateOrderTaxLinesWorkflow\n(TAX)\n세금 라인 갱신"]
    G["createOrderChangeActionsWorkflow\n(ORDER)\nITEM_ADD action 생성\n(reference: order_exchange)"]
    H["computeAdjustmentsForPreviewWorkflow\n(PROMOTION)\n프로모션 adjustment 재계산"]
    I["refreshExchangeShippingWorkflow\n배송비 재계산"]
    J["previewOrderChangeStep\n변경 미리보기 반환"]
    End([OrderPreviewDTO 반환])

    Start --> A --> B --> C --> D --> E --> F --> G --> H --> I --> J --> End
```

## Step 설명

| 순번 | Step | 모듈 | 보상(rollback) |
|------|------|------|----------------|
| 1 | `useRemoteQueryStep` (orderExchange) | Remote Query | 없음 |
| 2 | `useRemoteQueryStep` (order) | Remote Query | 없음 |
| 3 | `useRemoteQueryStep` (orderChange) | Remote Query | 없음 |
| 4 | `exchangeAddNewItemValidationStep` | — | 없음 |
| 5 | `addOrderLineItemsWorkflow` | ORDER | LineItem 삭제 |
| 6 | `updateOrderTaxLinesWorkflow` | TAX | 없음 |
| 7 | `createOrderChangeActionsWorkflow` | ORDER | action 삭제 |
| 8 | `computeAdjustmentsForPreviewWorkflow` | PROMOTION | 없음 |
| 9 | `refreshExchangeShippingWorkflow` | ORDER | 없음 |
| 10 | `previewOrderChangeStep` | ORDER | 없음 |

## Order Edit과의 차이

Order Edit의 `ITEM_ADD` action과 달리, 교환의 `ITEM_ADD` action에는 `reference: "order_exchange"`, `reference_id: orderExchange.id`가 추가로 기록된다. 이를 통해 확정 시 `createOrderExchangeItemsFromActionsStep`이 해당 action들을 OrderExchangeItem으로 변환한다.

## 호출하는 서브워크플로우

| 서브워크플로우 | 역할 |
|----------------|------|
| `addOrderLineItemsWorkflow` | LineItem DB 생성 |
| `updateOrderTaxLinesWorkflow` | 새 아이템 세금 라인 갱신 |
| `createOrderChangeActionsWorkflow` | ITEM_ADD action 생성 |
| `computeAdjustmentsForPreviewWorkflow` | 프로모션 조건 재평가 및 adjustment 재계산 |
| `refreshExchangeShippingWorkflow` | outbound 아이템 기반 배송비 재계산 |
