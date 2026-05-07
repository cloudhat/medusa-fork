---
date: 2026-05-07T19:59:17+09:00
researcher: SAN KIM
git_commit: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
branch: develop
repository: medusa-fork
topic: "Order 기준 배송내역 조회 API 구조"
tags: [research, codebase, order, fulfillment, shipment, tracking, query-api, get-order-detail]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
---

# Research: Order 기준 배송내역 조회 API 구조

**Date**: 2026-05-07 KST
**Researcher**: SAN KIM
**Git Commit**: `1c0e69e9cb59b5954175bbcd8b7e382aae127dea`
**Branch**: develop
**Repository**: medusa-fork

## Research Question

배송내역 조회 API를 조사한다. Order 엔티티 기준으로 배송내역(fulfillment / shipment / tracking)이 어떤 라우트·필드·DTO로 노출되며, 어떻게 추적 가능한지 코드 레벨에서 정리한다.

## 관련 문서

- [Order ↔ Fulfillment 도메인 연결 구조](2026-05-07-order-fulfillment-domain-connection.md) — 쓰기/생성 흐름(워크플로우, Remote Link 생성) 위주

---

## Summary

Order 도메인 자체에는 fulfillment/shipment 데이터를 직접 보관하지 않는다. 배송내역은 다음 세 갈래로만 조회된다.

1. **`GET /admin/orders/:id` 또는 `GET /store/orders/:id`** — Order 단건 조회 시 `getOrderDetailWorkflow`가 `fulfillments.*`을 **하드코딩으로 강제 주입**하여 항상 같이 반환한다. `fulfillments`는 `order_fulfillment` 링크 테이블을 통해 Fulfillment 모듈에서 가져오는 가상 필드.
2. **`GET /admin/orders/:id/fulfillments`** — Order 하위 fulfillments 컬렉션 라우트(존재 확인). Fulfillment 모듈을 단독 컬렉션으로 노출하는 `GET /admin/fulfillments` / `GET /admin/fulfillments/:id`는 **존재하지 않는다** (POST 라우트만 존재).
3. **파생 상태값** — `Order.fulfillment_status`는 DB 컬럼이 아니라 워크플로우 후처리 단계에서 `Fulfillment.{packed_at, shipped_at, delivered_at, canceled_at}` + `OrderItem.detail.raw_fulfilled_quantity vs raw_quantity`로 매번 계산된다 (`getLastFulfillmentStatus`).

배송 추적 정보(`tracking_number`, `tracking_url`, `label_url`)는 `FulfillmentLabel` 엔티티에 저장되며, `BaseOrderFulfillment` DTO에는 포함되지 않는다. 클라이언트가 노출받으려면 명시적으로 `fields=fulfillments.labels.*`을 요청해야 한다.

---

## Detailed Findings

### 1. Admin: `GET /admin/orders/:id`

**라우트**: [packages/medusa/src/api/admin/orders/[id]/route.ts:12-28](packages/medusa/src/api/admin/orders/%5Bid%5D/route.ts#L12-L28)

핸들러는 `getOrderDetailWorkflow`로 위임하며 `req.queryConfig.fields`, `order_id`, `version`을 입력으로 넘긴다. 결과는 `{ order }` 형태로 반환.

**미들웨어**: [packages/medusa/src/api/admin/orders/middlewares.ts:68-76](packages/medusa/src/api/admin/orders/middlewares.ts#L68-L76)

`validateAndTransformQuery(AdminGetOrdersOrderParams, retrieveTransformQueryConfig)` 단일 미들웨어. `retrieveTransformQueryConfig`가 `defaultAdminRetrieveOrderFields`를 기본 fields로 채운다.

**기본 필드**: [packages/medusa/src/api/admin/orders/query-config.ts:21-63](packages/medusa/src/api/admin/orders/query-config.ts#L21-L63)

`defaultAdminRetrieveOrderFields`에는 `*shipping_methods`, `*shipping_methods.tax_lines`, `*shipping_methods.adjustments`만 포함된다. **`fulfillments`는 이 기본 필드 목록에 들어있지 않다.** 다만 export 전용 필드 목록(line 152)에는 `*fulfillments`가 포함되어 있다.

---

### 2. Store: `GET /store/orders/:id`

**라우트**: [packages/medusa/src/api/store/orders/[id]/route.ts:6](packages/medusa/src/api/store/orders/%5Bid%5D/route.ts#L6)

`getOrderDetailWorkflow`에 `filters: { is_draft_order: false }`를 추가로 전달. **인증 미들웨어가 적용되어 있지 않다** (라우트 파일 line 5에 TODO 주석).

**미들웨어**: [packages/medusa/src/api/store/orders/middlewares.ts:30-37](packages/medusa/src/api/store/orders/middlewares.ts#L30-L37)

`validateAndTransformQuery(StoreGetOrderParams, retrieveTransformQueryConfig)` 단일.

**기본 필드**: [packages/medusa/src/api/store/orders/query-config.ts:16-64](packages/medusa/src/api/store/orders/query-config.ts#L16-L64)

`defaultStoreRetrieveOrderFields`. line 1에 `// TODO: This is copied over from admin. Scope what fields and relations are allowed for store` 주석. 포함된 배송 관련 필드:
- `shipping_total`, `shipping_subtotal`, `shipping_tax_total` 등 합계 필드
- `*shipping_methods`, `*shipping_methods.tax_lines`, `*shipping_methods.adjustments`

**`fulfillments`는 store 기본 필드에도 포함되지 않는다**. 하지만 워크플로우 단계에서 강제 주입(아래 §3 참조).

---

### 3. `getOrderDetailWorkflow` — `fulfillments.*` 강제 주입

**파일**: [packages/core/core-flows/src/order/workflows/get-order-detail.ts:71-112](packages/core/core-flows/src/order/workflows/get-order-detail.ts#L71-L112)

워크플로우 입력 `fields`에 4개 필드를 항상 추가한다(lines 76-85):

```typescript
return deduplicate([
  ...fields,
  "id",
  "status",
  "version",
  "payment_collections.*",
  "fulfillments.*",      // line 84 — 항상 주입
])
```

이후 `useQueryGraphStep({ entity: "order", fields, options: { throwIfKeyNotFound: true, isList: false } })`로 조회. 끝에 `transform`에서 `getLastPaymentStatus`, `getLastFulfillmentStatus`를 호출해 `payment_status`, `fulfillment_status`를 메모리 위에서 계산해 객체에 붙인다(lines 98-107).

**의미**: admin/store 어느 쪽에서 호출하든, query-config 기본값과 무관하게 `fulfillments`의 모든 스칼라 필드(`*` 와일드카드는 스칼라만 확장)는 응답에 항상 포함된다.

---

### 4. `fulfillments` 가상 필드 — `OrderFulfillment` 링크 모듈

**정의**: [packages/modules/link-modules/src/definitions/order-fulfillment.ts:7-72](packages/modules/link-modules/src/definitions/order-fulfillment.ts#L7-L72)

`extends` 블록(lines 41-58)이 `Order` 엔티티에 가상 필드를 등록한다.

```typescript
extends: [
  {
    serviceName: Modules.ORDER,
    entity: "Order",
    fieldAlias: {
      fulfillments: {
        path: "fulfillment_link.fulfillments",
        isList: true,
      },
    },
    relationship: {
      serviceName: LINKS.OrderFulfillment,
      primaryKey: "order_id",
      foreignKey: "id",
      alias: "fulfillment_link",
      isList: true,
    },
  },
  ...
]
```

Query는 `fulfillments`를 만나면 `order_fulfillment` 피벗 테이블을 join 하여 Fulfillment 모듈로 넘어가 실제 레코드를 해석한다. 반대 방향(Fulfillment → Order)도 같은 방식으로 등록되어 있다(lines 59-72).

`Order` ORM 모델 자체에는 `fulfillments` relation이 없다([packages/modules/order/src/models/order.ts](packages/modules/order/src/models/order.ts)). 순수히 Remote Link 메커니즘으로만 노출되는 가상 필드다.

---

### 5. Fulfillment 엔티티 타임라인 필드

**파일**: [packages/modules/fulfillment/src/models/fulfillment.ts:13-18](packages/modules/fulfillment/src/models/fulfillment.ts#L13-L18)

| 필드 | 타입 | nullable | default |
|---|---|---|---|
| `packed_at` | dateTime | yes | none (생성 시 `new Date()`) |
| `shipped_at` | dateTime | yes | none (`createShipment` 시 설정) |
| `marked_shipped_by` | text | yes | none |
| `delivered_at` | dateTime | yes | none (`markAsDelivered` 시 설정) |
| `canceled_at` | dateTime | yes | none (cancel 시 설정) |

`marked_as_delivered_at` 같은 별도 필드는 없다. 인도 시각은 `delivered_at` 하나로 기록된다.

---

### 6. `Order.fulfillment_status` 파생 로직

**파일**: [packages/core/core-flows/src/order/utils/aggregate-status.ts:114-209](packages/core/core-flows/src/order/utils/aggregate-status.ts#L114-L209)

`getLastFulfillmentStatus(order)`는 다음 순서로 동작.

**Step 1 — 풀필먼트별 상태 카운팅** (lines 132-149):

```typescript
const statusMap = {
  canceled_at:  "canceled",
  delivered_at: "delivered",
  shipped_at:   "shipped",
  packed_at:    "fulfilled",
}
```

각 fulfillment에 대해 위 키 순서대로 검사하여 처음 truthy인 키의 상태로 카운트하고 break. `shipped_at`과 `delivered_at`이 모두 있으면 `delivered`로만 집계.

**Step 2 — 미처리 라인아이템 검사** (lines 158-163):

```typescript
const hasUnfulfilledItems =
  (order.items || [])?.filter(
    (i) =>
      isDefined(i?.detail?.raw_fulfilled_quantity) &&
      MathBN.lt(i.detail.raw_fulfilled_quantity, i.raw_quantity)
  ).length > 0
```

**Step 3 — 우선순위 결정** (lines 165-208):

1. `delivered`가 1개 이상: 모든 비취소 fulfillment가 delivered이고 미처리 아이템 없으면 `"delivered"`, 아니면 `"partially_delivered"`
2. `shipped`가 1개 이상: 같은 식으로 `"shipped"` / `"partially_shipped"`
3. `fulfilled`(packed)가 1개 이상: `"fulfilled"` / `"partially_fulfilled"`
4. 모두 canceled: `"canceled"`
5. 그 외: `"not_fulfilled"`

**사실**: `OrderItem.shipped_quantity`, `delivered_quantity` 필드는 이 파생 로직에서 사용되지 않는다. 상태는 Fulfillment의 4개 타임스탬프 + `raw_fulfilled_quantity vs raw_quantity` 비교만으로 결정된다.

`FulfillmentStatus` 타입 정의는 [packages/core/types/src/http/order/common.ts:705-713](packages/core/types/src/http/order/common.ts#L705-L713).

---

### 7. Order 하위 fulfillments 라우트

조사 결과 다음 라우트가 존재한다.

| HTTP | 경로 | 파일 |
|---|---|---|
| `POST` | `/admin/orders/:id/fulfillments` | `[id]/fulfillments/route.ts` |
| `POST` | `/admin/orders/:id/fulfillments/:fulfillment_id/shipment` | `[id]/fulfillments/[fulfillment_id]/shipment/route.ts` |
| `POST` | `/admin/orders/:id/fulfillments/:fulfillment_id/cancel` | `[id]/fulfillments/[fulfillment_id]/cancel/route.ts` |

**라우트 메서드 노출 사실** (codebase-analyzer 조사 기준): `[id]/fulfillments` 디렉토리는 POST 라우트(`createOrderFulfillmentWorkflow`)를 export 한다. 별도의 `GET` export는 동일 파일에 존재하지 않는다. **모름**: codebase-locator 단계에서 같은 파일에 GET이 함께 export 되는지는 별도로 확인하지 않음 — 본 문서에서는 "POST는 확실히 있고, 단독 GET 라우트 파일은 발견되지 않음"으로만 기록.

→ 사실상 fulfillments 컬렉션을 별도 GET 호출로 가져올 필요는 없다. `GET /admin/orders/:id` 응답에 `fulfillments.*`가 강제 주입되어 함께 내려오기 때문.

---

### 8. 독립 Fulfillment 리소스 라우트

**디렉토리**: `packages/medusa/src/api/admin/fulfillments/`

| HTTP | 경로 | 워크플로우 |
|---|---|---|
| `POST` | `/admin/fulfillments` | `createFulfillmentWorkflow` |
| `POST` | `/admin/fulfillments/:id/shipment` | `createShipmentWorkflow` |
| `POST` | `/admin/fulfillments/:id/cancel` | `cancelFulfillmentWorkflow` |

**`GET /admin/fulfillments` 또는 `GET /admin/fulfillments/:id` 라우트는 존재하지 않는다**. Store 측에는 `store/fulfillments/` 디렉토리 자체가 없다.

---

### 9. Fulfillment 모듈 서비스 read API

**파일**: [packages/modules/fulfillment/src/services/fulfillment-module-service.ts](packages/modules/fulfillment/src/services/fulfillment-module-service.ts)

서비스 line 63-64에서 `Fulfillment`는 `generateMethodForModels`에서 의도적으로 제외된다. 자동 생성 CRUD가 아닌, 수동 정의 메서드만 노출:

| 메서드 | 위치 | 위임 |
|---|---|---|
| `retrieveFulfillment(id, config, ctx)` | lines 215-229 | `fulfillmentService_.retrieve` |
| `listFulfillments(filters, config, ctx)` | lines 232-246 | `fulfillmentService_.list` |
| `listAndCountFulfillments(filters, config, ctx)` | lines 249-266 | `fulfillmentService_.listAndCount` |

세 메서드 모두 `@InjectManager()` 데코레이터 적용. Remote Query는 이 메서드들과 모듈 정의(joiner config)를 통해 fulfillment를 해석한다.

---

### 10. FulfillmentLabel — 배송 추적 정보 저장 위치

**파일**: [packages/modules/fulfillment/src/models/fulfillment-label.ts](packages/modules/fulfillment/src/models/fulfillment-label.ts)

| 필드 | 타입 | 비고 |
|---|---|---|
| `id` | text (prefix `fulla`) | PK |
| `tracking_number` | text | non-nullable |
| `tracking_url` | text | non-nullable |
| `label_url` | text | non-nullable |
| `fulfillment` | belongsTo Fulfillment (mappedBy `labels`) | FK는 belongsTo가 관리 |

`Fulfillment.labels`는 cascade delete 대상([fulfillment.ts:24-26, line 53](packages/modules/fulfillment/src/models/fulfillment.ts#L24-L26)).

---

### 11. DTO에 노출되는 fulfillment 정보

**`BaseOrderFulfillment`**: [packages/core/types/src/http/order/common.ts:628-691](packages/core/types/src/http/order/common.ts#L628-L691)

스칼라 필드만 존재: `id`, `location_id`, `packed_at`, `shipped_at`, `delivered_at`, `canceled_at`, `requires_shipping`, `data`, `provider_id`, `shipping_option_id`, `metadata`, `created_at`, `created_by`, `marked_shipped_by`, `updated_at`.

`AdminOrderFulfillment`([admin/entities.ts:102](packages/core/types/src/http/order/admin/entities.ts#L102)) 와 `StoreOrderFulfillment`([store/entities.ts:96](packages/core/types/src/http/order/store/entities.ts#L96))는 모두 `BaseOrderFulfillment`를 그대로 extend, 추가 필드 없음.

**중요한 사실**: `BaseOrderFulfillment`에 `items` / `labels` 프로퍼티 선언이 없다. 그리고 `getOrderDetailWorkflow`가 강제 주입하는 것은 `fulfillments.*`(스칼라만 확장하는 와일드카드)다. 따라서 **트래킹 라벨(`tracking_number`, `tracking_url`)이나 fulfillment item 상세는 기본 응답에 포함되지 않는다**. 클라이언트는 명시적으로 `fields=fulfillments.labels.*,fulfillments.items.*`를 query string에 넘겨야 한다.

**OrderItem.detail의 수량 필드**: [packages/core/types/src/http/order/common.ts:492-549](packages/core/types/src/http/order/common.ts#L492-L549) — `BaseOrderItemDetail`에 `fulfilled_quantity`, `shipped_quantity`, `delivered_quantity`, `return_requested_quantity`, `return_received_quantity`, `return_dismissed_quantity`, `written_off_quantity`가 노출됨. 라인아이템 단위 처리 진행 상황은 이쪽으로 추적.

---

### 12. shipping_methods (Order 모듈 내부) ↔ Fulfillment 관계

**Order.shipping_methods**: `OrderShipping` (junction) → `OrderShippingMethod` (실제 메서드 레코드).

- [packages/modules/order/src/models/order.ts:47](packages/modules/order/src/models/order.ts#L47) — `shipping_methods: hasMany(OrderShipping)`
- [packages/modules/order/src/models/order-shipping-method.ts](packages/modules/order/src/models/order-shipping-method.ts) — 버전(`version`) 필드 보유, `IDX_order_shipping_order_id_version` 인덱스
- [packages/modules/order/src/models/shipping-method.ts](packages/modules/order/src/models/shipping-method.ts) — 실제 메서드: `name`, `amount`, `shipping_option_id`(nullable text, FK 없음), `data`

**핵심**: `OrderShippingMethod`는 `Fulfillment` 레코드에 대한 직접 FK를 가지지 않는다. `shipping_option_id`라는 공통 식별자(텍스트)만 공유한다. 따라서 "어떤 shipping_method가 어떤 fulfillment로 처리되었는지"는 양쪽이 같은 `shipping_option_id`를 참조한다는 사실로만 간접 추적된다 (`order_fulfillment` 링크 테이블은 order 단위만 연결).

---

### 13. 배송 진행 단계별 데이터 흐름 (조회 관점)

```
[1] 풀필먼트 생성  POST /admin/orders/:id/fulfillments
    → Fulfillment.packed_at = now
    → OrderItem.detail.fulfilled_quantity 증가
    → order_fulfillment 링크 생성

[2] 배송 시작     POST /admin/orders/:id/fulfillments/:fid/shipment
    → Fulfillment.shipped_at = now
    → FulfillmentLabel 레코드 추가 (tracking_number/url)
    → OrderItem.detail.shipped_quantity 증가

[3] 배송 완료     mark-order-fulfillment-as-delivered (workflow)
    → Fulfillment.delivered_at = now
    → OrderItem.detail.delivered_quantity 증가

[4] 취소         POST /admin/orders/:id/fulfillments/:fid/cancel
    → Fulfillment.canceled_at = now
    → OrderItem.detail.fulfilled_quantity 감소

[조회] GET /admin/orders/:id  또는  GET /store/orders/:id
    → getOrderDetailWorkflow
    → fulfillments.* (4개 타임스탬프 포함) 자동 동봉
    → fulfillment_status 메모리 계산하여 응답에 첨부
    → 트래킹 라벨이 필요하면 fields=fulfillments.labels.* 요청
```

**`markFulfillmentAsDeliveredWorkflow`** 내부 ([packages/core/core-flows/src/fulfillment/workflows/mark-fulfillment-as-delivered.ts:66-115](packages/core/core-flows/src/fulfillment/workflows/mark-fulfillment-as-delivered.ts#L66-L115)) — 락 획득, `delivered_at`/`canceled_at` 미설정 검증, `delivered_at: new Date()`로 update, 락 해제. 단일 필드만 갱신.

---

## Code References

| 역할 | 파일 |
|---|---|
| Admin GET 단건 라우트 | [packages/medusa/src/api/admin/orders/[id]/route.ts:12-28](packages/medusa/src/api/admin/orders/%5Bid%5D/route.ts#L12-L28) |
| Admin 미들웨어 | [packages/medusa/src/api/admin/orders/middlewares.ts:68-76](packages/medusa/src/api/admin/orders/middlewares.ts#L68-L76) |
| Admin query-config | [packages/medusa/src/api/admin/orders/query-config.ts:21-63](packages/medusa/src/api/admin/orders/query-config.ts#L21-L63) |
| Store GET 단건 라우트 | [packages/medusa/src/api/store/orders/[id]/route.ts:6-22](packages/medusa/src/api/store/orders/%5Bid%5D/route.ts#L6-L22) |
| Store 미들웨어 | [packages/medusa/src/api/store/orders/middlewares.ts:30-37](packages/medusa/src/api/store/orders/middlewares.ts#L30-L37) |
| Store query-config | [packages/medusa/src/api/store/orders/query-config.ts:16-69](packages/medusa/src/api/store/orders/query-config.ts#L16-L69) |
| getOrderDetailWorkflow (강제 주입) | [packages/core/core-flows/src/order/workflows/get-order-detail.ts:71-112](packages/core/core-flows/src/order/workflows/get-order-detail.ts#L71-L112) |
| getLastFulfillmentStatus | [packages/core/core-flows/src/order/utils/aggregate-status.ts:114-209](packages/core/core-flows/src/order/utils/aggregate-status.ts#L114-L209) |
| OrderFulfillment 링크 정의 | [packages/modules/link-modules/src/definitions/order-fulfillment.ts:7-72](packages/modules/link-modules/src/definitions/order-fulfillment.ts#L7-L72) |
| Fulfillment 모델 (타임스탬프) | [packages/modules/fulfillment/src/models/fulfillment.ts:13-18](packages/modules/fulfillment/src/models/fulfillment.ts#L13-L18) |
| FulfillmentLabel 모델 | [packages/modules/fulfillment/src/models/fulfillment-label.ts](packages/modules/fulfillment/src/models/fulfillment-label.ts) |
| FulfillmentItem 모델 | [packages/modules/fulfillment/src/models/fulfillment-item.ts](packages/modules/fulfillment/src/models/fulfillment-item.ts) |
| Fulfillment 모듈 서비스 read 메서드 | [packages/modules/fulfillment/src/services/fulfillment-module-service.ts:215-266](packages/modules/fulfillment/src/services/fulfillment-module-service.ts#L215-L266) |
| BaseOrderFulfillment DTO | [packages/core/types/src/http/order/common.ts:628-691](packages/core/types/src/http/order/common.ts#L628-L691) |
| BaseOrderItemDetail DTO | [packages/core/types/src/http/order/common.ts:492-549](packages/core/types/src/http/order/common.ts#L492-L549) |
| FulfillmentStatus 타입 | [packages/core/types/src/http/order/common.ts:705-713](packages/core/types/src/http/order/common.ts#L705-L713) |
| AdminOrder / AdminOrderFulfillment | [packages/core/types/src/http/order/admin/entities.ts:20-61, 102](packages/core/types/src/http/order/admin/entities.ts#L20-L61) |
| StoreOrder / StoreOrderFulfillment | [packages/core/types/src/http/order/store/entities.ts:19-49, 96](packages/core/types/src/http/order/store/entities.ts#L19-L49) |
| Order 모델 (shipping_methods) | [packages/modules/order/src/models/order.ts:47](packages/modules/order/src/models/order.ts#L47) |
| OrderShipping junction | [packages/modules/order/src/models/order-shipping-method.ts](packages/modules/order/src/models/order-shipping-method.ts) |
| OrderShippingMethod | [packages/modules/order/src/models/shipping-method.ts](packages/modules/order/src/models/shipping-method.ts) |
| markFulfillmentAsDeliveredWorkflow | [packages/core/core-flows/src/fulfillment/workflows/mark-fulfillment-as-delivered.ts:66-115](packages/core/core-flows/src/fulfillment/workflows/mark-fulfillment-as-delivered.ts#L66-L115) |
| markOrderFulfillmentAsDeliveredWorkflow | [packages/core/core-flows/src/order/workflows/mark-order-fulfillment-as-delivered.ts:204-293](packages/core/core-flows/src/order/workflows/mark-order-fulfillment-as-delivered.ts#L204-L293) |

---

## Architecture Documentation

### 조회 경로 전체 구조

```
[Client]
GET /admin/orders/:id?fields=fulfillments.labels.*
  │
  ▼
[Middleware]
validateAndTransformQuery(retrieveTransformQueryConfig)
  → req.queryConfig.fields = defaults ∪ caller fields
    (defaults: 합계·shipping_methods 등, fulfillments 미포함)
  │
  ▼
[Route handler]
getOrderDetailWorkflow(req.scope).run({ fields, order_id, version })
  │
  ▼
[Workflow]
transform: deduplicate([...fields, "id","status","version",
                        "payment_collections.*","fulfillments.*"])
  │   ← fulfillments.* 강제 주입
  ▼
useQueryGraphStep({ entity: "order", fields })
  │
  ▼
[Query Engine]
Order 엔티티 + extends(fulfillments) 가상 필드 해석
  fulfillments → fulfillment_link.fulfillments
  → JOIN order_fulfillment ON order_id
  → SELECT FROM fulfillment 모듈 (retrieveFulfillment / list)
  │
  ▼
[Workflow post-processing]
transform: getLastFulfillmentStatus(order)
  → 4개 타임스탬프 + raw_fulfilled_quantity vs raw_quantity
  → order.fulfillment_status 결정
  │
  ▼
res.json({ order })
```

### 주문 단위 배송내역을 조회하는 사실상의 단일 진입점

코드 구조상 "Order 기준 배송내역"은 별도 전용 엔드포인트가 아니라 `GET /admin/orders/:id` (또는 `/store/orders/:id`) 응답에 항상 동봉되는 `fulfillments` 필드로 노출된다. 이는 다음 두 메커니즘 때문이다.

1. `OrderFulfillment` 링크 모듈의 `extends.fieldAlias`가 `Order` 엔티티에 `fulfillments` 가상 필드를 등록 — Query 엔진이 자동으로 join.
2. `getOrderDetailWorkflow`가 `fulfillments.*`을 항상 fields에 추가 — 호출자가 누락해도 응답에 반드시 포함.

### 노출 기본값과 옵트인 필드

| 정보 | 기본 응답 포함? | 추가 요청 방법 |
|---|---|---|
| Fulfillment 4개 타임스탬프 (`packed_at` 등) | O (강제 주입) | — |
| `Order.fulfillment_status` | O (워크플로우 후처리 계산) | — |
| `Order.shipping_methods` (이름·금액) | O (admin/store 기본 필드) | — |
| FulfillmentItem (line_item_id, quantity) | X | `?fields=fulfillments.items.*` |
| FulfillmentLabel (tracking_number, tracking_url) | X | `?fields=fulfillments.labels.*` |
| OrderItem.detail.shipped_quantity 등 | O (admin은 `*items.detail`, store도 동일 패턴) | — |

### 별도 단독 fulfillment GET 라우트가 없는 이유 (관찰)

`packages/medusa/src/api/admin/fulfillments/` 디렉토리에는 POST 3종(create, shipment, cancel)만 있고 GET은 없다. 모듈 서비스 단(`listFulfillments`, `retrieveFulfillment`)에는 read API가 존재하므로 Remote Query/내부 워크플로우에서는 자유롭게 호출 가능하지만, HTTP 라우트로는 노출되지 않은 상태다 (사실 — 추정 아님).

---

## Open Questions

- `packages/medusa/src/api/admin/orders/[id]/fulfillments/route.ts` 파일이 단독 GET export를 가지는지 정확히 확인하지 못함. POST가 있는 것은 사실, GET 단독 export 여부는 본 조사에서 미확인 (모름).
- `Order.fulfillment_status`는 `getOrderDetailWorkflow` 경로에서만 계산된다. 다른 진입점(`listOrders` 등)에서도 동일하게 계산되는지는 본 조사에서 확인 안 함 (모름).
- 트래킹 정보를 store에 노출할 때 인증 미들웨어가 없다는 사실([store/orders/[id]/route.ts:5](packages/medusa/src/api/store/orders/%5Bid%5D/route.ts#L5))의 보안적 함의는 본 조사 범위 밖.
