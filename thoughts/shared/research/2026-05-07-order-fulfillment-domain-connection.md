---
date: 2026-05-07T00:00:00+09:00
researcher: SAN KIM
git_commit: 1c0e69e9cb59b5954175bbcd8b7e382aae127dea
branch: develop
repository: medusa-fork
topic: "주문(Order) 도메인과 배송(Fulfillment) 도메인의 연결 구조"
tags: [research, codebase, order, fulfillment, return, exchange, claim, workflow, remote-link, inventory]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
last_updated_note: "Follow-up: 일반 발송과 교체 발송(outbound) Fulfillment 구분 방법 추가"
---

# Research: 주문(Order) 도메인과 배송(Fulfillment) 도메인의 연결 구조

**Date**: 2026-05-07 KST  
**Researcher**: SAN KIM  
**Git Commit**: `1c0e69e9cb59b5954175bbcd8b7e382aae127dea`  
**Branch**: develop  
**Repository**: medusa-fork

## Research Question

참고자료/사용자 여정 분석/09-풀필먼트-배송처리/README.md를 기반으로, 주문(Order) 도메인과 배송(Fulfillment) 도메인이 코드레벨에서 어떻게 연결되어 있는지 조사.

## 관련 문서

- [09-풀필먼트-배송처리 README](../../참고자료/사용자%20여정%20분석/09-풀필먼트-배송처리/README.md)

---

## Summary

Order 도메인과 Fulfillment 도메인은 **서로 직접적인 의존성이 없는 독립 모듈**이다. 두 도메인의 연결은 세 가지 계층에서 이루어진다.

1. **워크플로우 계층** (`packages/core/core-flows/src/order/workflows/`) — 두 모듈 서비스를 순서대로 호출하고 결과를 조율한다.
2. **Remote Link** (`order_fulfillment` 테이블) — 두 모듈의 레코드를 피벗 테이블로 연결한다.
3. **이벤트** (`event-bus`) — 워크플로우 완료 후 이벤트를 발행하여 외부 구독자에게 상태 변경을 알린다.

Order 모듈은 Fulfillment 상태를 자체 엔티티 없이 `OrderItem`의 수량 필드(`fulfilled_quantity`, `shipped_quantity`, `delivered_quantity`)로만 추적한다. Fulfillment 모듈은 물류 레코드(`Fulfillment`, `FulfillmentItem`, `FulfillmentLabel`)와 외부 프로바이더 호출을 담당한다.

---

## Detailed Findings

### 1. 도메인 경계와 책임

| 모듈 | 역할 | 주요 엔티티 |
|---|---|---|
| **Order 모듈** | 주문 내 아이템의 처리 수량 추적 | `OrderItem` (수량 필드들), `OrderChange`, `OrderChangeAction` |
| **Fulfillment 모듈** | 물류 레코드 관리, 외부 프로바이더 연동 | `Fulfillment`, `FulfillmentItem`, `FulfillmentLabel` |
| **Link 모듈** | 두 모듈 레코드 연결 | `order_fulfillment` 피벗 테이블 |
| **Inventory 모듈** | 실물 재고 수량 차감 및 예약 관리 | `InventoryLevel`, `ReservationItem` |

Order 모듈에는 `OrderFulfillment` 별도 엔티티가 없다. Fulfillment 연결 여부는 `OrderItem.fulfilled_quantity > 0`으로만 판단한다.

---

### 2. Remote Link: ORDER ↔ FULFILLMENT

**링크 정의 파일**: [packages/modules/link-modules/src/definitions/order-fulfillment.ts](packages/modules/link-modules/src/definitions/order-fulfillment.ts)

```
피벗 테이블: order_fulfillment
idPrefix: ordful
primaryKeys: [id, order_id, fulfillment_id]
```

**관계 설정**:
- `ORDER.id` ← `order_fulfillment.order_id` → `FULFILLMENT.id`
- `Order` 엔티티에 `fulfillments` 가상 필드 노출 (hasMany)
- `Fulfillment` 엔티티에 `order` 가상 필드 노출

**LINKS 상수**: [packages/core/utils/src/link/links.ts:107-112](packages/core/utils/src/link/links.ts#L107-L112)
```typescript
OrderFulfillment: composeLinkName(
  Modules.ORDER, "order_id",
  Modules.FULFILLMENT, "fulfillment_id"
)
```

링크는 `createOrderFulfillmentWorkflow` 내 `createRemoteLinkStep`에서 생성된다.  
**createRemoteLinkStep**: [packages/core/core-flows/src/common/steps/create-remote-links.ts](packages/core/core-flows/src/common/steps/create-remote-links.ts) — 보상 함수에서 `link.dismiss(createdLinks)` 호출로 롤백.

---

### 3. API 라우트 → 워크플로우 진입점

| HTTP | 경로 | 워크플로우 |
|---|---|---|
| `POST` | `/admin/orders/:id/fulfillments` | `createOrderFulfillmentWorkflow` |
| `POST` | `/admin/orders/:id/fulfillments/:fulfillment_id/shipments` | `createOrderShipmentWorkflow` |
| `POST` | `/admin/orders/:id/fulfillments/:fulfillment_id/cancel` | `cancelOrderFulfillmentWorkflow` |

**미들웨어**: [packages/medusa/src/api/admin/orders/middlewares.ts:201-251](packages/medusa/src/api/admin/orders/middlewares.ts#L201-L251)
- body 검증: `AdminOrderCreateFulfillment` (`items` 최소 1개 필수), `AdminOrderCreateShipment`
- policy: 풀필먼트 생성은 `PolicyOperation.create`, 배송 처리는 `PolicyOperation.update`

**라우트 핸들러**:
- `POST fulfillments`: [packages/medusa/src/api/admin/orders/[id]/fulfillments/route.ts:12-36](packages/medusa/src/api/admin/orders/%5Bid%5D/fulfillments/route.ts#L12-L36)
- `POST shipments`: [packages/medusa/src/api/admin/orders/[id]/fulfillments/[fulfillment_id]/shipments/route.ts:15-46](packages/medusa/src/api/admin/orders/%5Bid%5D/fulfillments/%5Bfulfillment_id%5D/shipments/route.ts#L15-L46)

두 라우트 핸들러 모두 워크플로우 실행 후 `remoteQuery`로 업데이트된 Order를 재조회하여 `res.json({ order })`로 반환한다.

---

### 4. createOrderFulfillmentWorkflow (풀필먼트 생성)

**파일**: [packages/core/core-flows/src/order/workflows/create-fulfillment.ts](packages/core/core-flows/src/order/workflows/create-fulfillment.ts)  
**workflowId**: `"create-order-fulfillment"`

```
1. useQueryGraphStep       → Order + items + variants + inventory + shipping_methods 조회
2. createFulfillmentValidateOrder → 검증 (items 비어있음, 주문 취소, 아이템 미존재, 배송 그루핑)
3. useRemoteQueryStep      → ShippingOption → provider_id, location_id 조회
4. useRemoteQueryStep      → ReservationItem 조회 (line_item_id 기준)
5. transform               → prepareFulfillmentData() — Fulfillment 모듈 입력 조립
6. createFulfillmentWorkflow.runAsStep → [Fulfillment 도메인 서브워크플로우]
7. adjustInventoryLevelsStep          → 재고 실물 수량 차감 (음수 adjustment)
8. parallelize(
     registerOrderFulfillmentStep     → Order 모듈: OrderItem.fulfilled_quantity 증가
     createRemoteLinkStep             → order_fulfillment 피벗 테이블 레코드 생성
     updateReservationsStep           → 예약 수량 감소
     deleteReservationsStep           → 소진된 예약 삭제
     emitEventStep                    → order.fulfillment_created 이벤트
   )
9. hook: fulfillmentCreated
```

**반환값**: 생성된 `FulfillmentDTO` 객체.

**검증 스텝 `createFulfillmentValidateOrder`** (동일 파일 103-117행):
- `inputItems.length === 0` → `INVALID_DATA`
- 주문 취소 상태 → `INVALID_DATA`
- 입력 아이템이 주문에 없음 → `INVALID_DATA`
- 배송 필요 아이템과 불필요 아이템 혼재 → `INVALID_DATA`

**prepareFulfillmentData 핵심 로직** (141-264행):
- inventory kit(`required_quantity > 1`)인 경우 `fitem.quantity = inputQty × required_quantity`로 수량 변환
- `location_id` 우선순위: `input.location_id` > `shippingOption.service_zone.fulfillment_set.location.id`

---

### 5. createFulfillmentWorkflow (Fulfillment 도메인 서브워크플로우)

**파일**: [packages/core/core-flows/src/fulfillment/workflows/create-fulfillment.ts](packages/core/core-flows/src/fulfillment/workflows/create-fulfillment.ts)  
**workflowId**: `"create-fulfillment-workflow"`

```
1. useRemoteQueryStep  → stock_location 주소 조회 (throw_if_key_not_found: true)
2. transform           → { ...input, location } 합성
3. createFulfillmentStep → IFulfillmentModuleService.createFulfillment()
```

**createFulfillmentStep** ([packages/core/core-flows/src/fulfillment/steps/create-fulfillment.ts](packages/core/core-flows/src/fulfillment/steps/create-fulfillment.ts)):
- 보상 데이터: `fulfillment.id`
- 보상 함수: `service.cancelFulfillment(id)`

**IFulfillmentModuleService.createFulfillment()** ([packages/modules/fulfillment/src/services/fulfillment-module-service.ts:602-645](packages/modules/fulfillment/src/services/fulfillment-module-service.ts#L602-L645)):
1. `fulfillmentService_.create()` → DB에 Fulfillment 레코드 저장
2. `fulfillmentProviderService_.createFulfillment()` → 외부 프로바이더 API 호출
3. 프로바이더 응답으로 `data`, `labels` 업데이트
4. 프로바이더 실패 시 → 생성한 레코드 즉시 삭제 후 에러 throw

---

### 6. registerOrderFulfillmentStep — Order 모듈에 Fulfillment 등록

**파일**: [packages/core/core-flows/src/order/steps/register-fulfillment.ts](packages/core/core-flows/src/order/steps/register-fulfillment.ts)  
**stepId**: `"register-order-fullfillment"` (오타 있음)

입력:
```typescript
{
  order_id: string
  items: { id: string; quantity: number }[]
  reference: Modules.FULFILLMENT   // 고정값
  reference_id: fulfillment.id
  created_by?: string
}
```

**IOrderModuleService.registerFulfillment()** → **BundledActions.registerFulfillment()** ([packages/modules/order/src/services/actions/register-fulfillment.ts](packages/modules/order/src/services/actions/register-fulfillment.ts)):
1. 각 item을 `ChangeActionType.FULFILL_ITEM` action으로 변환
2. `createOrderChange_()` → `confirmOrderChange()` 즉시 확정 적용
3. `FULFILL_ITEM` action 처리: `OrderItem.fulfilled_quantity += action.details.quantity`

**보상 함수**: `IOrderModuleService.revertLastVersion(orderId)` — OrderItem의 version을 이전 상태로 롤백.

---

### 7. createOrderShipmentWorkflow (배송 시작)

**파일**: [packages/core/core-flows/src/order/workflows/create-shipment.ts](packages/core/core-flows/src/order/workflows/create-shipment.ts)  
**workflowId**: `"create-order-shipment"`

```
1. useQueryGraphStep         → Order + fulfillments + items.variant.inventory_items 조회
2. createShipmentValidateOrder → 취소 여부, fulfillment_id 유효성 검증
3. parallelize(
     createShipmentWorkflow.runAsStep → Fulfillment 모듈: shipped_at = now, labels 저장
     registerOrderShipmentStep        → Order 모듈: OrderItem.shipped_quantity 증가
   )
4. emitEventStep              → FulfillmentWorkflowEvents.SHIPMENT_CREATED 이벤트
5. hook: shipmentCreated
```

**반환값**: `void 0` (Order 재조회는 라우트 핸들러에서 처리).

**createShipmentWorkflow** ([packages/core/core-flows/src/fulfillment/workflows/create-shipment.ts](packages/core/core-flows/src/fulfillment/workflows/create-shipment.ts)):
1. `validateShipmentStep` — `shipped_at`/`canceled_at` 존재 여부, `shipping_option_id` 존재 여부 검증
2. `transform` → `{ ...input, shipped_at: new Date() }` 생성
3. `updateFulfillmentWorkflow.runAsStep` → DB 업데이트

**prepareRegisterShipmentData 핵심 로직** (105-161행):
- inventory kit인 경우 `lineItem.quantity = fulfillmentItem.quantity / required_quantity`로 역산

---

### 8. cancelOrderFulfillmentWorkflow (풀필먼트 취소)

**파일**: [packages/core/core-flows/src/order/workflows/cancel-order-fulfillment.ts](packages/core/core-flows/src/order/workflows/cancel-order-fulfillment.ts)  
**workflowId**: `"cancel-order-fulfillment"`

```
1. useQueryGraphStep                  → Order + fulfillments + items 조회
2. cancelOrderFulfillmentValidateOrder → shipped_at/canceled_at 있으면 취소 불가
3. useRemoteQueryStep                  → 기존 ReservationItem 조회
4. adjustInventoryLevelsStep           → 재고 복원 (양수 adjustment)
5. parallelize(
     cancelOrderFulfillmentStep        → Order 모듈: fulfilled_quantity 감소
     createReservationsStep            → 예약 없던 아이템 재예약 신규 생성
     updateReservationsStep            → 기존 예약 수량 복원
     emitEventStep                     → order.fulfillment_canceled 이벤트
   )
6. cancelFulfillmentWorkflow.runAsStep → Fulfillment 모듈: canceled_at = now
   (주석: "no compensation for this step" — 보상 불가 단계라 마지막에 배치)
7. hook: orderFulfillmentCanceled
```

---

### 9. OrderItem 수량 필드 추적 구조

**파일**: [packages/modules/order/src/models/order-item.ts](packages/modules/order/src/models/order-item.ts)

| 필드 | 증가 시점 | 감소 시점 |
|---|---|---|
| `fulfilled_quantity` | `registerFulfillment` (FULFILL_ITEM) | `cancelFulfillment` (CANCEL_ITEM_FULFILLMENT) |
| `shipped_quantity` | `registerShipment` (SHIP_ITEM) | — |
| `delivered_quantity` | `registerDelivery` (DELIVER_ITEM) | — |

OrderItem은 `version` 필드로 이력을 관리한다. `confirmOrderChange()` 호출마다 새 version이 기록되고, 보상 함수 `revertLastVersion()`이 version을 롤백한다.

각 action type의 수량 검증:
- `FULFILL_ITEM`: `요청 수량 ≤ (ordered_quantity - fulfilled_quantity)` 초과 시 에러
- `SHIP_ITEM`: `요청 수량 ≤ (fulfilled_quantity - shipped_quantity)` 초과 시 에러
- `DELIVER_ITEM`: `(기존 delivered + 신규 delivered) ≤ fulfilled_quantity` 초과 시 에러

---

### 10. Fulfillment 엔티티 구조

**파일**: [packages/modules/fulfillment/src/models/fulfillment.ts](packages/modules/fulfillment/src/models/fulfillment.ts)

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | text (prefix: `ful`) | PK |
| `location_id` | text | StockLocation ID (FK 없음) |
| `packed_at` | dateTime nullable | 생성 시 `new Date()` |
| `shipped_at` | dateTime nullable | createShipment 시 설정 |
| `delivered_at` | dateTime nullable | markAsDelivered 시 설정 |
| `canceled_at` | dateTime nullable | cancel 시 설정 |
| `data` | json nullable | 외부 프로바이더 응답 |
| `requires_shipping` | boolean default(true) | 배송 필요 여부 |
| `items` | hasMany FulfillmentItem | cascade delete |
| `labels` | hasMany FulfillmentLabel | cascade delete |
| `delivery_address` | hasOne FulfillmentAddress | cascade delete |

**FulfillmentItem** ([packages/modules/fulfillment/src/models/fulfillment-item.ts](packages/modules/fulfillment/src/models/fulfillment-item.ts)):
- `line_item_id`: Order의 LineItem ID (단순 텍스트, DB FK 없음)
- `inventory_item_id`: Inventory 아이템 ID (단순 텍스트, DB FK 없음)
- `quantity`: bigNumber

두 ID 모두 외부 모듈 레코드를 텍스트로만 참조하며, 실제 조인은 Remote Query를 통해 런타임에 이루어진다.

---

### 11. inventory kit 수량 변환 패턴

**발생 위치**: `createOrderFulfillmentWorkflow`, `createOrderShipmentWorkflow`, `cancelOrderFulfillmentWorkflow`, `markOrderFulfillmentAsDeliveredWorkflow`

Fulfillment 생성 시 (`prepareFulfillmentData`):
```
FulfillmentItem.quantity = lineItem.quantity × inventory_item.required_quantity
```

Shipment/Delivery 등록 시 역산 (`prepareRegisterShipmentData`, `prepareRegisterDeliveryData`):
```
lineItem.quantity = fulfillmentItem.quantity ÷ inventory_item.required_quantity
```

이 변환이 없으면 inventory kit(1개 LineItem이 여러 inventory item으로 구성)의 수량이 Order 모듈에 잘못 기록된다.

---

## Code References

| 역할 | 파일 |
|---|---|
| 링크 상수 | [packages/core/utils/src/link/links.ts:107-112](packages/core/utils/src/link/links.ts#L107-L112) |
| 링크 정의 (ModuleJoinerConfig) | [packages/modules/link-modules/src/definitions/order-fulfillment.ts](packages/modules/link-modules/src/definitions/order-fulfillment.ts) |
| 미들웨어 등록 | [packages/medusa/src/api/admin/orders/middlewares.ts:201-251](packages/medusa/src/api/admin/orders/middlewares.ts#L201-L251) |
| Body 유효성 스키마 | [packages/medusa/src/api/admin/orders/validators.ts:96-120](packages/medusa/src/api/admin/orders/validators.ts#L96-L120) |
| POST fulfillments 라우트 | [packages/medusa/src/api/admin/orders/[id]/fulfillments/route.ts](packages/medusa/src/api/admin/orders/%5Bid%5D/fulfillments/route.ts) |
| POST shipments 라우트 | [packages/medusa/src/api/admin/orders/[id]/fulfillments/[fulfillment_id]/shipments/route.ts](packages/medusa/src/api/admin/orders/%5Bid%5D/fulfillments/%5Bfulfillment_id%5D/shipments/route.ts) |
| createOrderFulfillmentWorkflow | [packages/core/core-flows/src/order/workflows/create-fulfillment.ts](packages/core/core-flows/src/order/workflows/create-fulfillment.ts) |
| createOrderShipmentWorkflow | [packages/core/core-flows/src/order/workflows/create-shipment.ts](packages/core/core-flows/src/order/workflows/create-shipment.ts) |
| cancelOrderFulfillmentWorkflow | [packages/core/core-flows/src/order/workflows/cancel-order-fulfillment.ts](packages/core/core-flows/src/order/workflows/cancel-order-fulfillment.ts) |
| registerOrderFulfillmentStep | [packages/core/core-flows/src/order/steps/register-fulfillment.ts](packages/core/core-flows/src/order/steps/register-fulfillment.ts) |
| registerOrderShipmentStep | [packages/core/core-flows/src/order/steps/register-shipment.ts](packages/core/core-flows/src/order/steps/register-shipment.ts) |
| createFulfillmentWorkflow (서브) | [packages/core/core-flows/src/fulfillment/workflows/create-fulfillment.ts](packages/core/core-flows/src/fulfillment/workflows/create-fulfillment.ts) |
| createFulfillmentStep | [packages/core/core-flows/src/fulfillment/steps/create-fulfillment.ts](packages/core/core-flows/src/fulfillment/steps/create-fulfillment.ts) |
| Order 모듈 서비스 (register 메서드) | [packages/modules/order/src/services/order-module-service.ts:4462-4494](packages/modules/order/src/services/order-module-service.ts#L4462-L4494) |
| BundledActions.registerFulfillment | [packages/modules/order/src/services/actions/register-fulfillment.ts](packages/modules/order/src/services/actions/register-fulfillment.ts) |
| FULFILL_ITEM action | [packages/modules/order/src/utils/actions/fulfill-item.ts](packages/modules/order/src/utils/actions/fulfill-item.ts) |
| SHIP_ITEM action | [packages/modules/order/src/utils/actions/ship-item.ts](packages/modules/order/src/utils/actions/ship-item.ts) |
| OrderItem 모델 | [packages/modules/order/src/models/order-item.ts](packages/modules/order/src/models/order-item.ts) |
| Fulfillment 모듈 서비스 | [packages/modules/fulfillment/src/services/fulfillment-module-service.ts:602-645](packages/modules/fulfillment/src/services/fulfillment-module-service.ts#L602-L645) |
| Fulfillment 모델 | [packages/modules/fulfillment/src/models/fulfillment.ts](packages/modules/fulfillment/src/models/fulfillment.ts) |
| FulfillmentItem 모델 | [packages/modules/fulfillment/src/models/fulfillment-item.ts](packages/modules/fulfillment/src/models/fulfillment-item.ts) |
| createRemoteLinkStep | [packages/core/core-flows/src/common/steps/create-remote-links.ts](packages/core/core-flows/src/common/steps/create-remote-links.ts) |

---

## Architecture Documentation

### 두 도메인 연결의 전체 구조

```
[HTTP Layer]
POST /admin/orders/:id/fulfillments
  └── createOrderFulfillmentWorkflow (req.scope)

[Workflow Layer — 두 도메인 조율]
createOrderFulfillmentWorkflow
  ├── [조회] useQueryGraphStep (Order)
  ├── [조회] useRemoteQueryStep (ShippingOption, Reservations)
  ├── [위임] createFulfillmentWorkflow.runAsStep
  │         └── createFulfillmentStep
  │               └── IFulfillmentModuleService.createFulfillment()
  │                     ├── fulfillmentService_.create()         → Fulfillment 레코드 생성
  │                     └── fulfillmentProviderService_.createFulfillment() → 외부 API
  ├── [재고] adjustInventoryLevelsStep → IInventoryModuleService
  └── [동시] parallelize
            ├── registerOrderFulfillmentStep
            │     └── IOrderModuleService.registerFulfillment()
            │           └── OrderItem.fulfilled_quantity 증가
            ├── createRemoteLinkStep → order_fulfillment 테이블 삽입
            ├── updateReservationsStep / deleteReservationsStep
            └── emitEventStep → order.fulfillment_created

[Data Layer]
Order 모듈 DB: order_item (fulfilled_quantity)
Fulfillment 모듈 DB: fulfillment, fulfillment_item, fulfillment_label
Link 테이블: order_fulfillment (order_id, fulfillment_id)
```

### 보상(Compensation) 패턴

Order 모듈 스텝들(`registerOrderFulfillmentStep`, `registerOrderShipmentStep` 등)은 모두 `IOrderModuleService.revertLastVersion(orderId)`를 보상 함수로 사용한다. Fulfillment 모듈 스텝(`createFulfillmentStep`)은 `IFulfillmentModuleService.cancelFulfillment(id)`를 사용한다.

`cancelOrderFulfillmentWorkflow`에서 `cancelFulfillmentWorkflow.runAsStep`은 의도적으로 마지막에 배치되어 있다. 소스 코드 주석(398행)에 "no compensation for this step"이라 명시되어 있으며, 이 단계는 실패해도 롤백 없이 종료된다.

### 이벤트 상수 정리

| 이벤트 | 상수 | 발생 시점 |
|---|---|---|
| `order.fulfillment_created` | `OrderWorkflowEvents.FULFILLMENT_CREATED` | createOrderFulfillmentWorkflow 완료 |
| `fulfillment.shipment_created` | `FulfillmentWorkflowEvents.SHIPMENT_CREATED` | createOrderShipmentWorkflow 완료 |
| `order.fulfillment_canceled` | `OrderWorkflowEvents.FULFILLMENT_CANCELED` | cancelOrderFulfillmentWorkflow 완료 |

---

## Open Questions

- `registerOrderShipmentStep` 내 `shippingMethodId` 변수가 선언되지만 값이 없어 `SHIPPING_ADD` action 분기가 실행되지 않는 부분 (`register-shipment.ts:29-35`) — 현재 코드 상태 확인 필요.
- `createReturnFulfillmentStep` 보상 함수에 `// TODO: Implement cancelReturnFulfillment` 주석 존재 (`create-return-fulfillment.ts:55`) — 반품 풀필먼트 취소 보상 로직 미구현 상태 확인 필요.
- `LINKS.OrderClaimPaymentCollection`, `LINKS.OrderExchangePaymentCollection` 상수는 `links.ts`에 정의되어 있으나 `link-modules/src/definitions/` 내 joiner config 파일이 존재하지 않음. 실제 워크플로우는 `OrderPaymentCollection` 링크만 사용함.

---

## Follow-up Research 2026-05-07: Return / Exchange / Claim ↔ Fulfillment 연결

### 질문

반품(Return), 교환(Exchange), 클레임(Claim)도 Fulfillment 도메인과 연결되는가? ReturnItem 등은 어떻게 연결되는가?

### 결론 요약

Return / Exchange / OrderClaim 세 엔티티는 모두 **Order 모듈 내부 엔티티**다 (`packages/modules/order/src/models/`). 별도 모듈이 아니라 Order 도메인의 일부로 관리된다. Fulfillment 도메인과의 연결 패턴은 다음과 같다.

| 흐름 | Fulfillment 연결 방식 | Link 테이블 |
|---|---|---|
| **일반 주문 발송** | `createOrderFulfillmentWorkflow` | `order_fulfillment` (`order_id ↔ fulfillment_id`) |
| **Return 수거 (inbound)** | `createReturnFulfillmentWorkflow` | `return_fulfillment` (`return_id ↔ fulfillment_id`) |
| **Exchange 회수 (inbound)** | `createReturnFulfillmentWorkflow` | `return_fulfillment` (Exchange가 보유한 `return_id` 사용) |
| **Claim 회수 (inbound)** | `createReturnFulfillmentWorkflow` | `return_fulfillment` (Claim이 보유한 `return_id` 사용) |
| **Exchange 신규 발송 (outbound)** | confirm 시점에는 `reserveInventoryStep`만 (재고 예약). 실제 fulfillment 생성은 별도로 `createOrderFulfillmentWorkflow` 호출 | `order_fulfillment` |
| **Claim 교체품 발송 (outbound)** | 동일하게 `reserveInventoryStep` + 별도 `createOrderFulfillmentWorkflow` | `order_fulfillment` |

핵심 패턴: **Exchange/Claim 전용 Fulfillment 링크 테이블은 존재하지 않는다**. 회수(inbound)는 항상 Return을 거쳐서 `return_fulfillment` 링크로 연결되고, 교체품 발송(outbound)은 일반 `order_fulfillment` 링크로 연결된다.

---

### 1. Return / Exchange / Claim 모델 구조

#### Return 모델
[packages/modules/order/src/models/return.ts](packages/modules/order/src/models/return.ts)

| 필드 | 비고 |
|---|---|
| `id` (prefix: `return`) | PK |
| `status` | `OPEN` / `REQUESTED` / `RECEIVED` / `PARTIALLY_RECEIVED` / `CANCELED` |
| `location_id` | nullable |
| `refund_amount` | nullable |
| `requested_at`, `received_at`, `canceled_at` | 상태 타임스탬프 |
| `order` → `Order` (belongsTo, FK `order_id`) | |
| `exchange` → `OrderExchange` (hasOne, FK `exchange_id`, nullable) | Exchange가 만든 Return인지 표시 |
| `claim` → `OrderClaim` (hasOne, FK `claim_id`, nullable) | Claim이 만든 Return인지 표시 |
| `items` → `ReturnItem[]` | cascade delete |
| `shipping_methods` → `OrderShipping[]` | cascade delete |

**Return 모델 자체에는 `fulfillment_id`가 없다**. Fulfillment 연결은 `return_fulfillment` 링크 테이블이 담당.

#### ReturnItem 모델
[packages/modules/order/src/models/return-item.ts](packages/modules/order/src/models/return-item.ts)

| 필드 | 비고 |
|---|---|
| `id` (prefix: `retitem`) | PK |
| `quantity`, `received_quantity`, `damaged_quantity` | 수량 추적 |
| `reason` → `ReturnReason` (FK `reason_id`, nullable) | |
| `return` → `Return` (FK `return_id`) | |
| `item` → `OrderLineItem` (FK `item_id`) | **OrderLineItem.id를 직접 참조 (DB FK)** |

ReturnItem은 `item_id` (= `OrderLineItem.id`)를 **DB FK로** 보유한다. `FulfillmentItem.line_item_id`(텍스트, FK 없음)와는 다른 패턴이다 (Order 모듈 내부 관계이므로 진짜 FK 사용 가능).

#### OrderExchange 모델
[packages/modules/order/src/models/exchange.ts](packages/modules/order/src/models/exchange.ts)

| 필드 | 비고 |
|---|---|
| `id` (prefix: `oexc`) | PK |
| `difference_due` | 차액 |
| `allow_backorder` | |
| `order` → `Order` (FK `order_id`) | |
| `return` → `Return` (FK `return_id`, nullable) | **회수 반품을 직접 참조** |
| `additional_items` → `OrderExchangeItem[]` | 교체로 새로 발송할 아이템 |

#### OrderExchangeItem 모델
[packages/modules/order/src/models/exchange-item.ts](packages/modules/order/src/models/exchange-item.ts)
- `item` → `OrderLineItem` (FK `item_id`) — 새 발송 라인아이템 참조

#### OrderClaim 모델
[packages/modules/order/src/models/claim.ts](packages/modules/order/src/models/claim.ts)

| 필드 | 비고 |
|---|---|
| `id` (prefix: `claim`) | PK |
| `type` | `ClaimType` enum |
| `refund_amount` | nullable |
| `order` → `Order` (FK `order_id`) | |
| `return` → `Return` (FK `return_id`, nullable) | **회수 반품을 직접 참조** |
| `additional_items` → `OrderClaimItem[]` | 교체품 |
| `claim_items` → `OrderClaimItem[]` | 클레임 대상 아이템 (동일 엔티티) |

#### OrderClaimItem 모델
[packages/modules/order/src/models/claim-item.ts](packages/modules/order/src/models/claim-item.ts)
- `item` → `OrderLineItem` (FK `item_id`)
- `is_additional_item: boolean` — 교체 발송 아이템(true)인지 클레임 대상(false)인지 구분

---

### 2. Link 테이블 정리

#### `return_fulfillment` 링크
[packages/modules/link-modules/src/definitions/order-return-fulfillment.ts](packages/modules/link-modules/src/definitions/order-return-fulfillment.ts)

| 항목 | 값 |
|---|---|
| serviceName | `LINKS.ReturnFulfillment` |
| tableName | `return_fulfillment` |
| idPrefix | `retful` |
| primaryKeys | `[id, return_id, fulfillment_id]` |
| 좌측 | `Modules.ORDER` / entity `Return` / FK `return_id` |
| 우측 | `Modules.FULFILLMENT` / entity `Fulfillment` / FK `fulfillment_id` (hasMany) |

`Return` 엔티티에 `fulfillments` 가상 필드 추가, `Fulfillment` 엔티티에 `return_link` relationship 추가.

#### Claim/Exchange 전용 Fulfillment 링크 — 없음

`link-modules/src/definitions/` 디렉토리 전수 조사 결과, `claim_fulfillment` 또는 `exchange_fulfillment` 정의 파일은 존재하지 않는다. 다음 두 경로로 처리된다:

1. **회수(inbound)**: Exchange/Claim의 `return_id` → Return 엔티티 → `return_fulfillment` 링크
2. **교체 발송(outbound)**: 일반 `order_fulfillment` 링크 사용

---

### 3. 워크플로우별 Fulfillment 호출 패턴

#### Return: `confirmReturnRequestWorkflow`
[packages/core/core-flows/src/order/workflows/return/confirm-return-request.ts](packages/core/core-flows/src/order/workflows/return/confirm-return-request.ts)

```
1. createReturnItemsFromActionsStep         → ORDER 모듈에 ReturnItem 생성
2. when(returnShippingOptionId).then(
     createReturnFulfillmentWorkflow.runAsStep   → FULFILLMENT 모듈에 회수 fulfillment
     createRemoteLinkStep                        → ORDER.return_id ↔ FULFILLMENT.fulfillment_id
   )
3. parallelize(updateReturnsStep, confirmOrderChanges, emitEventStep)
4. createOrUpdateOrderPaymentCollectionWorkflow.runAsStep
```

#### Return: `createAndCompleteReturnOrderWorkflow` (storefront)
[packages/core/core-flows/src/order/workflows/return/create-complete-return.ts](packages/core/core-flows/src/order/workflows/return/create-complete-return.ts)

```
1. createReturnFulfillmentWorkflow.runAsStep  → FULFILLMENT 회수 fulfillment 생성
2. createCompleteReturnStep                   → ORDER 모듈에 Return 직접 생성
3. createRemoteLinkStep                       → ORDER.return_id ↔ FULFILLMENT.fulfillment_id
4. (input.receive_now가 true이면) receiveReturnStep
5. parallelize(emitEventStep × 2)
```

#### Return: `confirmReturnReceiveWorkflow`
[packages/core/core-flows/src/order/workflows/return/confirm-receive-return-request.ts](packages/core/core-flows/src/order/workflows/return/confirm-receive-return-request.ts)

이 워크플로우는 **Fulfillment 모듈을 호출하지 않는다**. 이미 생성된 Return의 수령 처리만 담당:
```
1. parallelize(updateReturnsStep, updateReturnItemsStep, confirmOrderChanges, adjustInventoryLevelsStep)
2. parallelize(createOrUpdateOrderPaymentCollectionWorkflow, emitEventStep)
```
재고 복원은 INVENTORY 모듈의 `adjustInventoryLevelsStep`이 담당. Return 상태는 모든 아이템 수령 시 `RECEIVED`, 일부만 수령 시 `PARTIALLY_RECEIVED`.

#### Exchange: `confirmExchangeRequestWorkflow`
[packages/core/core-flows/src/order/workflows/exchange/confirm-exchange-request.ts](packages/core/core-flows/src/order/workflows/exchange/confirm-exchange-request.ts)

Exchange는 inbound(회수) + outbound(교체 발송) 두 방향을 처리한다:

```
1. parallelize(
     createOrderExchangeItemsFromActionsStep,    → ORDER에 ExchangeItem 생성
     createReturnItemsFromActionsStep            → ORDER에 ReturnItem 생성
   )
2. when(returnId).then(updateReturnsStep)        → Return 상태 REQUESTED로
3. when(exchangeShippingMethod).then(
     reserveInventoryStep                        → outbound용 재고 예약만
   )
4. when(returnShippingMethod && returnId).then(
     createReturnFulfillmentWorkflow.runAsStep   → 회수 fulfillment 생성
     createRemoteLinkStep                        → ORDER.return_id ↔ FULFILLMENT.fulfillment_id
   )
```

**Exchange의 outbound fulfillment는 이 confirm 시점에 생성되지 않는다.** 재고 예약만 잡고, 실제 발송 fulfillment는 추후 별도의 `createOrderFulfillmentWorkflow` 호출(관리자 발송 처리)로 생성된다.

#### Claim: `confirmClaimRequestWorkflow`
[packages/core/core-flows/src/order/workflows/claim/confirm-claim-request.ts](packages/core/core-flows/src/order/workflows/claim/confirm-claim-request.ts)

구조가 Exchange와 거의 동일:
```
1. parallelize(createOrderClaimItemsFromActionsStep, createReturnItemsFromActionsStep)
2. when(returnId).then(updateReturnsStep)
3. when(claimShippingMethod).then(reserveInventoryStep)
4. when(returnShippingMethod && returnId).then(
     createReturnFulfillmentWorkflow.runAsStep
     createRemoteLinkStep                        → ORDER.return_id ↔ FULFILLMENT.fulfillment_id
   )
```

---

### 4. `createReturnFulfillmentWorkflow` 내부

[packages/core/core-flows/src/fulfillment/workflows/create-return-fulfillment.ts](packages/core/core-flows/src/fulfillment/workflows/create-return-fulfillment.ts)

```
1. useRemoteQueryStep    → stock_location 조회
2. transform             → input + location 합성
3. createReturnReturnStep → IFulfillmentModuleService.createReturnFulfillment(data)
```

일반 `createFulfillmentWorkflow`와의 차이는 **Fulfillment 모듈 서비스 메서드만 다르다** (`createReturnFulfillment` vs `createFulfillment`). 워크플로우 자체에서는 Return 도메인과 직접 링크를 만들지 않으며, 링크 생성은 호출자(상위 워크플로우)가 `createRemoteLinkStep`으로 처리한다.

`createReturnFulfillmentStep` 보상 함수는 `cancelFulfillment(id)`를 호출하며, 소스에 `// TODO: Implement cancelReturnFulfillment` 주석이 남아있다.

---

### 5. Order 모듈 등록 step 비교

| Step | 워크플로우에서의 사용처 | 호출 서비스 |
|---|---|---|
| `registerOrderFulfillmentStep` | `createOrderFulfillmentWorkflow` | `service.registerFulfillment()` (FULFILL_ITEM action) |
| `registerOrderShipmentStep` | `createOrderShipmentWorkflow` | `service.registerShipment()` (SHIP_ITEM action) |
| `cancelOrderFulfillmentStep` | `cancelOrderFulfillmentWorkflow` | `service.cancelFulfillment()` |
| `createReturnItemsFromActionsStep` | Return/Exchange/Claim confirm | `service.createReturnItems()` |
| `createOrderExchangeItemsFromActionsStep` | Exchange confirm | `service.createOrderExchangeItems()` |
| `createOrderClaimItemsFromActionsStep` | Claim confirm | `service.createOrderClaimItems()` |
| `createCompleteReturnStep` | `createAndCompleteReturnOrderWorkflow` | `service.createReturn()` |
| `receiveReturnStep` | Return 수령 워크플로우 | `service.receiveReturn()` |

**Return/Exchange/Claim confirm 워크플로우는 `registerOrderFulfillmentStep`을 호출하지 않는다.** 일반 fulfillment 흐름과는 다른 step 세트를 사용한다.

---

### 6. 전체 연결 그림

```
ORDER 모듈                                    LINK 테이블             FULFILLMENT 모듈
────────────                                  ────────────            ──────────────
Order ──────────────────────────── order_fulfillment ──────────── Fulfillment
  │                                                                     │
  │                                                                     │
  ├── OrderItem (fulfilled_qty, shipped_qty ...)                        │
  ├── OrderLineItem (스냅샷)                                           │
  │                                                                     │
  ├── Return                                                             │
  │     ├─ order_id (FK)                                                 │
  │     ├─ exchange_id (FK, nullable)                                    │
  │     ├─ claim_id (FK, nullable)                                       │
  │     └─ ReturnItem[] ──→ item_id (FK → OrderLineItem)                │
  │                                                                     │
  │     ↕ return_fulfillment ←───────────────────────────────────────┐  │
  │                                                                  │  │
  │                                                                  └──┘
  │
  ├── OrderExchange
  │     ├─ order_id (FK)
  │     ├─ return_id (FK, nullable) ──→ Return ──→ return_fulfillment ──→ Fulfillment
  │     └─ OrderExchangeItem[] ──→ item_id (FK → OrderLineItem) (새 발송 아이템)
  │           └─ outbound 발송: 별도 createOrderFulfillmentWorkflow → order_fulfillment
  │
  └── OrderClaim
        ├─ order_id (FK)
        ├─ return_id (FK, nullable) ──→ Return ──→ return_fulfillment ──→ Fulfillment
        └─ OrderClaimItem[] (is_additional_item으로 발송품/클레임품 구분)
              └─ outbound 발송: 별도 createOrderFulfillmentWorkflow → order_fulfillment
```

### 핵심 관찰

1. **Return / Exchange / Claim은 별도 모듈이 아니라 Order 모듈 내부 엔티티**다. Fulfillment와의 모듈 경계 횡단은 Return ↔ Fulfillment, Order ↔ Fulfillment 두 종류만 존재한다.

2. **inbound 회수는 항상 Return을 통해서만** Fulfillment에 연결된다. Exchange/Claim이 회수가 필요하면 자신의 `return_id`로 Return을 참조하고, Return이 `return_fulfillment` 링크로 Fulfillment에 연결된다.

3. **outbound 교체 발송은 일반 주문 발송과 동일한 경로**를 사용한다. confirm 시점에는 `reserveInventoryStep`으로 재고만 잡아두고, 실제 fulfillment 생성은 관리자가 발송 처리할 때 `createOrderFulfillmentWorkflow`로 별도 진행된다.

4. **Order 모듈 내부 엔티티들 사이의 참조는 진짜 DB FK**를 사용 (`return_id`, `exchange_id`, `claim_id`, `item_id`). 모듈 경계를 넘는 참조만 Remote Link 또는 텍스트 ID로 처리된다.

---

## Follow-up Research 2026-05-07: 일반 발송과 교체 발송(outbound) Fulfillment 구분 방법

### 질문

`order_fulfillment` 링크 테이블은 일반 주문 발송과 Exchange/Claim 교체 발송 outbound 모두 `Order.id ↔ Fulfillment.id`로 연결한다. 두 경우를 어떻게 구분하는가?

### 결론

**Fulfillment 도메인과 링크 테이블 수준에서는 구분 불가능하다** (사실).

`Fulfillment`, `FulfillmentItem`, `order_fulfillment` 링크 테이블 어디에도 `exchange_id`, `claim_id` 필드가 존재하지 않는다. `createOrderFulfillmentWorkflow`도 이 값을 입력으로 받지 않는다.

`registerFulfillment` action 생성 코드([packages/modules/order/src/services/actions/register-fulfillment.ts](packages/modules/order/src/services/actions/register-fulfillment.ts)):

```typescript
const items = data.items.map((item) => ({
  action: ChangeActionType.FULFILL_ITEM,
  reference: data.reference,
  reference_id: data.reference_id,
  details: { reference_id: item.id, quantity: item.quantity },
  // exchange_id / claim_id 없음
}))
```

### `OrderChangeAction`에는 `exchange_id`, `claim_id`가 있다

[packages/modules/order/src/models/order-change-action.ts:10-11](packages/modules/order/src/models/order-change-action.ts#L10-L11)

```typescript
claim_id: model.text().nullable()
exchange_id: model.text().nullable()
```

단, 이 필드는 Exchange/Claim의 아이템 추가/수정 action (`ITEM_ADD`, `WRITE_OFF_ITEM` 등) 생성 시에만 채워진다. `FULFILL_ITEM` action에는 채워지지 않는다.

### 간접 추적 경로 (추정)

"이 Fulfillment가 Exchange의 교체 발송이다"를 추적하려면 `OrderLineItem.id`를 공통 키로 삼은 간접 조인이 필요하다:

```
FulfillmentItem.line_item_id
  → OrderLineItem.id (공통 키)
    ← OrderExchangeItem.item_id → OrderExchange
    ← OrderClaimItem.item_id   → OrderClaim
```

Medusa가 이 조인을 어디서 실제로 수행하는지는 현재 확인되지 않음.
