# 07. 결제 세션 생성

사용자가 결제 수단을 선택하고 결제 세션이 생성되는 단계.

[← 여정 전체 목록](../README.md) | [다음: 08 체크아웃 완료](../08-주문생성-체크아웃완료/README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `POST` | `/store/carts/:id/payment-collection` | `createPaymentCollectionForCartWorkflow` |
| `GET` | `/store/carts/:id/payment-collection` | (Query 직접 조회) |
| `POST` | `/store/payment-collections/:id/payment-sessions` | `createPaymentSessionsWorkflow` |
| `DELETE` | `/store/payment-collections/:id/payment-sessions/:session_id` | `deletePaymentSessionsWorkflow` |

---

## createPaymentCollectionForCartWorkflow

**파일**: [packages/core/core-flows/src/cart/workflows/create-payment-collection-for-cart.ts](../../../../packages/core/core-flows/src/cart/workflows/create-payment-collection-for-cart.ts)

PaymentCollection은 장바구니당 1개다. API 핸들러에서 이미 존재하는지 확인 후 없을 때만 실행한다.

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `acquireLockStep` | `LOCKING` | cart_id 락 |
| 2 | `useRemoteQueryStep` | Remote Query | 장바구니 조회 (currency_code, total, payment_collection.id) |
| 3 | `parallelize` | — | `validateCartStep` + `validateExistingPaymentCollectionStep` |
| 4 | `createPaymentCollectionsStep` | `PAYMENT` | PaymentCollection 레코드 생성 |
| 5 | `createRemoteLinkStep` | Link | `CART ↔ PAYMENT` Remote Link 생성 |
| 6 | `releaseLockStep` | `LOCKING` | 락 해제 |

---

## createPaymentSessionsWorkflow

**파일**: [packages/core/core-flows/src/payment-collection/workflows/create-payment-session.ts](../../../../packages/core/core-flows/src/payment-collection/workflows/create-payment-session.ts)

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `useRemoteQueryStep` | Remote Query | PaymentCollection 조회 |
| 2 | (조건) `useRemoteQueryStep` | Remote Query | 로그인 고객 조회 (account_holders 포함) |
| 3 | (조건) `createPaymentAccountHolderStep` | `PAYMENT` | AccountHolder 없으면 생성 |
| 4 | (조건) `createRemoteLinkStep` | Link | `CUSTOMER ↔ PAYMENT` AccountHolder 링크 |
| 5 | `parallelize` | — | 아래 2개 동시 실행 |
| 5a | `createPaymentSessionStep` | `PAYMENT` | 새 PaymentSession 생성 + 외부 프로바이더 호출 |
| 5b | `deletePaymentSessionsWorkflow` | `PAYMENT` | 기존 활성 세션 삭제 (분할결제 미지원) |

**`createPaymentSessionStep` 내부**: `paymentModule.createPaymentSession(payment_collection_id, { provider_id, amount, currency_code, data, context })` → 외부 결제 프로바이더의 세션 초기화 API 호출.

---

## Payment 모듈 엔티티 구조

**파일**: [packages/modules/payment/src/models/](../../../../packages/modules/payment/src/models/)

```
PaymentCollection (pay_col_...)
  ├── status: NOT_PAID | AWAITING | AUTHORIZED | PARTIALLY_AUTHORIZED | CANCELED
  ├── amount, currency_code
  ├── authorized_amount, captured_amount, refunded_amount
  └── PaymentSession (payses_...)
        ├── status: PENDING | AUTHORIZED | REQUIRES_MORE | CANCELED | ERROR
        ├── provider_id
        ├── data (json, 프로바이더 응답)
        └── Payment (pay_...)
              ├── captured_at
              ├── canceled_at
              ├── Capture (capt_...)
              └── Refund (ref_...)
```

---

## 결제 상태 흐름

```
PaymentSession.status
  PENDING ──→ AUTHORIZED ──→ (Payment 생성됨)
             └──→ REQUIRES_MORE (3DS 등 추가 인증 필요)
             └──→ ERROR

Payment.status (captured_at / canceled_at 기준)
  (captured_at = null) → 미캡처
  (captured_at 설정)   → 캡처 완료
```

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `PAYMENT` | PaymentCollection, PaymentSession, AccountHolder 생성·관리; 외부 결제 프로바이더 연동 |
| `CUSTOMER` | AccountHolder 생성 시 고객 정보 조회 |
| Link | CART ↔ PAYMENT, CUSTOMER ↔ PAYMENT (AccountHolder) 연관 |
| `LOCKING` | 동시 생성 방지 |
