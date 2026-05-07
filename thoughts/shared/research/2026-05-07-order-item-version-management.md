---
date: 2026-05-07T17:59:50+0900
researcher: SAN KIM
git_commit: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
branch: develop
repository: medusa-fork
topic: "OrderItem 버전 관리 구조와 주문 조회 쿼리 방식 (반품 시나리오 중심)"
tags: [research, codebase, order, order-item, version, return, order-change]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
---

# Research: OrderItem 버전 관리 구조와 주문 조회 쿼리 방식

**Date**: 2026-05-07T17:59:50+0900
**Researcher**: SAN KIM
**Git Commit**: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
**Branch**: develop
**Repository**: medusa-fork

## Research Question

주문내역 조회 시 OrderItem의 버전(version) 관리 구조와 쿼리 방법, 그리고 여러 번 반품이 발생했을 때 각 버전이 어떻게 누적되고 최종 상태가 어떻게 노출되는지 조사한다.

## Summary

Medusa 의 주문 모델은 세 엔티티로 분리된다.

- **`Order`** : `version` 컬럼을 보유하는 루트. 현재 시점의 "정식" 버전 번호를 가진다.
- **`OrderItem`** : `(order_id, version)` 인덱스를 가진 **버전별 스냅샷 행(row)**. `quantity`·`fulfilled_quantity`·`return_requested_quantity`·`return_received_quantity` 등 **수량 카운터**를 모두 보유한다.
- **`OrderLineItem`** : 상품 정보 스냅샷. `version` 없음. 상품 제목·variant·가격 등 카탈로그 데이터만 들고 있고 한 번 만들어지면 변하지 않는다.

버전 갱신은 **`OrderChange` → `confirm` → `applyChangesToOrder`** 파이프라인을 통한다.

1. `createOrderChange_` 가 `order.version + 1` 의 `OrderChange` 를 만든다 (`order-module-service.ts:2522-2536`).
2. `RETURN_ITEM`, `RECEIVE_RETURN_ITEM` 등 `OrderChangeAction` 들이 그 change 에 매달린다.
3. `confirmOrderChange_` → `applyOrderChanges_` → `applyChangesToOrder` 가 호출되면, 각 액션 핸들러가 **현재 버전 OrderItem 을 메모리상으로 깊은 복사**해 카운터를 갱신한 뒤, **새 version 번호로 새 OrderItem row 를 INSERT** 한다 (`apply-order-changes.ts:84-101`).
4. 동시에 `Order.version` 자체도 새 값으로 UPDATE 된다 (`apply-order-changes.ts:191`).

**핵심 결정 (apply-order-changes.ts:86)**:
```
id: orderItem.version === version ? orderItem.id : undefined
```
- `orderItem.version === version` (즉 같은 버전 행이 이미 있음) → 기존 행 **UPDATE**
- `orderItem.version < version` → `id: undefined` 로 **INSERT** (새 스냅샷 생성)

따라서 한 주문에서 N 번의 반품/변경이 일어나면 한 line_item 당 OrderItem 행이 최대 N+1 개까지 누적된다 (이전 버전 행은 삭제되지 않고 보존).

**조회 측면**:
- `GET /admin/orders/:id` → `getOrderDetailWorkflow` → `useQueryGraphStep(entity: "order", filters: { id, version? })` 로 쿼리한다 (`get-order-detail.ts:71-112`).
- `version` 쿼리 파라미터를 명시하지 않으면 **모든 버전의 OrderItem 행이 다 반환**된다 (filter 미적용).
- `version` 을 명시하면 그 버전의 OrderItem 만 반환된다.
- 결과는 `OrderModuleService.retrieveOrder` → `formatOrder` (`transform-order.ts:37-63`) 가 **OrderItem 과 OrderLineItem 을 머지**해서 `items[]` 로 노출한다. `items[].detail.*` 는 OrderItem 의 카운터, `items[].title`/`variant_id` 등은 OrderLineItem 에서 온다.
- Admin UI 가 호출하는 일반 호출은 보통 `version` 미지정 이며, `OrderItem.version` 의 가장 큰 값(=현재 `order.version`) 행이 "최신 상태"로 사용된다. 하위 버전 행은 함께 반환되지만 "이전 스냅샷"으로 식별 가능하다.

## Detailed Findings

### 1. 엔티티 구조

#### OrderItem (버전 행)

[packages/modules/order/src/models/order-item.ts](packages/modules/order/src/models/order-item.ts)

| 필드 | 타입 | 기본값 | 비고 |
|---|---|---|---|
| `id` | id | — | `orditem` prefix |
| `version` | number | `1` | **이 행이 속한 주문 version** |
| `unit_price` | bigNumber | nullable | |
| `compare_at_unit_price` | bigNumber | nullable | |
| `quantity` | bigNumber | — | 주문 수량 |
| `fulfilled_quantity` | bigNumber | `0` | 출고 처리된 수량 |
| `delivered_quantity` | bigNumber | `0` | |
| `shipped_quantity` | bigNumber | `0` | |
| `return_requested_quantity` | bigNumber | `0` | 반품 요청 수량 |
| `return_received_quantity` | bigNumber | `0` | 반품 수령(정상 입고) 수량 |
| `return_dismissed_quantity` | bigNumber | `0` | 파손 입고 수량 |
| `written_off_quantity` | bigNumber | `0` | 손실 처리 수량 |
| `metadata` | json | nullable | |

관계: `belongsTo Order` (FK `order_id`), `hasOne OrderLineItem` (FK `item_id`).

인덱스 (line 29-54):
- `IDX_order_item_order_id_version` on `(order_id, version)` — **비유일** partial index (`deleted_at IS NULL`).
- `(order_id, version, item_id)` 에 unique 제약은 **없다**.

#### OrderLineItem (상품 스냅샷)

[packages/modules/order/src/models/line-item.ts](packages/modules/order/src/models/line-item.ts)

`version` 없음. `title`, `variant_id`, `product_id`, `unit_price`, `tax_lines`, `adjustments`, 카탈로그 메타데이터 등을 보유. `OrderItem.item_id` 가 이걸 참조한다.

#### Order (루트)

[packages/modules/order/src/models/order.ts:17](packages/modules/order/src/models/order.ts#L17)

`version: model.number().default(1)`. `hasMany items` (OrderItem), `hasMany summary` (OrderSummary).

#### OrderSummary (총액 스냅샷)

[packages/modules/order/src/models/order-summary.ts](packages/modules/order/src/models/order-summary.ts)

`version` (default 1), `totals` (json). `IDX_order_summary_order_id_version` 으로 OrderItem 과 같은 (order_id, version) 키 패턴을 가짐. 버전 별 총액 스냅샷.

### 2. 버전 증가 파이프라인

#### Step A — OrderChange 생성

[packages/modules/order/src/services/order-module-service.ts:2522-2536](packages/modules/order/src/services/order-module-service.ts#L2522-L2536)

```ts
return {
  ...dataMap[order.id],
  version: order.version! + 1,
} as any
```

`OrderChange.version = order.version + 1`. `OrderChangeAction` 들은 `@OnInit` 훅으로 부모 change 의 version 을 자동 상속 (line 147-165).

#### Step B — applyChangesToOrder

[packages/modules/order/src/utils/apply-order-changes.ts:61](packages/modules/order/src/utils/apply-order-changes.ts#L61)

```ts
const version = actionsMap[order.id]?.[0]?.version ?? order.version
```

새 OrderItem 의 version 번호는 액션이 들고 있는 (이미 +1 된) version.

[apply-order-changes.ts:84-101](packages/modules/order/src/utils/apply-order-changes.ts#L84-L101):

```ts
const itemToUpsert = {
  id: orderItem.version === version ? orderItem.id : undefined,
  item_id: itemId,
  order_id: order.id,
  version,
  quantity: orderItem.quantity,
  fulfilled_quantity: orderItem.detail.fulfilled_quantity,
  return_requested_quantity: orderItem.detail.return_requested_quantity,
  return_received_quantity: orderItem.detail.return_received_quantity,
  ...
}
```

- 같은 version 의 행이 이미 있으면 → UPDATE.
- 없으면 → 새 INSERT (새 스냅샷). 이전 버전의 OrderItem 은 그대로 남는다.

#### Step C — Order.version 갱신

[apply-order-changes.ts:191](packages/modules/order/src/utils/apply-order-changes.ts#L191) → `orderService_.update` 가 `Order.version = version` 으로 UPDATE.

### 3. 액션 핸들러 (return 시 카운터 변화)

#### RETURN_ITEM (반품 요청)

[packages/modules/order/src/utils/actions/return-item.ts:9-64](packages/modules/order/src/utils/actions/return-item.ts#L9-L64)

- **operation**: `existing.detail.return_requested_quantity += action.details.quantity`
- **validate**: `fulfilled_quantity - return_requested_quantity >= 요청수량`

#### RECEIVE_RETURN_ITEM (반품 정상 입고)

[packages/modules/order/src/utils/actions/receive-return-item.ts:9-69](packages/modules/order/src/utils/actions/receive-return-item.ts#L9-L69)

- **operation**:
  - `return_received_quantity += quantity`
  - `return_requested_quantity -= quantity` (요청에서 수령으로 옮김)

#### RECEIVE_DAMAGED_RETURN_ITEM (파손 입고)

`return_dismissed_quantity` 만 증가. 재고 복원 대상에서 제외.

이 모든 변경은 `calculate-order-change.ts:58` 의 **메모리상 deep clone** 위에서 이루어진다. 결과는 `applyChangesToOrder` 의 upsert 페이로드로 흘러간다.

### 4. 반품 흐름과 OrderChange 의 짝짓기

[packages/modules/order/src/services/actions/create-return.ts:132-165](packages/modules/order/src/services/actions/create-return.ts#L132-L165) — `RETURN_ITEM` 액션 + change 생성 후 즉시 `confirmOrderChange` 호출. ⇒ **반품 요청 단계에서 이미 version +1**.

[packages/modules/order/src/services/actions/receive-return.ts:79-117](packages/modules/order/src/services/actions/receive-return.ts#L79-L117) — `RECEIVE_RETURN_ITEM` 액션 + change 생성 후 즉시 confirm. ⇒ **수령 확정 단계에서 또 version +1**.

따라서 한 번의 반품 사이클(요청 → 수령) 만으로도 **version 이 2 번 증가**할 수 있다.

### 5. 주문 조회

#### Route → Workflow

[packages/medusa/src/api/admin/orders/[id]/route.ts:12-28](packages/medusa/src/api/admin/orders/[id]/route.ts#L12-L28)

```ts
GET → getOrderDetailWorkflow.run({
  fields: req.queryConfig.fields,
  order_id: req.params.id,
  version: req.validatedQuery.version, // optional
})
```

#### Workflow

[packages/core/core-flows/src/order/workflows/get-order-detail.ts:71-112](packages/core/core-flows/src/order/workflows/get-order-detail.ts#L71-L112)

- 필드 augmentation: `id`, `status`, `version`, `payment_collections.*`, `fulfillments.*` 강제 포함.
- 필터 머지: `{ id: order_id, version }` → `useQueryGraphStep(entity: "order", filters)`.
- `version` 미지정 시 OrderItem.version 필터 없음 → **모든 버전의 OrderItem 이 함께 반환**.

#### Service & 머지

[packages/modules/order/src/services/order-module-service.ts:434-456](packages/modules/order/src/services/order-module-service.ts#L434-L456) → `retrieveOrder` → `formatOrder`.

[packages/modules/order/src/utils/transform-order.ts:37-63](packages/modules/order/src/utils/transform-order.ts#L37-L63):

각 OrderItem 행마다:
1. `detail` 필드를 `OrderItem` 자체 (수량 카운터들) 로 채움.
2. 머지된 결과는 `OrderLineItem` 의 카탈로그 데이터를 베이스로, 그 위에 `OrderItem` 의 `quantity`/`unit_price`/`metadata` 를 덮어씌움.

응답 모양:
```
items: [
  { id, title, variant_id, ...,            // ← OrderLineItem
    quantity, unit_price,                   // ← OrderItem
    detail: {                                // ← OrderItem 카운터들
      version,
      fulfilled_quantity,
      return_requested_quantity,
      return_received_quantity,
      return_dismissed_quantity,
      ...
    }
  }, ...
]
```

#### "최종 상태" 의 의미

`version` 미지정 호출에서 같은 `item_id` 에 대해 **여러 OrderItem 행이 노출**될 수 있다. 각 행의 `detail.version` 으로 어느 시점의 스냅샷인지 식별한다. UI 상 "현재 상태" 는 보통 `version === order.version` 인 행이다.

명시적으로 단일 시점만 보고 싶다면 `?version=N` 쿼리로 그 버전만 받는다. `OrderService.retrieveOrderVersion` 이 동일 패턴의 보조 진입점 ([order-service.ts:36-58](packages/modules/order/src/services/order-service.ts#L36-L58)).

## Code References

- `packages/modules/order/src/models/order-item.ts:8-54` — OrderItem 필드 + (order_id, version) 인덱스
- `packages/modules/order/src/models/line-item.ts` — OrderLineItem (version 없음)
- `packages/modules/order/src/models/order.ts:17` — `Order.version` default 1
- `packages/modules/order/src/models/order-summary.ts:11-25` — OrderSummary (버전별 총액 스냅샷)
- `packages/modules/order/src/services/order-module-service.ts:2522-2536` — OrderChange 생성 시 `version + 1`
- `packages/modules/order/src/services/order-module-service.ts:2811-2848` — `confirmOrderChange_`
- `packages/modules/order/src/services/order-module-service.ts:3591-3708` — `applyOrderChanges_`
- `packages/modules/order/src/utils/apply-order-changes.ts:61,84-101,191` — version 결정 + upsert 분기 + Order.version 업데이트
- `packages/modules/order/src/utils/actions/return-item.ts:9-64` — RETURN_ITEM 핸들러
- `packages/modules/order/src/utils/actions/receive-return-item.ts:9-69` — RECEIVE_RETURN_ITEM 핸들러
- `packages/modules/order/src/services/actions/create-return.ts:132-165` — 반품 요청 시 change 생성 + confirm
- `packages/modules/order/src/services/actions/receive-return.ts:79-117` — 반품 수령 시 change 생성 + confirm
- `packages/medusa/src/api/admin/orders/[id]/route.ts:12-28` — 주문 상세 라우트
- `packages/core/core-flows/src/order/workflows/get-order-detail.ts:71-112` — getOrderDetailWorkflow
- `packages/modules/order/src/utils/transform-order.ts:37-63` — formatOrder (OrderItem ⨝ OrderLineItem)
- `packages/modules/order/src/utils/transform-order.ts:199-281` — mapRepositoryToOrderModel (필드 경로 매핑)
- `packages/modules/order/src/services/order-service.ts:36-58` — `retrieveOrderVersion` (단일 버전 명시 조회 진입점)

## Architecture Documentation

**Append-only snapshot 방식**: OrderItem 행은 동일 (order_id, item_id) 에 대해 version 별로 누적된다. 갱신은 in-place UPDATE 가 아니라 새 row INSERT 를 우선한다. `Order.version` 이 "공식 현재 시점" 을 가리키는 포인터 역할.

**OrderChange 가 단일 변경 단위**: 모든 mutation (반품, 교환, 주문 편집) 은 OrderChange + OrderChangeAction 으로 표현되고, confirm 시점에 한꺼번에 적용된다.

**조회 시 version 필터는 옵셔널**: 명시 안 하면 모든 버전의 OrderItem 이 응답에 포함된다. UI/클라이언트가 `detail.version` 을 보고 "현재" vs "과거" 를 구분한다.

**OrderLineItem 은 불변**: 카탈로그 데이터 자체는 한번 박제되며 버전을 갖지 않음. 가격/수량 변경은 OrderItem 쪽에서만 일어난다.

## Related Research

(없음)

## Open Questions

- `OrderItem` 에 `(order_id, version, item_id)` unique 제약이 없는데, 동시성 환경에서 같은 (order_id, version, item_id) 행이 두 개 만들어질 가능성은 어떻게 차단되는지(애플리케이션 레벨 보장만으로 충분한가?). — 본 조사 범위에서는 해당 동시성 가드 코드를 직접 검증하지 못함.
- Admin UI 대시보드가 OrderItem 의 이전 버전 행을 사용자에게 노출하는지, 아니면 최신 버전만 필터링해서 보여주는지 (이 부분은 admin/dashboard 패키지를 별도 조사해야 확인 가능).
