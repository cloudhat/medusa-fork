# 09. 풀필먼트 생성·배송 처리

관리자가 주문을 발송 준비하고 배송을 시작하는 단계.

[← 여정 전체 목록](../README.md) | [다음: 10 배송 완료](../10-배송완료/README.md)

---

## API 엔드포인트

| 메서드 | 경로 | 워크플로우 |
|--------|------|-----------|
| `POST` | `/admin/orders/:id/fulfillments` | [createOrderFulfillmentWorkflow](./flow-createOrderFulfillmentWorkflow.md) |
| `POST` | `/admin/orders/:id/fulfillments/:fulfillment_id/cancel` | [cancelOrderFulfillmentWorkflow](./flow-cancelOrderFulfillmentWorkflow.md) |
| `POST` | `/admin/orders/:id/fulfillments/:fulfillment_id/shipments` | [createOrderShipmentWorkflow](./flow-createOrderShipmentWorkflow.md) |

---

## [createOrderFulfillmentWorkflow](./flow-createOrderFulfillmentWorkflow.md) (발송 준비)

**파일**: [packages/core/core-flows/src/order/workflows/create-fulfillment.ts](../../../../packages/core/core-flows/src/order/workflows/create-fulfillment.ts)

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `useQueryGraphStep` | Query | 주문 + 아이템 + 변형 + 인벤토리 + 배송 방법 전체 조회 |
| 2 | `createFulfillmentValidateOrder` | — | 아이템 존재 여부, 취소 여부, 배송 그루핑 검증 |
| 3 | `useRemoteQueryStep` | Remote Query | ShippingOption → FulfillmentSet → StockLocation ID 조회 |
| 4 | `useRemoteQueryStep` | Remote Query | 대상 라인 아이템들의 재고 예약(Reservation) 목록 조회 |
| 5 | `createFulfillmentWorkflow.runAsStep` | `FULFILLMENT` | 풀필먼트 레코드 생성 + 외부 프로바이더 호출 |
| 6 | **`adjustInventoryLevelsStep`** | `INVENTORY`, `LOCKING` | **재고 실물 수량 차감** (음수 adjustment) |
| **7~11** | **`parallelize`** | — | **아래 5개 동시 실행** |
| 7 | `registerOrderFulfillmentStep` | `ORDER` | 주문 이력에 풀필먼트 등록 |
| 8 | `createRemoteLinkStep` | Link | `ORDER ↔ FULFILLMENT` 링크 생성 |
| 9 | `updateReservationsStep` | `INVENTORY` | 잔여 예약 수량 업데이트 |
| 10 | `deleteReservationsStep` | `INVENTORY` | 소진된 예약 소프트 삭제 |
| 11 | `emitEventStep` | `EVENT_BUS` | `order.fulfillment_created` 이벤트 |
| 12 | `fulfillmentCreated` (hook) | — | 풀필먼트 생성 후 커스터마이징 지점 |

**재고 차감 시점**: Step 6 (`adjustInventoryLevelsStep`) — `parallelize` 블록 **이전**에 단독 실행된다.

### [createFulfillmentWorkflow](./flow-createFulfillmentWorkflow.md) 내부 (서브워크플로우)

**파일**: [packages/core/core-flows/src/fulfillment/workflows/create-fulfillment.ts](../../../../packages/core/core-flows/src/fulfillment/workflows/create-fulfillment.ts)

1. `useRemoteQueryStep` → StockLocation 주소 조회
2. `createFulfillmentStep` → `Modules.FULFILLMENT`:
   - `fulfillmentService_.create()` → DB에 Fulfillment 레코드 생성
   - `fulfillmentProviderService_.createFulfillment()` → 외부 물류 프로바이더 API 호출
   - 프로바이더 응답으로 `data`, `labels` 업데이트
   - 프로바이더 호출 실패 시 → 생성된 레코드 즉시 삭제 후 에러 throw

---

## [createOrderShipmentWorkflow](./flow-createOrderShipmentWorkflow.md) (배송 시작)

**파일**: [packages/core/core-flows/src/order/workflows/create-shipment.ts](../../../../packages/core/core-flows/src/order/workflows/create-shipment.ts)

### Step 실행 순서

| 순번 | Step | 모듈 | 주요 동작 |
|------|------|------|----------|
| 1 | `useQueryGraphStep` | Query | 주문 + fulfillments 조회 |
| 2 | `createShipmentValidateOrder` | — | 취소 여부, fulfillment_id 유효성 검증 |
| 3 | `parallelize` | — | 아래 2개 동시 실행 |
| 3a | `createShipmentWorkflow.runAsStep` | `FULFILLMENT` | `Fulfillment.shipped_at = now` + 배송 라벨 기록 |
| 3b | `registerOrderShipmentStep` | `ORDER` | 주문 이력에 shipment 등록 |
| 4 | `emitEventStep` | `EVENT_BUS` | `order.shipment_created` 이벤트 |

**검증 (`validateShipmentStep`)**: `shipped_at`이 이미 있으면 에러, `canceled_at`이 있으면 에러, `shipping_option_id`가 없으면 에러.

**인벤토리 변경 없음**: 배송 처리 단계에서 재고 수량은 변경되지 않는다. 재고 차감은 Step 09의 `createOrderFulfillmentWorkflow`에서 완료됐다.

---

## [cancelOrderFulfillmentWorkflow](./flow-cancelOrderFulfillmentWorkflow.md) (풀필먼트 취소)

**파일**: [packages/core/core-flows/src/order/workflows/cancel-order-fulfillment.ts](../../../../packages/core/core-flows/src/order/workflows/cancel-order-fulfillment.ts)

| 조건 | 결과 |
|------|------|
| `shipped_at`이 있는 경우 | 취소 불가 에러 |
| `canceled_at`이 이미 있는 경우 | 취소 불가 에러 |

취소 가능한 경우 재고 복원 + 예약 재생성이 이루어진다.

| 순번 | Step | 주요 동작 |
|------|------|----------|
| 1 | `useQueryGraphStep` | 주문 + fulfillments + 예약 조회 |
| 2 | `adjustInventoryLevelsStep` | **재고 복원** (+n 양수 adjustment) |
| 3 | `parallelize` | ORDER 취소 기록 + INVENTORY 예약 재생성·업데이트 + 이벤트 |
| 4 | `cancelFulfillmentWorkflow.runAsStep` | FULFILLMENT 프로바이더 취소 + `canceled_at = now` |

---

## Fulfillment 엔티티 구조

**파일**: [packages/modules/fulfillment/src/models/fulfillment.ts](../../../../packages/modules/fulfillment/src/models/fulfillment.ts)

| 필드 | 설명 |
|------|------|
| `location_id` | StockLocation ID (텍스트, FK 없음) |
| `packed_at` | 풀필먼트 생성 시 `new Date()` |
| `shipped_at` | createShipment 시 설정 |
| `delivered_at` | markAsDelivered 시 설정 |
| `canceled_at` | cancel 시 설정 |
| `data` | 외부 프로바이더 응답 JSON |
| `labels` → `FulfillmentLabel` | `tracking_number`, `tracking_url`, `label_url` |
| `items` → `FulfillmentItem` | `line_item_id`, `inventory_item_id`, `quantity` |

---

## 개입 모듈

| 모듈 | 역할 |
|------|------|
| `FULFILLMENT` | Fulfillment, FulfillmentItem, FulfillmentLabel 관리; 외부 물류 프로바이더 연동 |
| `ORDER` | 주문 이력 (registerFulfillment, registerShipment) |
| `INVENTORY` | 재고 수량 차감 (adjustInventoryLevels), 예약 삭제/갱신 |
| `LOCKING` | Inventory item 단위 동시성 제어 |
| Link | ORDER ↔ FULFILLMENT 연결 |
