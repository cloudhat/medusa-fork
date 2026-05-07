# 03. 고객 식별·주소 입력

사용자가 이메일을 입력하거나 로그인하고, 배송 주소를 장바구니에 등록하는 단계.

[← 여정 전체 목록](../README.md) | [다음: 04 배송옵션 선택](../04-배송옵션-선택/README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `POST` | `/store/customers` | `createCustomerWorkflow` |
| `POST` | `/auth/customer/emailpass` | 인증 (Auth 모듈) |
| `GET` / `POST` | `/store/carts/:id` | `updateCartWorkflow` |

주소 입력과 고객 연결은 모두 `updateCartWorkflow`를 통해 처리된다.

---

## updateCartWorkflow

**파일**: [packages/core/core-flows/src/cart/workflows/update-cart.ts](../../../../packages/core/core-flows/src/cart/workflows/update-cart.ts)

### 입력

```typescript
{
  id,                    // 장바구니 ID
  region_id?,            // 리전 변경 시
  email?,                // 고객 이메일
  customer_id?,          // 로그인된 고객 ID
  shipping_address?,     // 배송 주소
  billing_address?,      // 청구 주소
  sales_channel_id?,
  promo_codes?
}
```

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `acquireLockStep` | `LOCKING` | cart_id 키로 락 획득 |
| 2 | `useQueryGraphStep` | Query | 장바구니 + 리전·국가 조회 |
| 3 | `validateCartStep` | — | 완료된 장바구니 차단 |
| 4 | `parallelize` | — | 아래 2개 병렬 실행 |
| 4a | `findSalesChannelStep` | `SALES_CHANNEL`, `STORE` | 채널 조회 |
| 4b | `findOrCreateCustomerStep` | `CUSTOMER` | 고객 조회 또는 신규 생성 |
| 5 | `validateSalesChannelStep` | — | 채널 유효성 검증 |
| 6 | (조건) `useQueryGraphStep` | Query | region_id 변경 시 새 리전 조회 |
| 7 | `updateCartsStep` | `CART` | Cart 필드 + Address 업데이트 |
| 8 | (조건) `deleteLineItemsStep` | `CART` | 리전 변경 시 커스텀 가격 아이템 삭제 |
| 9 | `refreshCartItemsWorkflow` | 여러 모듈 | 세금·프로모션·결제 컬렉션 재계산 |
| 10 | `releaseLockStep` | `LOCKING` | 락 해제 |

### 주소 처리 규칙

- `shipping_address.country_code`가 새 리전의 국가 목록에 없으면 `INVALID_DATA` 에러
- 리전이 변경되고 국가가 1개이면 해당 country_code를 자동 설정
- 리전이 변경되고 `country_code`가 없으면 `shipping_address = null`로 초기화

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `CART` | Cart, Address 업데이트 (`updateCarts`, `updateAddresses`) |
| `CUSTOMER` | 이메일로 고객 조회 또는 신규 생성 |
| `SALES_CHANNEL` | 판매 채널 검증 |
| `LOCKING` | 동시 수정 방지 |

---

## Customer 모듈 엔티티

**파일**: [packages/modules/customer/src/](../../../../packages/modules/customer/src/)

| 엔티티 | 주요 필드 |
|--------|----------|
| `Customer` | `email`, `first_name`, `last_name`, `company_name`, `phone`, `has_account`, `metadata` |
| `CustomerAddress` | `first_name`, `last_name`, `company`, `address_1`, `city`, `country_code`, `postal_code`, `is_default_shipping`, `is_default_billing` |
| `CustomerGroup` | 고객 그룹 (가격·프로모션 규칙 적용에 활용) |

---

## Address 저장 위치

이 단계에서 입력된 주소는 `cart_address` 테이블에 저장된다. 이후 체크아웃 완료 시 `order_address` 테이블에 **복사**되어 별도 스냅샷으로 보관된다.
