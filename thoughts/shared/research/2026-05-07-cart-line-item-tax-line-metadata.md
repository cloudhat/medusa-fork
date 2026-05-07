---
date: 2026-05-07T14:24:57+0900
researcher: SAN KIM
git_commit: 221ca3586f04f6a6afa99f21f2bd98770f3ead07
branch: develop
repository: medusa-fork
topic: "CartLineItemTaxLine.metadata 컬럼의 용도와 활용처"
tags: [research, codebase, cart, tax-line, metadata]
status: complete
last_updated: 2026-05-07
last_updated_by: SAN KIM
---

# Research: CartLineItemTaxLine.metadata 컬럼의 용도와 활용처

**Date**: 2026-05-07T14:24:57+0900
**Researcher**: SAN KIM
**Git Commit**: 221ca3586f04f6a6afa99f21f2bd98770f3ead07
**Branch**: develop
**Repository**: medusa-fork

## Research Question

`CartLineItemTaxLine`의 `metadata` 컬럼에 어떤 값이 들어가는지, 코드베이스 어디에서 활용되는지 조사한다. (테스트 코드 포함)

## Summary

(사실) `metadata`는 `cart_line_item_tax_line` 테이블/엔티티에 **`jsonb NULL` 컬럼으로 존재**하지만, 현재 코드베이스에서 **이 컬럼에 값을 쓰는 코드 경로, 읽는 코드 경로, 검증하는 테스트 케이스가 모두 존재하지 않는다**.

- 모델 정의에 `metadata: model.json().nullable()`가 선언되어 있다 ([line-item-tax-line.ts:16](packages/modules/cart/src/models/line-item-tax-line.ts#L16)).
- 마이그레이션이 컬럼을 `JSONB NULL`로 생성한다 ([Migration20240222170223.ts:131](packages/modules/cart/src/migrations/Migration20240222170223.ts#L131)).
- 그러나 `CartLineItemTaxLineDTO`, `CreateLineItemTaxLineDTO`, `UpdateLineItemTaxLineDTO` 어디에도 `metadata` 필드가 없다.
- 세금 계산 → 카트 반영 파이프라인(`SystemTaxService.getTaxLines` → `setTaxLinesForItemsStep` → `cartService.setLineItemTaxLines`)에서 `metadata`를 매핑/전달하는 구간이 없다.
- 통합 테스트(`packages/modules/cart/integration-tests/__tests__/services/cart-module/index.spec.ts`)의 `setLineItemTaxLines`/`addLineItemTaxLines` 케이스 모두 `description`, `code`, `rate`, `provider_id`, `tax_rate_id`, `item_id`만 사용하며 `metadata`는 입력으로도 검증으로도 등장하지 않는다.

(추정) DB 컬럼은 모델/마이그레이션 레벨에 "Cart 도메인 다른 엔티티들이 모두 가지는 `metadata` 패턴"을 따라 일관성 차원에서 추가되어 있고, 외부 확장(커스텀 워크플로우, 외부 세금 프로바이더 구현 등)이 `upsertLineItemTaxLines`를 직접 호출할 때 임의 JSON을 저장하라는 용도로만 열려 있는 것으로 보인다.

(추정 / 비교) 같은 도메인의 `OrderLineItemTaxLine`([line-item-tax-line.ts:1-22](packages/modules/order/src/models/line-item-tax-line.ts#L1-L22))은 `metadata` 컬럼이 **없다**. Cart 쪽에만 `metadata`가 존재한다는 점은 "Cart 단계에서 외부 시스템이 임시로 부착하는 정보용"이라는 해석과 정합적이지만, 이를 실제로 사용하는 코드는 본 리포지토리 내에 없다.

(모름) 외부 플러그인/사설 모듈/문서가 이 필드를 어떻게 쓰는지는 본 코드베이스만으로 알 수 없다.

## Detailed Findings

### 1. 모델 정의

[packages/modules/cart/src/models/line-item-tax-line.ts:1-37](packages/modules/cart/src/models/line-item-tax-line.ts#L1-L37)

```ts
const LineItemTaxLine = model.define(
  { name: "LineItemTaxLine", tableName: "cart_line_item_tax_line" },
  {
    id: model.id({ prefix: "calitxl" }).primaryKey(),
    description: model.text().nullable(),
    code: model.text(),
    rate: model.float(),
    provider_id: model.text().nullable(),
    metadata: model.json().nullable(),     // ← 여기
    tax_rate_id: model.text().nullable(),
    item: model.belongsTo(() => LineItem, { mappedBy: "tax_lines" }),
  }
)
```

- `metadata`는 nullable JSON. 별도 인덱스/제약 없음.

### 2. 마이그레이션 (DDL)

[packages/modules/cart/src/migrations/Migration20240222170223.ts:124-141](packages/modules/cart/src/migrations/Migration20240222170223.ts#L124-L141)

```sql
CREATE TABLE IF NOT EXISTS "cart_line_item_tax_line" (
  ...
  "metadata" JSONB NULL,
  ...
)
```

- 초기 카트 스키마에 이미 `metadata JSONB NULL`로 포함되어 있음.
- 이후 `Migration20241205095237`, `Migration20241216183049`, `Migration20251017153909` 등은 이 테이블의 다른 측면(인덱스/외래키 정합)을 다루지만 `metadata` 컬럼 자체는 변경하지 않는다.

### 3. DTO 타입 정의 — `metadata` 부재

[packages/core/types/src/cart/common.ts:101-200](packages/core/types/src/cart/common.ts#L101-L200)

`TaxLineDTO`(부모) 필드: `id, description?, tax_rate_id?, code, rate, provider_id?, created_at, updated_at`. **`metadata` 없음.**
`LineItemTaxLineDTO extends TaxLineDTO`: 위 + `item, item_id, total, subtotal, raw_total, raw_subtotal`. **여전히 `metadata` 없음.**

[packages/core/types/src/cart/mutations.ts:374-475](packages/core/types/src/cart/mutations.ts#L374-L475)

```ts
export interface CreateTaxLineDTO {
  description?: string
  tax_rate_id?: string
  code: string
  rate: number
  provider_id?: string
  item_id?: string
}
export interface UpdateTaxLineDTO { id: string; description?: string; tax_rate_id?: string; code?: string; rate?: number; provider_id?: string; item_id?: string }
export interface CreateLineItemTaxLineDTO extends CreateTaxLineDTO {}
export interface UpdateLineItemTaxLineDTO extends UpdateTaxLineDTO {}
```

→ Create/Update 입력 어디에도 `metadata` 슬롯이 없다. 타입 시스템상으로는 외부 호출자가 `as any` 우회 없이 `metadata`를 채워 넣을 방법이 없다. (단, MikroORM 모델은 컬럼을 알고 있으므로 `upsert` 호출에서 추가 키를 넘기면 저장은 가능하다.)

### 4. 세금 계산 파이프라인 — `metadata` 미사용

#### 4.1 시스템 세금 프로바이더 출력

[packages/modules/tax/src/providers/system.ts:10-41](packages/modules/tax/src/providers/system.ts#L10-L41)

`getTaxLines`가 반환하는 `ItemTaxLineDTO`는 `{rate_id, rate, name, code, line_item_id, provider_id}`만 포함. **metadata 없음.**

#### 4.2 카트 반영 단계

[packages/core/core-flows/src/cart/steps/set-tax-lines-for-items.ts:137-148](packages/core/core-flows/src/cart/steps/set-tax-lines-for-items.ts#L137-L148)

```ts
function normalizeItemTaxLinesForCart(taxLines: ItemTaxLineDTO[]): CreateLineItemTaxLineDTO[] {
  return taxLines.map((taxLine) => ({
    description: taxLine.name,
    tax_rate_id: taxLine.rate_id,
    code: taxLine.code!,
    rate: taxLine.rate!,
    provider_id: taxLine.provider_id,
    item_id: taxLine.line_item_id,
  }))
}
```

→ 프로바이더 결과를 `CreateLineItemTaxLineDTO`로 normalize할 때 `metadata`는 매핑되지 않는다.

`set-tax-lines-for-items.ts`의 보상(rollback) 로직(Line 109-121)도 `description, tax_rate_id, code, rate, provider_id, item_id`만 복원한다.

#### 4.3 카트 모듈 서비스

[packages/modules/cart/src/services/cart-module.ts:873-902](packages/modules/cart/src/services/cart-module.ts#L873-L902)

`upsertLineItemTaxLines` / `setLineItemTaxLines` / `addLineItemTaxLines`는 입력 DTO를 그대로 `lineItemTaxLineService_.upsert(...)`에 전달한다. DTO 타입에 `metadata`가 없으므로 기본 호출자에서는 항상 `null`로 저장된다.

### 5. 통합 테스트 — `metadata` 미검증

테스트 파일: [packages/modules/cart/integration-tests/__tests__/services/cart-module/index.spec.ts:1949-2820](packages/modules/cart/integration-tests/__tests__/services/cart-module/index.spec.ts#L1949-L2820)

해당 범위에서 다루는 케이스:

- `setLineItemTaxLines` — set/replace/remove/update/혼합 시나리오 (Line 1949-2272)
- `setShippingMethodTaxLines` — 동일 패턴 (Line 2275-2620)
- `addLineItemTaxLines` — 단건/배열/소프트 삭제 (Line 2622-2820)

(사실) 위 모든 케이스에서 입력 객체는 `{item_id, rate, code}` (선택적으로 `id`, `description`)만 사용하고, `expect.objectContaining` 단언도 동일 필드만 검사한다. `metadata`라는 키는 한 번도 등장하지 않는다.

같은 파일에서 `metadata`가 등장하는 곳은 **카트 본문/라인아이템/주소** 등 별개 엔티티의 직렬화 결과 단언(예: Line 2897, 3010, 3107)뿐이며, 이들은 `metadata: null`을 검사한다 — tax line이 아니다.

### 6. 다른 tax line 엔티티와의 비교

| 엔티티 | 파일 | `metadata` 컬럼 |
|---|---|---|
| `CartLineItemTaxLine` | [packages/modules/cart/src/models/line-item-tax-line.ts](packages/modules/cart/src/models/line-item-tax-line.ts) | **있음** (json nullable) |
| `CartShippingMethodTaxLine` | [packages/modules/cart/src/models/shipping-method-tax-line.ts:17](packages/modules/cart/src/models/shipping-method-tax-line.ts#L17) | **있음** (json nullable) |
| `OrderLineItemTaxLine` | [packages/modules/order/src/models/line-item-tax-line.ts](packages/modules/order/src/models/line-item-tax-line.ts) | **없음** |

(사실) Cart 도메인의 두 tax-line 엔티티만 `metadata`를 갖고, Order 도메인은 갖지 않는다.

## Code References

- `packages/modules/cart/src/models/line-item-tax-line.ts:16` — `metadata` 모델 정의
- `packages/modules/cart/src/migrations/Migration20240222170223.ts:124-141` — 테이블 생성 DDL
- `packages/core/types/src/cart/common.ts:101-200` — DTO에 metadata 부재
- `packages/core/types/src/cart/mutations.ts:374-475` — Create/Update DTO에 metadata 부재
- `packages/modules/cart/src/services/cart-module.ts:873-902` — upsertLineItemTaxLines 시그니처
- `packages/core/core-flows/src/cart/steps/set-tax-lines-for-items.ts:137-148` — normalize 함수, metadata 미매핑
- `packages/modules/tax/src/providers/system.ts:10-41` — 시스템 프로바이더 출력에 metadata 없음
- `packages/modules/cart/integration-tests/__tests__/services/cart-module/index.spec.ts:1949-2820` — tax line 통합 테스트(metadata 미사용)

## Architecture Documentation

현재 `cart_line_item_tax_line.metadata`의 동작:

1. **쓰기 경로**: 기본 워크플로우(`updateTaxLinesWorkflow`, `setTaxLinesForItemsStep`)는 메타데이터를 채우지 않는다. `lineItemTaxLineService_.upsert(...)`가 직접 호출되며 입력 DTO에 `metadata` 슬롯이 없으므로 항상 `NULL`로 인서트된다.
2. **읽기 경로**: `LineItemTaxLineDTO`에 `metadata`가 없으므로 직렬화 출력에서도 노출되지 않는다. (단, `relations: ["items.tax_lines"]`로 조회 시 MikroORM 엔티티 객체에는 `metadata` 속성이 포함될 수 있음 — 사실/추정 경계: 직렬화 layer 동작은 별도 검증 필요.)
3. **확장 지점**: 커스텀 모듈이 `cartModuleService.upsertLineItemTaxLines`를 호출할 때 타입 단언으로 `metadata`를 추가해 저장하면 DB에 들어간다. 다만 본 리포지토리 내에는 그런 호출자가 없다.

## Related Research

- 본 디렉토리 `thoughts/shared/research/`에 추가 관련 문서는 없음

## Open Questions

- **모름**: 외부 plugin이나 비공개 사용처가 이 필드를 어떻게 쓰는지(예: 외부 세금 프로바이더가 계산 컨텍스트를 보존하기 위해 채우는지) — 본 코드베이스에는 흔적이 없다.
- **모름**: 직렬화 단계(`baseRepository_.serialize`)가 `metadata`를 출력에 포함하는지 — `LineItemTaxLineDTO` 인터페이스에는 없으나 실제 직렬화 결과는 별도 확인 필요.
