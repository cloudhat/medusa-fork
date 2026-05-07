# beginExchangeOrderWorkflow

관리자가 교환 세션을 시작할 때 호출되는 워크플로우. OrderExchange 레코드와 `change_type: "exchange"` 인 OrderChange를 생성한다.

[← 단계 README](./README.md)

**소스**: [packages/core/core-flows/src/order/workflows/exchange/begin-order-exchange.ts](../../../../packages/core/core-flows/src/order/workflows/exchange/begin-order-exchange.ts)  
**호출 API**: `POST /admin/exchanges`

## 입력 / 출력

| 항목 | 타입 | 설명 |
|------|------|------|
| order_id | string | 교환 대상 주문 ID |
| created_by? | string | 교환을 시작한 관리자 ID |
| description? | string | 교환 설명 |
| metadata? | object | 추가 메타데이터 |
| output | OrderChangeDTO | 생성된 OrderChange 객체 |

## Flowchart

```mermaid
flowchart TD
    Start([POST /admin/exchanges])
    A["useRemoteQueryStep\n주문 조회"]
    B["beginOrderExchangeValidationStep\n주문 취소 여부 확인"]
    C["createOrderExchangesStep\n(ORDER)\nOrderExchange 레코드 생성"]
    D["createOrderChangeStep\n(ORDER)\nOrderChange 생성\n(change_type: exchange, exchange_id 연결)"]
    End([OrderChange 반환])

    Start --> A --> B --> C --> D --> End
```

## Step 설명

| 순번 | Step | 모듈 | 보상(rollback) |
|------|------|------|----------------|
| 1 | `useRemoteQueryStep` | Remote Query | 없음 |
| 2 | `beginOrderExchangeValidationStep` | — | 없음 |
| 3 | `createOrderExchangesStep` | ORDER | OrderExchange 삭제 |
| 4 | `createOrderChangeStep` | ORDER | OrderChange 삭제 |

## 보상(Compensation) 흐름

- **`createOrderExchangesStep` 실패**: 생성된 OrderExchange 삭제.
- **`createOrderChangeStep` 실패**: 생성된 OrderChange 삭제.

## 호출하는 서브워크플로우

없음.
