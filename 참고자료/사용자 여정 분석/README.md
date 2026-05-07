---
date: 2026-05-07T00:00:00+09:00
git_commit: 589258aa1c02de3637aa26914f89e1967fd3358e
branch: develop
repository: medusa
topic: "장바구니부터 배송·반품까지 사용자 여정 전체 흐름"
tags: [research, cart, order, fulfillment, payment, return, refund]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
---

# 사용자 여정 분석: 장바구니 → 배송 → 반품/환불

Medusa 기반 커머스의 구매 전 과정을 사용자 여정 단위로 분해하고, 각 단계에서 개입하는 워크플로우·모듈·API 라우트를 정리한 문서 모음.

## 여정 단계 목록

| # | 단계 | 핵심 워크플로우 | 개입 모듈 |
|---|------|----------------|-----------|
| [01](./01-상품탐색/README.md) | 상품 탐색·선택 | — (Query 직접 조회) | Product, Pricing, Inventory, SalesChannel |
| [02](./02-장바구니-생성-아이템추가/README.md) | 장바구니 생성 + 아이템 추가 | `createCartWorkflow`, `addToCartWorkflow` | Cart, Customer, Product, Pricing, Inventory, Locking |
| [03](./03-고객식별-주소입력/README.md) | 고객 식별·주소 입력 | `updateCartWorkflow` | Cart, Customer, SalesChannel, Region |
| [04](./04-배송옵션-선택/README.md) | 배송 옵션 조회·선택 | `listShippingOptionsForCartWorkflow`, `addShippingMethodToCartWorkflow` | Cart, Fulfillment, Pricing, Tax, Locking |
| [05](./05-프로모션-적용/README.md) | 프로모션·할인 적용 | `updateCartPromotionsWorkflow` | Cart, Promotion, Locking |
| [06](./06-세금계산/README.md) | 세금 계산 | `updateTaxLinesWorkflow`, `upsertTaxLinesWorkflow` | Cart, Tax, Locking |
| [07](./07-결제세션-생성/README.md) | 결제 세션 생성 | `createPaymentCollectionForCartWorkflow`, `createPaymentSessionsWorkflow` | Payment, Cart, Customer, Locking |
| [08](./08-주문생성-체크아웃완료/README.md) | 체크아웃 완료·주문 생성 | `completeCartWorkflow` | Cart, Order, Payment, Inventory, Promotion, Locking |
| [09](./09-풀필먼트-배송처리/README.md) | 풀필먼트 생성·배송 처리 | `createOrderFulfillmentWorkflow`, `createOrderShipmentWorkflow` | Order, Fulfillment, Inventory, Locking |
| [10](./10-배송완료/README.md) | 배송 완료 | `markOrderFulfillmentAsDeliveredWorkflow` | Order, Fulfillment, Locking |
| [11](./11-반품-부분환불/README.md) | 반품 + 부분환불 | `confirmReturnRequestWorkflow`, `confirmReturnReceiveWorkflow`, `refundPaymentWorkflow` | Order, Payment, Fulfillment, Inventory |
| [12](./12-주문편집/README.md) | 주문 편집 (Order Edit) | `beginOrderEditOrderWorkflow`, `orderEditAddNewItemWorkflow`, `confirmOrderEditRequestWorkflow` | Order, Promotion, Tax, Inventory, Payment, Locking |
| [13](./13-교환/README.md) | 교환 (Exchange) | `beginExchangeOrderWorkflow`, `orderExchangeRequestItemReturnWorkflow`, `confirmExchangeRequestWorkflow` | Order, Promotion, Tax, Inventory, Fulfillment, Payment |

## 모듈 전체 관계도

```
SalesChannel ──┐
Region ────────┤
Customer ──────┤
               ▼
              Cart ──── Promotion
               │           │
               │      LineItemAdjustment
               │      ShippingMethodAdjustment
               │
               ├── Tax (TaxLines)
               │
               ├── PaymentCollection ── PaymentSession ── Payment
               │                                              │
               ▼                                          Capture / Refund
             Order ─────────────────────────── Promotion (usage)
               │
               ├── Inventory (ReservationItem)
               │
               └── Fulfillment ── StockLocation
                        │
                    FulfillmentLabel (Tracking)
```

## 공통 패턴

- **락(Locking)**: Cart를 변경하는 모든 워크플로우는 `acquireLockStep(cart_id)` → 작업 → `releaseLockStep`으로 동시 요청을 직렬화한다.
- **보상(Compensation)**: 각 step은 보상 함수를 가지며, 워크플로우 실패 시 자동으로 이전 상태를 복원한다.
- **Remote Link**: 모듈 간 연관은 DB 외래키 대신 Remote Link 테이블로 관리된다. (`ORDER ↔ CART`, `ORDER ↔ PAYMENT`, `ORDER ↔ FULFILLMENT` 등)
- **refreshCartItemsWorkflow**: 아이템 추가/수정/배송 방법 선택 후 공통으로 호출되어 세금·프로모션·결제 컬렉션을 일괄 재계산한다.
