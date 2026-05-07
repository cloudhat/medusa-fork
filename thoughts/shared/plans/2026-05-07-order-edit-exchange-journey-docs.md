# Order Edit · Exchange 사용자 여정 분석 문서 작성 계획

## 개요

`참고자료/사용자 여정 분석/` 폴더에 Order Edit(주문 편집)과 Exchange(교환) 여정을 추가한다. 기존 `11-반품-부분환불/` 폴더와 동일한 양식을 따른다.

시나리오 테스트 파일이 확인되었으며, 이를 기준으로 여정 단계와 워크플로우를 정의한다.

---

## 확인된 시나리오 테스트

| 흐름 | 테스트 파일 | 규모 |
|------|------------|------|
| Order Edit | `integration-tests/http/__tests__/order-edits/order-edits.spec.ts` | 2,841줄 |
| Exchange | `integration-tests/http/__tests__/exchanges/exchanges.spec.ts` | 1,600줄 |

### Order Edit 테스트 시나리오 목록

| describe / it | 핵심 내용 |
|---------------|-----------|
| `Order Edits lifecycle > Full flow test` | 아이템 추가·수정·확정 전체 흐름 |
| `Order Edit Inventory > should manage reservations on order edit` | 재고 예약 관리 |
| `Order Edit Inventory > should manage inventory across locations` | 복수 위치 재고 |
| `Order Edit Shipping Methods > should add a shipping method` | 배송 방법 추가 |
| `Order Edit Payment Collection > should add a create a new payment collection` | 결제 컬렉션 갱신 |
| `Order Edits promotions > should update adjustments when adding a new item` | 프로모션 adjustment 재계산 |
| `Order Edits promotions > should update adjustments when updating an item` | 수량 변경 시 재계산 |
| `Order Edits promotions > should update adjustments when removing an item` | 아이템 제거 시 재계산 |
| `Order Edits promotions > should add, remove, and add buy-get adjustment depending on the quantity` | buy-get 프로모션 재계산 |
| `Order Edits promotions > should maintain shipping method adjustments` | 배송 방법 adjustment |

### Exchange 테스트 시나리오 목록

| describe / it | 핵심 내용 |
|---------------|-----------|
| `Exchanges lifecycle > test full exchange flow` | 교환 전체 흐름 (inbound + outbound) |
| `Exchanges lifecycle > Full flow with 2 orders` | 복수 주문 교환 |
| `with inbound and outbound items > should remove outbound shipping method when outbound items are completely removed` | outbound 배송 방법 제거 |
| `with inbound and outbound items > should remove inbound shipping method when inbound items are completely removed` | inbound 배송 방법 제거 |
| `Exchange adjustments > should update adjustments when adding an inbound and outbound item` | adjustment 재계산 |
| `Exchange adjustments > should enable carry_over_promotions flag (flag disabled before request)` | carry_over_promotions 플래그 |
| `Exchange adjustments > should enable carry_over_promotions flag (flag enabled before request)` | carry_over_promotions 플래그 (선행 설정) |

---

## 생성할 폴더 및 문서 구조

```
참고자료/사용자 여정 분석/
├── 12-주문편집/
│   ├── README.md
│   ├── flow-beginOrderEditWorkflow.md
│   ├── flow-orderEditAddNewItemWorkflow.md
│   ├── flow-orderEditUpdateItemQuantityWorkflow.md
│   ├── flow-removeItemOrderEditActionWorkflow.md
│   ├── flow-createOrderEditShippingMethodWorkflow.md
│   ├── flow-removeOrderEditShippingMethodWorkflow.md
│   ├── flow-requestOrderEditWorkflow.md
│   ├── flow-confirmOrderEditRequestWorkflow.md
│   └── flow-cancelOrderEditWorkflow.md
└── 13-교환/
    ├── README.md
    ├── flow-beginOrderExchangeWorkflow.md
    ├── flow-exchangeRequestItemReturnWorkflow.md
    ├── flow-exchangeAddNewItemWorkflow.md
    ├── flow-createExchangeShippingMethodWorkflow.md
    ├── flow-confirmExchangeRequestWorkflow.md
    └── flow-cancelExchangeWorkflow.md
```

---

## 각 README.md 구성 기준

기존 `11-반품-부분환불/README.md` 구조를 동일하게 따른다:

1. **한 줄 요약** + 상위 index 링크
2. **API 엔드포인트 표** (메서드 / 경로 / 워크플로우)
3. **흐름 유형 표** (시나리오별 진입 워크플로우 체인)
4. **단계별 흐름** (Step 번호 / Step명 / 모듈 / 동작)
5. **관련 엔티티 표**
6. **개입 모듈 표**

---

## 각 flow-*.md 구성 기준

기존 `flow-beginReturnOrderWorkflow.md` 구조를 동일하게 따른다:

1. 한 줄 요약 + README 링크
2. 소스 파일 경로 + 호출 API
3. 입력 / 출력 표
4. Mermaid flowchart
5. Step 설명 표 (순번 / Step / 모듈 / 보상)
6. 보상(Compensation) 흐름
7. 호출하는 서브워크플로우

---

## 작업 단계

### Phase 1: Order Edit (12-주문편집)

1. 테스트 파일 전체 정독 (`order-edits.spec.ts`)
2. 워크플로우 소스 파일 분석
   - `packages/core/core-flows/src/order/workflows/order-edit/` 내 12개 파일
3. README.md 작성
4. flow-*.md 9개 작성

### Phase 2: Exchange (13-교환)

1. 테스트 파일 전체 정독 (`exchanges.spec.ts`)
2. 워크플로우 소스 파일 분석
   - `packages/core/core-flows/src/order/workflows/exchange/` 내 10개 파일
3. README.md 작성
4. flow-*.md 6개 작성

### Phase 3: 상위 README.md 갱신

`참고자료/사용자 여정 분석/README.md`의 여정 단계 목록 표에 12, 13번 행 추가.

---

## 참고 소스 파일

### Order Edit 워크플로우

| 파일 | 설명 |
|------|------|
| `order-edit/begin-order-edit.ts` | 편집 세션 시작 |
| `order-edit/order-edit-add-new-item.ts` | 아이템 추가 |
| `order-edit/order-edit-update-item-quantity.ts` | 수량·가격 수정 |
| `order-edit/remove-order-edit-item-action.ts` | 추가한 아이템 action 제거 |
| `order-edit/create-order-edit-shipping-method.ts` | 배송 방법 추가 |
| `order-edit/remove-order-edit-shipping-method.ts` | 배송 방법 제거 |
| `order-edit/request-order-edit.ts` | 편집 요청(confirm 전 단계) |
| `order-edit/confirm-order-edit-request.ts` | 편집 확정 |
| `order-edit/cancel-begin-order-edit.ts` | 편집 세션 취소 |

### Exchange 워크플로우

| 파일 | 설명 |
|------|------|
| `exchange/begin-order-exchange.ts` | 교환 세션 시작 |
| `exchange/exchange-request-item-return.ts` | 반품(inbound) 아이템 지정 |
| `exchange/exchange-add-new-item.ts` | 교환(outbound) 아이템 추가 |
| `exchange/create-exchange-shipping-method.ts` | 배송 방법 추가 |
| `exchange/confirm-exchange-request.ts` | 교환 확정 |
| `exchange/cancel-exchange.ts` | 교환 취소 |

### 시나리오 테스트

- `integration-tests/http/__tests__/order-edits/order-edits.spec.ts`
- `integration-tests/http/__tests__/exchanges/exchanges.spec.ts`
- `integration-tests/modules/__tests__/order/workflows/begin-order-exchange.spec.ts`
- `integration-tests/modules/__tests__/order/workflows/exchange/exchange-shipping.spec.ts`
