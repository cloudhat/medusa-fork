# 08. 체크아웃 완료·주문 생성

사용자가 "결제하기"를 누르면 Cart가 Order로 전환되고 결제 승인이 이루어지는 단계.

[← 여정 전체 목록](../README.md) | [다음: 09 풀필먼트·배송](../09-풀필먼트-배송처리/README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `POST` | `/store/carts/:id/complete` | `completeCartWorkflow` |

**파일**: [packages/medusa/src/api/store/carts/[id]/complete/route.ts](../../../../packages/medusa/src/api/store/carts/%5Bid%5D/complete/route.ts)

API 핸들러가 `Modules.WORKFLOW_ENGINE`을 통해 워크플로우를 실행한다. 동일 cart_id로 중복 호출 시 이미 생성된 order_id를 반환한다 (멱등성, `retentionTime: 3일`).

---

## completeCartWorkflow 전체 Step 순서

**파일**: [packages/core/core-flows/src/cart/workflows/complete-cart.ts](../../../../packages/core/core-flows/src/cart/workflows/complete-cart.ts)

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `acquireLockStep` | `LOCKING` | cart_id 락 (timeout 30초, TTL 2분) |
| 2 | `parallelize` | — | 아래 2개 병렬 실행 |
| 2a | `useQueryGraphStep` (order_cart) | Query | 기존 order 존재 여부 확인 (멱등성 체크) |
| 2b | `useQueryGraphStep` (cart) | Query | 장바구니 전체 조회 (inventory level, payment_collection 포함) |
| 3 | `validateCartPaymentsStep` | — | PENDING/REQUIRES_MORE/AUTHORIZED/CAPTURED 상태 세션 필터링 |
| 4 | `compensatePaymentIfNeededStep` | — | 실행 시엔 아무것도 안 함. 실패 보상 시 결제 환불 트리거 |
| 5 | `validate` (hook) | — | 커스텀 검증 지점 |
| — | **`when("create-order")` — 최초 완료 시에만 아래 실행** | — | orderId가 없을 때만 진입 |
| 6 | `useQueryGraphStep` (shipping_option) | Query | shipping_profile_id 조회 |
| 7 | `validateShippingStep` | — | 아이템 배송 프로파일 ↔ 배송 방법 매핑 검증 |
| 8 | `createOrdersStep` | `ORDER` | Order 레코드 생성 (`status: PENDING`) |
| **9~13** | **`parallelize`** | — | **아래 5개 동시 실행** |
| 9 | `createRemoteLinkStep` | Link | ORDER↔CART, ORDER↔PROMOTION, ORDER↔PAYMENT 링크 생성 |
| 10 | `updateCartsStep` | `CART` | `cart.completed_at = now` 설정 |
| 11 | `reserveInventoryStep` | `INVENTORY`, `LOCKING` | 재고 예약 레코드 생성 (inventory lock 하에서) |
| 12 | `registerUsageStep` | `PROMOTION` | 프로모션 사용 횟수·예산 차감 |
| 13 | `emitEventStep` | `EVENT_BUS` | `order.placed` 이벤트 발행 |
| 14 | `beforePaymentAuthorization` (hook) | — | 결제 인증 직전 커스터마이징 지점 |
| 15 | `authorizePaymentSessionStep` | `PAYMENT` | 결제 세션 승인 (첫 번째 세션만 처리) |
| 16 | `addOrderTransactionStep` | `ORDER` | Capture를 OrderTransaction으로 기록 |
| 17 | `orderCreated` (hook) | — | 주문 생성 후 커스터마이징 지점 |
| 18 | `releaseLockStep` | `LOCKING` | cart_id 락 해제 |

---

## Cart → Order 데이터 변환

`createOrdersStep` 이전에 `transform`으로 cart 데이터를 order 구조로 변환한다.

| Cart 데이터 | Order 데이터 |
|------------|-------------|
| `LineItem` | `OrderLineItem` (상품 스냅샷 전체 복사) |
| `ShippingMethod` | `OrderShippingMethod` (배송 방법 스냅샷) |
| `Address` | `OrderAddress` (id 제거 후 새 레코드 생성) |
| `LineItemAdjustment` | `OrderLineItemAdjustment` |
| `LineItemTaxLine` | `OrderLineItemTaxLine` |
| `CreditLine` | `OrderCreditLine` |

---

## 재고 예약 (`reserveInventoryStep`)

**파일**: [packages/core/core-flows/src/cart/steps/reserve-inventory.ts](../../../../packages/core/core-flows/src/cart/steps/reserve-inventory.ts)

- `Modules.LOCKING`으로 inventory_item_id 단위 락 획득
- `Modules.INVENTORY`의 `createReservationItems(items)` 호출
- 각 예약: `{ line_item_id, inventory_item_id, quantity, location_id: location_ids[0] }`
- 가용 재고(`stocked - reserved`)가 충분한 첫 번째 위치에만 예약
- **보상**: 워크플로우 실패 시 `deleteReservationItems(reservationIds)`로 예약 취소

---

## 결제 인증 (`authorizePaymentSessionStep`)

**파일**: [packages/core/core-flows/src/payment/steps/authorize-payment-session.ts](../../../../packages/core/core-flows/src/payment/steps/authorize-payment-session.ts)

1. `paymentModule.authorizePaymentSession(session_id)` 호출
2. 인증 후 상태 재조회:
   - `REQUIRES_MORE` → `PAYMENT_REQUIRES_MORE_ERROR` throw (3DS 추가 인증 필요)
   - `AUTHORIZED` 아님 또는 Payment 없음 → `PAYMENT_AUTHORIZATION_ERROR` throw
3. 성공 시 `Payment` 객체 반환
4. **보상**: `paymentModule.cancelPayment(payment.id)` (REQUIRES_MORE 상태는 취소 없이 유지)

API 핸들러에서 `PAYMENT_AUTHORIZATION_ERROR` / `PAYMENT_REQUIRES_MORE_ERROR`는 **HTTP 200**으로 내려가며, 응답 body에 `error` 필드와 함께 `cart`가 포함된다.

---

## Order 모듈 핵심 엔티티

**파일**: [packages/modules/order/src/models/](../../../../packages/modules/order/src/models/)

| 엔티티 | 주요 필드 |
|--------|----------|
| `Order` | `status` (PENDING), `version`, `display_id`, `currency_code`, `canceled_at` |
| `OrderItem` | 버전별 수량 추적: `quantity`, `fulfilled_quantity`, `return_requested_quantity` 등 |
| `OrderTransaction` | `reference: "capture"`, `reference_id: capture_id`, `amount` (음수이면 환불) |
| `OrderSummary` | 버전별 합계 정보 (`totals` JSON) |

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `ORDER` | Order, OrderLineItem, OrderItem, OrderTransaction 생성 |
| `CART` | `completed_at` 설정 |
| `PAYMENT` | 결제 세션 승인 |
| `INVENTORY` | 재고 예약 생성 |
| `PROMOTION` | 사용량 등록 |
| `LOCKING` | Cart 락 + Inventory 락 |
| Link | ORDER↔CART, ORDER↔PROMOTION, ORDER↔PAYMENT 연결 |
