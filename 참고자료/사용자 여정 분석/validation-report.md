통합 테스트 기반 사용자 여정 문서 검증 보고서

검증 기준: integration-tests/http/__tests__/ 의 실제 API 호출 시퀀스
검증 대상: 참고자료/사용자 여정 분석/ 01~11단계 문서

---

## 요약

| 단계 | API 순서 정확성 | 누락 항목 |
|------|---------------|----------|
| 01 상품 탐색 | 테스트 없음 | — |
| 02 장바구니 생성·아이템 추가 | ✅ | — |
| 03 고객 식별·주소 입력 | 테스트 없음 (guest) | — |
| 04 배송 옵션 선택 | ✅ | — |
| 05 프로모션 적용 | ✅ | promo_codes 경로 미언급 (아래 참고) |
| 06 세금 계산 | ✅ | — |
| 07 결제 세션 생성 | ✅ | — |
| 08 주문 생성·체크아웃 완료 | ✅ | — |
| 09 풀필먼트·배송 처리 | ✅ | — |
| 10 배송 완료 | ✅ | — |
| 11 반품·부분환불 | ✅ (일치하는 것들의 순서는 맞음) | **6개 API 누락** |

---

## 테스트로 확인된 최소 체크아웃 흐름

근거: `integration-tests/http/__tests__/order/admin/order.spec.ts` — 풀필먼트 테스트의 beforeEach

```
POST /store/carts                                      (02 단계)
POST /store/carts/:id/shipping-methods                 (04 단계)
POST /store/payment-collections                        (07 단계)
POST /store/payment-collections/:id/payment-sessions   (07 단계)
POST /store/carts/:id/complete                         (08 단계)
```

이 순서는 문서 02→04→07→08 와 일치한다.

---

## 단계별 상세

### 01 상품 탐색

테스트에서 상품은 beforeEach에서 admin API로 미리 생성되므로, `GET /store/products` 호출 자체를 테스트하는 시나리오는 확인되지 않았다.
판정: 테스트 커버리지 없음 — 오류 단정 불가.

---

### 03 고객 식별·주소 입력

통합 테스트는 guest checkout(인증 없음)으로 진행된다. `POST /store/customers`, `POST /auth/customer/emailpass` 호출은 테스트에서 확인되지 않는다.
판정: 테스트 커버리지 없음 — 오류 단정 불가.

---

### 05 프로모션 적용

문서는 `POST /store/carts/:id/promotions`만 기술하고 있다.
통합 테스트(`cart.spec.ts` "should successfully complete cart with promotions")에서는 프로모션을 카트 생성 시 `promo_codes` 파라미터로 적용한다.

```typescript
POST /store/carts  { promo_codes: [promotion.code], ... }
```

이 경로는 문서 02단계(createCartWorkflow)에도 입력 파라미터로 `promo_codes?`가 기술되어 있으나, 05단계 문서에는 별도로 언급되지 않는다.
판정: 순서 오류 없음. 프로모션을 카트 생성 시점에 포함시키는 경로가 05단계 문서에서 누락되어 있음.

---

### 06 세금 계산

문서는 이미 다음과 같이 기술하고 있다.

> "세금 계산은 명시적 API 호출 없이 refreshCartItemsWorkflow 내에서 자동으로 수행된다."

통합 테스트에서 `POST /store/carts/:id/taxes`는 명시적으로 호출되지 않는다. 문서 내용과 일치한다.
판정: ✅ 일치.

---

### 11 반품·부분환불

통합 테스트 근거: `integration-tests/http/__tests__/returns/returns.spec.ts` — "should initiate a return" (라인 434-854)

**테스트에서 확인된 전체 반품 흐름:**

```
1.  POST /admin/returns                               (beginReturnOrderWorkflow ✅ 문서에 있음)
2.  POST /admin/returns/:id                           (업데이트 — 문서 누락)
3.  POST /admin/returns/:id/request-items             (requestItemReturnWorkflow ✅ 문서에 있음)
4.  POST /admin/returns/:id/request-items/:action_id  (아이템 수정 — 문서 누락)
5.  POST /admin/returns/:id/shipping-method           (반품 배송비 설정 — 문서 누락)
6.  POST /admin/returns/:id/request                   (confirmReturnRequestWorkflow ✅ 문서에 있음)
7.  POST /admin/returns/:id/receive                   (수령 시작 — 문서 누락)
8.  POST /admin/returns/:id/receive-items             (아이템 수령 처리 — 문서 누락)
9.  POST /admin/returns/:id/dismiss-items             (아이템 거절/파손 처리 — 문서 누락)
10. POST /admin/returns/:id/receive/confirm           (confirmReturnReceiveWorkflow ✅ 문서에 있음)
```

**누락된 API 6개:**

| 경로 | 용도 |
|------|------|
| `POST /admin/returns/:id` | 반품 메타데이터·입고 위치 등 업데이트 |
| `POST /admin/returns/:id/request-items/:action_id` | 이미 추가된 반품 아이템 수량 수정 |
| `POST /admin/returns/:id/shipping-method` | 반품 배송 방법 지정 |
| `POST /admin/returns/:id/receive` | 수령 프로세스 시작 |
| `POST /admin/returns/:id/receive-items` | 개별 아이템 수령 처리 |
| `POST /admin/returns/:id/dismiss-items` | 파손·거절 아이템 처리 |

**추가 확인 사항 — 흐름 요약 테이블 오류:**

문서 상단 "관리자 주도 반품 흐름" 행에는 다음과 같이 기재되어 있다.

> `beginReturnOrderWorkflow → confirmReturnRequestWorkflow → confirmReturnReceiveWorkflow`

`requestItemReturnWorkflow` (3번 단계)가 흐름 요약에서 빠져 있다. 이 워크플로우는 API 표에는 있지만 흐름 요약 테이블에서는 누락되었다.

---

## 기타 — createCartWorkflow hook 누락 (이전 대화 확인 사항)

문서에는 `createCartWorkflow` 의 `validate` hook (createCartsStep 직전)과 `cartCreated` hook (워크플로우 마지막) 이 표기되지 않았다. 이는 flow-createCartWorkflow.md의 flowchart 정확성 문제이며 API 순서 오류는 아니다.

---

## 결론

- **체크아웃 흐름 (01~08)**: API 순서는 테스트와 일치. 일부 단계(03, 01)는 테스트에서 검증되지 않았으나 순서 오류 근거는 없다.
- **풀필먼트·배송 흐름 (09~10)**: API 순서 테스트와 완전히 일치.
- **반품 흐름 (11)**: 일치하는 API들의 순서는 맞으나, 중간 단계 6개 API가 문서에 누락되어 있다. 실제 반품 구현 시 이 API들 없이는 완료 불가능하다.
