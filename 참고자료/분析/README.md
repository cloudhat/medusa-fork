---
# 요구사항별 Medusa 처리 방식 분析

「요구사항 혹은 고려사항 모음.md」에 열거된 네 가지 주제를 Medusa가 어떻게 다루는지 정리한다.

## 문서 목록

| 파일 | 주제 |
|------|------|
| [01-배송비.md](./01-배송비.md) | 배송 그룹, 조건부 무료배송, 도서산간 |
| [02-할인.md](./02-할인.md) | 포인트, 쿠폰(상품·그룹·주문 전체 단위) |
| [03-과세.md](./03-과세.md) | 과세 대상 구분, 할인액 분담과 과세 신고 |
| [04-부분취소-환불.md](./04-부분취소-환불.md) | 증가·차감 요소 재계산, 무료배송 기준 이탈 |

## 핵심 요약

| 요구사항 | Medusa 지원 여부 | 비고 |
|----------|-----------------|------|
| 배송 그룹 단위 묶음 | 미지원 (설계 필요) | Cart당 ShippingMethod 1개만 허용 |
| 조건부 무료배송 | 부분 지원 | ShippingOptionRule 또는 Promotion으로 구현 |
| 도서산간 별도 배송비 | 지원 | GeoZone(city/postal_code) + 별도 ServiceZone |
| 포인트 사용 | 미지원 (확장 필요) | CreditLine 구조는 있으나 포인트 모듈 없음 |
| 쿠폰(적용 범위별) | 지원 | `target_type`: items / order / shipping_methods |
| 과세 대상 구분 | 지원 | `is_tax_inclusive`, `is_discountable` 필드 |
| 할인액 상품 간 분담 추적 | 지원 | `allocation=across` → 아이템별 Adjustment 생성 |
| 부분 환불 | 지원 | Return → OrderChange → Refund 흐름 |
| 반품 후 배송비 자동 재계산 | 미지원 (확장 필요) | 배송비 조건 이탈 감지 로직 없음 |
