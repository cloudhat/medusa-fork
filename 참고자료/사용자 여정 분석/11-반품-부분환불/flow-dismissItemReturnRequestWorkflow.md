# dismissItemReturnRequestWorkflow

파손되거나 거절된 아이템을 수령 처리하는 워크플로우. `RECEIVE_DAMAGED_RETURN_ITEM` action을 생성하며, 이 action은 `confirmReturnReceiveWorkflow`에서 `damaged_quantity`로만 기록되고 재고에 복원되지 않는다.

[← 단계 README](./README.md)

**소스**: [packages/core/core-flows/src/order/workflows/return/dismiss-item-return-request.ts](../../../../packages/core/core-flows/src/order/workflows/return/dismiss-item-return-request.ts)
**호출 API**: `POST /admin/returns/:id/dismiss-items`

## 입력 / 출력

| 항목 | 타입 | 설명 |
|------|------|------|
| return_id | string | Return ID |
| items | `{id, quantity, internal_note?}[]` | 파손·거절 처리할 아이템 목록 (`id`는 ReturnItem ID) |
| output | OrderPreviewDTO | 변경 미리보기 |

## Flowchart

```mermaid
flowchart TD
    Start([POST /admin/returns/:id/dismiss-items])
    A["useRemoteQueryStep\nReturn 조회 (items.* 포함)"]
    B["useRemoteQueryStep\nOrder 조회"]
    C["useRemoteQueryStep\nOrderChange 조회\n(status: PENDING or REQUESTED)"]
    D["dismissItemReturnRequestValidationStep\n취소 여부·OrderChange 활성 상태·아이템 존재 확인"]
    E[["createOrderChangeActionsWorkflow\n(ORDER)\nRECEIVE_DAMAGED_RETURN_ITEM action 생성\n(아이템별 각각 생성)"]]]
    F["previewOrderChangeStep\n(ORDER)\n변경 미리보기 반환"]
    End([파손 아이템 등록 완료])

    Start --> A --> B --> C --> D --> E --> F --> End
```

## Step 설명

| 순번 | Step | 모듈 | 보상(rollback) |
|------|------|------|----------------|
| 1 | `useRemoteQueryStep` (Return) | Remote Query | 없음 |
| 2 | `useRemoteQueryStep` (Order) | Remote Query | 없음 |
| 3 | `useRemoteQueryStep` (OrderChange) | Remote Query | 없음 |
| 4 | `dismissItemReturnRequestValidationStep` | — | 없음 |
| 5 | `createOrderChangeActionsWorkflow` | ORDER | 생성된 action 삭제 |
| 6 | `previewOrderChangeStep` | ORDER | 없음 |

## 보상(Compensation) 흐름

- **`createOrderChangeActionsWorkflow` 실패**: 생성된 `RECEIVE_DAMAGED_RETURN_ITEM` action 삭제.

## 호출하는 서브워크플로우

| 워크플로우 | 목적 |
|-----------|------|
| `createOrderChangeActionsWorkflow` | `RECEIVE_DAMAGED_RETURN_ITEM` action 생성 |

## 참고

`RECEIVE_DAMAGED_RETURN_ITEM` action과 `RECEIVE_RETURN_ITEM` action의 차이는 `confirmReturnReceiveWorkflow` 단계에서 드러난다.

| action 타입 | 최종 확정 시 동작 |
|------------|----------------|
| `RECEIVE_RETURN_ITEM` | `received_quantity` 업데이트 + **재고 복원(+n)** |
| `RECEIVE_DAMAGED_RETURN_ITEM` | `damaged_quantity` 업데이트만, 재고 복원 없음 |
