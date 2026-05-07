#!/usr/bin/env python3
"""Medusa ERD PDF — graphviz 기반, 관계선 + 카디널리티 포함"""

import subprocess
import shutil
import sys

BASE = "/Users/kimsan/Documents/workspace/study/medusa/참고자료/스키마"
DOT_FILE = f"{BASE}/erd_source.dot"
PDF_FILE = f"{BASE}/erd.pdf"

# ── 도메인 색상 ────────────────────────────────────────────────────────────────
C = {
    "order":   {"hdr": "#2E5C99", "bg": "#EBF1FA", "bdr": "#1A3A6B"},
    "pay":     {"hdr": "#1F8B5E", "bg": "#E8F6F0", "bdr": "#0D5A3B"},
    "ff":      {"hdr": "#9E5819", "bg": "#FAF0E6", "bdr": "#6B3A0D"},
    "promo":   {"hdr": "#7B2A8A", "bg": "#F5EBF8", "bdr": "#4E1B5A"},
}
DOMAIN_LABELS = {
    "order": "Order Module",
    "pay":   "Payment Module",
    "ff":    "Fulfillment Module",
    "promo": "Promotion Module",
}

# ── 엔티티 정의 ───────────────────────────────────────────────────────────────
# (이름, 도메인, [(필드명, 타입, "pk"|"fk"|"")])
ENTITIES = [
    # 주문
    ("Order", "order", [
        ("id",              "String",      "pk"),
        ("display_id",      "Int?",        ""),
        ("customer_id",     "String?",     ""),
        ("currency_code",   "String",      ""),
        ("status",          "OrderStatus", ""),
        ("version",         "Int",         ""),
        ("is_draft_order",  "Boolean",     ""),
    ]),
    ("OrderItem", "order", [
        ("id",                        "String",  "pk"),
        ("order_id",                  "String",  "fk"),
        ("item_id",                   "String",  "fk"),
        ("version",                   "Int",     ""),
        ("quantity",                  "Decimal", ""),
        ("fulfilled_quantity",        "Decimal", ""),
        ("shipped_quantity",          "Decimal", ""),
        ("return_requested_quantity", "Decimal", ""),
        ("return_received_quantity",  "Decimal", ""),
        ("written_off_quantity",      "Decimal", ""),
    ]),
    ("OrderLineItem", "order", [
        ("id",               "String",  "pk"),
        ("title",            "String",  ""),
        ("variant_id",       "String?", ""),
        ("product_id",       "String?", ""),
        ("variant_sku",      "String?", ""),
        ("unit_price",       "Decimal?",""),
        ("is_discountable",  "Boolean", ""),
        ("is_tax_inclusive", "Boolean", ""),
        ("requires_shipping","Boolean", ""),
        ("is_giftcard",      "Boolean", ""),
    ]),
    ("OrderLineItemAdjustment", "order", [
        ("id",           "String",  "pk"),
        ("item_id",      "String",  "fk"),
        ("promotion_id", "String?", ""),
        ("code",         "String?", ""),
        ("amount",       "Decimal", ""),
    ]),
    ("OrderLineItemTaxLine", "order", [
        ("id",          "String",  "pk"),
        ("item_id",     "String",  "fk"),
        ("code",        "String",  ""),
        ("rate",        "Decimal", ""),
        ("tax_rate_id", "String?", ""),
    ]),
    ("OrderShippingMethod", "order", [
        ("id",                 "String",  "pk"),
        ("order_id",           "String",  "fk"),
        ("shipping_option_id", "String?", ""),
        ("name",               "String",  ""),
        ("amount",             "Decimal", ""),
        ("is_tax_inclusive",   "Boolean", ""),
        ("is_custom_amount",   "Boolean", ""),
    ]),
    ("OrderShippingMethodAdjustment", "order", [
        ("id",                 "String",  "pk"),
        ("shipping_method_id", "String",  "fk"),
        ("promotion_id",       "String?", ""),
        ("code",               "String?", ""),
        ("amount",             "Decimal", ""),
    ]),
    ("OrderShippingMethodTaxLine", "order", [
        ("id",                 "String",  "pk"),
        ("shipping_method_id", "String",  "fk"),
        ("code",               "String",  ""),
        ("rate",               "Decimal", ""),
        ("tax_rate_id",        "String?", ""),
    ]),
    ("OrderAddress", "order", [
        ("id",                "String",  "pk"),
        ("first_name",        "String?", ""),
        ("last_name",         "String?", ""),
        ("address_1 / city",  "String?", ""),
        ("country_code",      "String?", ""),
        ("shipping_order_id", "String?", "fk"),
        ("billing_order_id",  "String?", "fk"),
    ]),
    ("OrderSummary", "order", [
        ("id",             "String",  "pk"),
        ("order_id",       "String",  "fk"),
        ("total",          "Decimal", ""),
        ("subtotal",       "Decimal", ""),
        ("tax_total",      "Decimal", ""),
        ("discount_total", "Decimal", ""),
        ("shipping_total", "Decimal", ""),
    ]),
    ("OrderTransaction", "order", [
        ("id",            "String",  "pk"),
        ("order_id",      "String",  "fk"),
        ("amount",        "Decimal", ""),
        ("currency_code", "String",  ""),
        ("reference_id",  "String?", ""),
    ]),
    ("OrderCreditLine", "order", [
        ("id",           "String",  "pk"),
        ("order_id",     "String",  "fk"),
        ("version",      "Int",     ""),
        ("reference",    "String?", ""),
        ("reference_id", "String?", ""),
        ("amount",       "Decimal", ""),
    ]),
    ("OrderChange", "order", [
        ("id",           "String",           "pk"),
        ("order_id",     "String",           "fk"),
        ("status",       "OrderChangeStatus",""),
        ("change_type",  "OrderChangeType?", ""),
        ("requested_by", "String?",          ""),
        ("confirmed_by", "String?",          ""),
    ]),
    ("OrderChangeAction", "order", [
        ("id",              "String",  "pk"),
        ("order_change_id", "String",  "fk"),
        ("action",          "String",  ""),
        ("amount",          "Decimal?",""),
    ]),
    ("Return", "order", [
        ("id",            "String",      "pk"),
        ("order_id",      "String",      "fk"),
        ("status",        "ReturnStatus",""),
        ("refund_amount", "Decimal?",    ""),
    ]),
    ("ReturnItem", "order", [
        ("id",                "String",  "pk"),
        ("return_id",         "String",  "fk"),
        ("item_id",           "String",  "fk"),
        ("reason_id",         "String?", "fk"),
        ("quantity",          "Decimal", ""),
        ("received_quantity", "Decimal", ""),
        ("damaged_quantity",  "Decimal", ""),
    ]),
    ("ReturnReason", "order", [
        ("id",                      "String",  "pk"),
        ("value",                   "String",  ""),
        ("label",                   "String",  ""),
        ("parent_return_reason_id", "String?", "fk"),
    ]),
    ("Claim", "order", [
        ("id",            "String",    "pk"),
        ("order_id",      "String",    "fk"),
        ("return_id",     "String?",   "fk"),
        ("type",          "ClaimType", ""),
        ("refund_amount", "Decimal?",  ""),
    ]),
    ("OrderClaimItem", "order", [
        ("id",                 "String",  "pk"),
        ("claim_id",           "String",  "fk"),
        ("item_id",            "String",  "fk"),
        ("reason",             "String?", ""),
        ("quantity",           "Decimal", ""),
        ("is_additional_item", "Boolean", ""),
    ]),
    ("OrderClaimItemImage", "order", [
        ("id",            "String", "pk"),
        ("claim_item_id", "String", "fk"),
        ("url",           "String", ""),
    ]),
    ("Exchange", "order", [
        ("id",             "String",  "pk"),
        ("order_id",       "String",  "fk"),
        ("return_id",      "String?", "fk"),
        ("difference_due", "Decimal?",""),
    ]),
    ("OrderExchangeItem", "order", [
        ("id",          "String",  "pk"),
        ("exchange_id", "String",  "fk"),
        ("item_id",     "String",  "fk"),
        ("quantity",    "Decimal", ""),
    ]),
    # 결제
    ("PaymentCollection", "pay", [
        ("id",                "String",                  "pk"),
        ("currency_code",     "String",                  ""),
        ("amount",            "Decimal",                 ""),
        ("authorized_amount", "Decimal?",                ""),
        ("captured_amount",   "Decimal?",                ""),
        ("refunded_amount",   "Decimal?",                ""),
        ("status",            "PaymentCollectionStatus", ""),
    ]),
    ("Payment", "pay", [
        ("id",                    "String",        "pk"),
        ("payment_collection_id", "String",        "fk"),
        ("provider_id",           "String",        "fk"),
        ("amount",                "Decimal",       ""),
        ("currency_code",         "String",        ""),
        ("status",                "PaymentStatus", ""),
        ("customer_id",           "String?",       ""),
    ]),
    ("PaymentSession", "pay", [
        ("id",                    "String",               "pk"),
        ("payment_collection_id", "String",               "fk"),
        ("provider_id",           "String",               "fk"),
        ("amount",                "Decimal",              ""),
        ("currency_code",         "String",               ""),
        ("status",                "PaymentSessionStatus", ""),
        ("authorized_at",         "DateTime?",            ""),
    ]),
    ("Capture", "pay", [
        ("id",         "String",  "pk"),
        ("payment_id", "String",  "fk"),
        ("amount",     "Decimal", ""),
        ("created_by", "String?", ""),
    ]),
    ("Refund", "pay", [
        ("id",               "String",  "pk"),
        ("payment_id",       "String",  "fk"),
        ("amount",           "Decimal", ""),
        ("refund_reason_id", "String?", ""),
        ("note",             "String?", ""),
    ]),
    ("PaymentProvider", "pay", [
        ("id",         "String",  "pk"),
        ("is_enabled", "Boolean", ""),
    ]),
    # 배송
    ("FulfillmentSet", "ff", [
        ("id",   "String", "pk"),
        ("name", "String", ""),
        ("type", "String", ""),
    ]),
    ("ServiceZone", "ff", [
        ("id",                 "String", "pk"),
        ("fulfillment_set_id", "String", "fk"),
        ("name",               "String", ""),
    ]),
    ("GeoZone", "ff", [
        ("id",                    "String",      "pk"),
        ("service_zone_id",       "String",      "fk"),
        ("type",                  "GeoZoneType", ""),
        ("country_code",          "String",      ""),
        ("province_code / city",  "String?",     ""),
    ]),
    ("ShippingProfile", "ff", [
        ("id",   "String", "pk"),
        ("name", "String", ""),
        ("type", "String", ""),
    ]),
    ("ShippingOption", "ff", [
        ("id",                  "String",                  "pk"),
        ("service_zone_id",     "String",                  "fk"),
        ("shipping_profile_id", "String?",                 "fk"),
        ("provider_id",         "String?",                 "fk"),
        ("name",                "String",                  ""),
        ("price_type",          "ShippingOptionPriceType", ""),
    ]),
    ("Fulfillment", "ff", [
        ("id",                 "String",    "pk"),
        ("provider_id",        "String?",   "fk"),
        ("shipping_option_id", "String?",   "fk"),
        ("location_id",        "String?",   ""),
        ("shipped_at",         "DateTime?", ""),
        ("delivered_at",       "DateTime?", ""),
        ("canceled_at",        "DateTime?", ""),
    ]),
    ("FulfillmentItem", "ff", [
        ("id",                "String",  "pk"),
        ("fulfillment_id",    "String",  "fk"),
        ("title",             "String",  ""),
        ("quantity",          "Int",     ""),
        ("line_item_id",      "String?", ""),
        ("inventory_item_id", "String?", ""),
    ]),
    ("FulfillmentLabel", "ff", [
        ("id",              "String",  "pk"),
        ("fulfillment_id",  "String",  "fk"),
        ("tracking_number", "String",  ""),
        ("tracking_url",    "String?", ""),
        ("label_url",       "String?", ""),
    ]),
    ("FulfillmentProvider", "ff", [
        ("id",         "String",  "pk"),
        ("is_enabled", "Boolean", ""),
    ]),
    # 프로모션
    ("Campaign", "promo", [
        ("id",                  "String",    "pk"),
        ("name",                "String",    ""),
        ("identifier",          "String",    ""),
        ("starts_at / ends_at", "DateTime?", ""),
    ]),
    ("CampaignBudget", "promo", [
        ("id",            "String",            "pk"),
        ("campaign_id",   "String",            "fk"),
        ("type",          "CampaignBudgetType",""),
        ("limit",         "Decimal?",          ""),
        ("used",          "Decimal",           ""),
        ("currency_code", "String?",           ""),
    ]),
    ("Promotion", "promo", [
        ("id",           "String",          "pk"),
        ("campaign_id",  "String?",         "fk"),
        ("code",         "String",          ""),
        ("type",         "PromotionType",   ""),
        ("is_automatic", "Boolean",         ""),
        ("status",       "PromotionStatus", ""),
    ]),
    ("ApplicationMethod", "promo", [
        ("id",                     "String",                      "pk"),
        ("promotion_id",           "String",                      "fk"),
        ("type",                   "ApplicationMethodType",       ""),
        ("value",                  "Decimal?",                    ""),
        ("target_type",            "ApplicationMethodTargetType", ""),
        ("allocation",             "ApplicationMethodAllocation?",""),
        ("max_quantity",           "Int?",                        ""),
        ("apply_to_quantity",      "Int?",                        ""),
        ("buy_rules_min_quantity", "Int?",                        ""),
    ]),
    ("PromotionRule", "promo", [
        ("id",                           "String",                "pk"),
        ("promotion_id",                 "String?",               "fk"),
        ("application_method_target_id", "String?",               "fk"),
        ("application_method_buy_id",    "String?",               "fk"),
        ("attribute",                    "String",                ""),
        ("operator",                     "PromotionRuleOperator", ""),
    ]),
    ("PromotionRuleValue", "promo", [
        ("id",                "String", "pk"),
        ("promotion_rule_id", "String", "fk"),
        ("value",             "String", ""),
    ]),
]

# ── 관계 정의 ─────────────────────────────────────────────────────────────────
# (parent, child, parent_card, child_card, edge_label)
# card: "1" = exactly one  |  "0..1" = zero or one  |  "N" = one or more  |  "0..N" = zero or more
RELS = [
    # 주문 — Order 직속
    ("Order", "OrderItem",           "1",    "0..N", ""),
    ("Order", "OrderShippingMethod", "1",    "0..N", ""),
    ("Order", "OrderSummary",        "1",    "1",    ""),
    ("Order", "OrderTransaction",    "1",    "0..N", ""),
    ("Order", "OrderCreditLine",     "1",    "0..N", ""),
    ("Order", "OrderChange",         "1",    "0..N", ""),
    ("Order", "OrderAddress",        "1",    "0..N", "shipping/billing"),
    ("Order", "Return",              "1",    "0..N", ""),
    ("Order", "Claim",               "1",    "0..N", ""),
    ("Order", "Exchange",            "1",    "0..N", ""),
    # OrderItem ↔ OrderLineItem (이중 레이어)
    ("OrderItem",           "OrderLineItem",              "1",    "1",    "snapshot"),
    # LineItem 하위
    ("OrderLineItem",       "OrderLineItemAdjustment",    "1",    "0..N", ""),
    ("OrderLineItem",       "OrderLineItemTaxLine",       "1",    "0..N", ""),
    # ShippingMethod 하위
    ("OrderShippingMethod", "OrderShippingMethodAdjustment", "1", "0..N", ""),
    ("OrderShippingMethod", "OrderShippingMethodTaxLine", "1",    "0..N", ""),
    # OrderChange
    ("OrderChange",         "OrderChangeAction",          "1",    "0..N", ""),
    # Return 계열
    ("Return",              "ReturnItem",                 "1",    "0..N", ""),
    ("ReturnReason",        "ReturnItem",                 "0..1", "0..N", ""),
    ("ReturnReason",        "ReturnReason",               "0..1", "0..N", "sub-reason"),
    ("Return",              "Claim",                      "0..1", "0..N", ""),
    ("Return",              "Exchange",                   "0..1", "0..N", ""),
    # Claim 계열
    ("Claim",               "OrderClaimItem",             "1",    "0..N", ""),
    ("OrderClaimItem",      "OrderClaimItemImage",        "1",    "0..N", ""),
    # Exchange 계열
    ("Exchange",            "OrderExchangeItem",          "1",    "0..N", ""),
    # LineItem → Return/Claim/Exchange 아이템 참조
    ("OrderLineItem",       "ReturnItem",                 "1",    "0..N", ""),
    ("OrderLineItem",       "OrderClaimItem",             "1",    "0..N", ""),
    ("OrderLineItem",       "OrderExchangeItem",          "1",    "0..N", ""),
    # 결제
    ("PaymentCollection", "PaymentSession", "1",    "0..N", ""),
    ("PaymentCollection", "Payment",        "1",    "0..N", ""),
    ("Payment",           "Capture",        "1",    "0..N", ""),
    ("Payment",           "Refund",         "1",    "0..N", ""),
    ("PaymentProvider",   "Payment",        "1",    "0..N", ""),
    ("PaymentProvider",   "PaymentSession", "1",    "0..N", ""),
    # 배송
    ("FulfillmentSet",     "ServiceZone",    "1",    "0..N", ""),
    ("ServiceZone",        "GeoZone",        "1",    "0..N", ""),
    ("ServiceZone",        "ShippingOption", "1",    "0..N", ""),
    ("ShippingProfile",    "ShippingOption", "0..1", "0..N", ""),
    ("FulfillmentProvider","ShippingOption", "0..1", "0..N", ""),
    ("FulfillmentProvider","Fulfillment",    "0..1", "0..N", ""),
    ("ShippingOption",     "Fulfillment",    "0..1", "0..N", ""),
    ("Fulfillment",        "FulfillmentItem",  "1",  "0..N", ""),
    ("Fulfillment",        "FulfillmentLabel", "1",  "0..N", ""),
    # 프로모션
    ("Campaign",          "CampaignBudget",    "1",    "0..1", ""),
    ("Campaign",          "Promotion",         "0..1", "0..N", ""),
    ("Promotion",         "ApplicationMethod", "1",    "0..1", ""),
    ("Promotion",         "PromotionRule",      "0..1", "0..N", ""),
    ("ApplicationMethod", "PromotionRule",      "0..1", "0..N", "target"),
    ("ApplicationMethod", "PromotionRule",      "0..1", "0..N", "buy"),
    ("PromotionRule",     "PromotionRuleValue", "1",    "0..N", ""),
]


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def entity_label(name: str, fields: list, domain: str) -> str:
    hdr = C[domain]["hdr"]
    bg  = C[domain]["bg"]

    rows = [
        f'<TR>'
        f'<TD BGCOLOR="{hdr}" ALIGN="CENTER" COLSPAN="2" CELLPADDING="4">'
        f'<FONT COLOR="white" POINT-SIZE="8.5"><B>{esc(name)}</B></FONT>'
        f'</TD></TR>'
    ]

    for fname, ftype, fkind in fields:
        if fkind == "pk":
            badge, fc, fs = "PK", "#0D2D6B", "B"
        elif fkind == "fk":
            badge, fc, fs = "FK", "#8B1A1A", "I"
        else:
            badge, fc, fs = "",  "#333333", ""

        badge_inner = f"<B>{badge}</B>" if badge else "&nbsp;"
        badge_cell = (
            f'<TD BGCOLOR="{bg}" WIDTH="22" ALIGN="CENTER" CELLPADDING="2">'
            f'<FONT COLOR="{fc}" POINT-SIZE="5.5">{badge_inner}</FONT></TD>'
        )
        field_str = f"{esc(fname)}: {esc(ftype)}"
        if fs == "B":
            text = f"<B>{field_str}</B>"
        elif fs == "I":
            text = f"<I>{field_str}</I>"
        else:
            text = field_str

        field_cell = (
            f'<TD BGCOLOR="{bg}" ALIGN="LEFT" CELLPADDING="2">'
            f'<FONT COLOR="{fc}" POINT-SIZE="7">{text}</FONT></TD>'
        )
        rows.append(f"<TR>{badge_cell}{field_cell}</TR>")

    body = "\n      ".join(rows)
    return (
        f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">\n'
        f'      {body}\n'
        f'    </TABLE>>'
    )


def arrow_style(card: str) -> str:
    """cardinality → graphviz arrowhead/tail name"""
    return {
        "1":    "tee",
        "0..1": "teeodot",
        "N":    "crow",
        "0..N": "crowodot",
    }.get(card, "none")


def card_label(card: str) -> str:
    return {"1": "1", "0..1": "0..1", "N": "N", "0..N": "0..N"}.get(card, "")


def build_dot() -> str:
    lines: list[str] = []

    lines += [
        "digraph MedusaERD {",
        "  graph [",
        "    rankdir=LR",
        '    splines=polyline',
        "    nodesep=0.55",
        "    ranksep=1.4",
        "    compound=true",
        "    pad=0.5",
        "  ]",
        "  node [shape=none margin=0]",
        '  edge [fontsize=7 fontname="Helvetica" arrowsize=0.75 dir=both]',
        "",
    ]

    # Group entities by domain
    by_domain: dict[str, list] = {}
    for name, domain, fields in ENTITIES:
        by_domain.setdefault(domain, []).append((name, fields))

    for dom in ["order", "pay", "ff", "promo"]:
        label = DOMAIN_LABELS[dom]
        bdr   = C[dom]["bdr"]
        bg    = C[dom]["bg"]
        lines += [
            f"  subgraph cluster_{dom} {{",
            f'    label="{label}"',
            f"    style=filled",
            f'    fillcolor="{bg}"',
            f'    color="{bdr}"',
            f"    penwidth=1.8",
            f'    fontname="Helvetica-Bold"',
            f"    fontsize=12",
            f'    fontcolor="{bdr}"',
            "",
        ]
        for name, fields in by_domain.get(dom, []):
            lbl = entity_label(name, fields, dom)
            lines.append(f"    {name} [label={lbl}]")
        lines += ["  }", ""]

    lines.append("  // Relationships")
    # Track multi-edges between same node pair
    edge_count: dict[tuple, int] = {}
    for parent, child, pc, cc, elabel in RELS:
        key = (parent, child)
        edge_count[key] = edge_count.get(key, 0) + 1

    edge_seen: dict[tuple, int] = {}
    for parent, child, pc, cc, elabel in RELS:
        tail = arrow_style(pc)
        head = arrow_style(cc)
        tl   = card_label(pc)
        hl   = card_label(cc)
        key  = (parent, child)
        edge_seen[key] = edge_seen.get(key, 0) + 1
        multi = edge_count[key] > 1

        attrs: list[str] = [
            f"arrowtail={tail}",
            f"arrowhead={head}",
            f'taillabel="{tl}"',
            f'headlabel="{hl}"',
        ]
        if elabel:
            attrs.append(f'label=" {elabel} "')
        if multi:
            # offset second edge so it doesn't overlap
            attrs.append("constraint=false")
            if edge_seen[key] > 1:
                attrs.append('style="dashed"')

        lines.append(f"  {parent} -> {child} [{' '.join(attrs)}]")

    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    if not shutil.which("dot"):
        print("graphviz 없음 — brew install graphviz 실행 필요")
        sys.exit(1)

    dot = build_dot()
    with open(DOT_FILE, "w", encoding="utf-8") as f:
        f.write(dot)
    print(f"DOT 파일: {DOT_FILE}")

    # A2 가로 크기 렌더링 (더 넓게)
    res = subprocess.run(
        ["dot", "-Tpdf", "-Gsize=25,17", f"-o{PDF_FILE}", DOT_FILE],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        print("렌더링 오류:", res.stderr[:500])
        sys.exit(1)
    print(f"ERD PDF 저장: {PDF_FILE}")


if __name__ == "__main__":
    main()
