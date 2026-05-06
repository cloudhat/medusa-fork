# Medusa 주문 시스템 참고자료

주문 시스템 구조 변경 설계를 위한 Medusa 오픈소스 스키마 및 로직 참조.

요구사항 원본: `/Users/kimsan/Documents/workspace/repository/heroines_data_engineering/1-projects/0.주문시스템 구조 변경/1.설계/0.요구사항/러프한 초안/요구사항 혹은 고려사항 모음.md`

---

## 문서 목록

| 문서 | 다루는 영역 |
|------|------------|
| [주문-스키마.md](주문-스키마.md) | Order, LineItem, Adjustment, Tax, Return, Exchange, Claim |
| [결제-스키마.md](결제-스키마.md) | Payment, Refund, Capture, Cart |
| [프로모션-할인-스키마.md](프로모션-할인-스키마.md) | Promotion, Campaign, PromotionRule, ApplicationMethod |
| [배송-스키마.md](배송-스키마.md) | FulfillmentSet, ServiceZone, GeoZone, ShippingOption, ShippingOptionRule |

---

## 요구사항 → 관련 스키마 매핑

| 요구사항 항목 | 관련 문서 | 핵심 모델 |
|-------------|----------|----------|
| 이벤트 소싱/불변성 | [주문-스키마.md](주문-스키마.md) | `OrderLineItem`(스냅샷) + `OrderItem`(버전별 상태) |
| 증가/차감 요소 구조 | [주문-스키마.md](주문-스키마.md) | `OrderLineItemAdjustment`, `OrderShippingMethodAdjustment`, `OrderSummary.totals` |
| 배송비 상품군 단위 | [배송-스키마.md](배송-스키마.md) | `FulfillmentSet → ServiceZone → ShippingOption` |
| 조건부 무료배송 | [배송-스키마.md](배송-스키마.md) | `ShippingOptionRule` |
| 도서산간 배송비 | [배송-스키마.md](배송-스키마.md) | `GeoZone(type=province/zip)` |
| 쿠폰 적용 범위 | [프로모션-할인-스키마.md](프로모션-할인-스키마.md) | `ApplicationMethod.target_type` + `target_rules` |
| 포인트 사용 | [결제-스키마.md](결제-스키마.md) | `Cart.CreditLine`, `Order.CreditLine` |
| 부분 반품/환불 | [주문-스키마.md](주문-스키마.md), [결제-스키마.md](결제-스키마.md) | `Return`, `OrderItem.return_*_quantity`, `Refund` |
| 정산/과세 | [주문-스키마.md](주문-스키마.md) | `OrderLineItemTaxLine`, `OrderSummary.totals.accounting_total` |
| 할인액 상품 간 분담 | [프로모션-할인-스키마.md](프로모션-할인-스키마.md) | `ApplicationMethod.allocation(each/across)` |
