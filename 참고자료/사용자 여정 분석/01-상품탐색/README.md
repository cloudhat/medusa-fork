# 01. 상품 탐색·선택

사용자가 상품 목록을 조회하고 구매할 상품·옵션을 선택하는 단계.

[← 여정 전체 목록](../README.md) | [다음: 02 장바구니 생성](../02-장바구니-생성-아이템추가/README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/store/products` | 상품 목록 조회 |
| `GET` | `/store/products/:handle` | 상품 상세 조회 |
| `GET` | `/store/products/:id/variants` | 상품 옵션(변형) 목록 |
| `GET` | `/store/shipping-options` | 배송 가능 지역·옵션 사전 조회 |

이 단계의 API는 워크플로우 없이 **Query Graph 직접 조회**로 응답을 구성한다.

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `Modules.PRODUCT` | 상품·변형(variant)·옵션 데이터 제공 |
| `Modules.PRICING` | 변형별 가격 세트(PriceSet) 계산. `calculated_price` 컨텍스트(region_id, customer_id, currency_code)로 최종 노출 가격 결정 |
| `Modules.INVENTORY` | 재고 수준(`stocked_quantity`, `reserved_quantity`) 제공 — 품절 여부 표시 |
| `Modules.SALES_CHANNEL` | 해당 판매 채널에 활성화된 상품만 노출 |

---

## 핵심 데이터 구조

### Product → Variant → InventoryItem 연결

```
Product
  └── ProductVariant (variant_id, sku, allow_backorder, manage_inventory)
        └── InventoryItem (inventory_item_id, requires_shipping)
              └── InventoryLevel (location_id, stocked_quantity, reserved_quantity)
```

- `manage_inventory: false` 변형은 재고 수준 무시 → 항상 구매 가능
- `allow_backorder: true` 변형은 재고 부족 시에도 주문 허용

### 가격 계산 컨텍스트

`/store/products` 조회 시 `calculated_price`를 포함하려면 `fields=+variants.calculated_price`와 함께 다음 컨텍스트가 필요하다.

| 컨텍스트 파라미터 | 설명 |
|------------------|------|
| `region_id` | 지역별 가격 규칙 적용 |
| `currency_code` | 통화 |
| `customer_id` | 고객 그룹 기반 가격 |

---

## 다음 단계로의 전달 데이터

상품 탐색 단계에서 다음 단계(장바구니 생성)로 전달되는 핵심 값:

| 데이터 | 사용 목적 |
|--------|----------|
| `variant_id` | 장바구니 아이템 추가 |
| `quantity` | 주문 수량 |
| `sales_channel_id` | 장바구니 생성 시 채널 설정 |
| `region_id` | 장바구니 생성 시 리전·통화 설정 |
