#!/usr/bin/env python3
"""
Medusa ERD PDF — prisma 파일당 1페이지 PDF 생성
실행: python3 gen_erd.py
출력: erd_output/<name>.pdf x 13 + erd_all.pdf (13페이지)
"""

import re
import subprocess
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

BASE = Path(__file__).parent
OUT_DIR = BASE / "erd_output"
FINAL_PDF = BASE / "erd_all.pdf"

# ── 페이지 크기 (인치, A2 가로) ───────────────────────────────────────────────
PAGE_W, PAGE_H = "20", "14"

# ── 파일명별 색상 ──────────────────────────────────────────────────────────────
COLOR_MAP: dict[str, dict] = {
    "cart":           {"hdr": "#1A5276", "bg": "#D6EAF8", "bdr": "#1A5276"},
    "customer":       {"hdr": "#0E6655", "bg": "#D0ECE7", "bdr": "#0E6655"},
    "fulfillment":    {"hdr": "#784212", "bg": "#FDEBD0", "bdr": "#784212"},
    "inventory":      {"hdr": "#1D6A39", "bg": "#D5F5E3", "bdr": "#1D6A39"},
    "order":          {"hdr": "#1B4F72", "bg": "#D6EAF8", "bdr": "#1B4F72"},
    "payment":        {"hdr": "#145A32", "bg": "#D5F5E3", "bdr": "#145A32"},
    "pricing":        {"hdr": "#4A235A", "bg": "#E8DAEF", "bdr": "#4A235A"},
    "product":        {"hdr": "#641E16", "bg": "#FADBD8", "bdr": "#641E16"},
    "promotion":      {"hdr": "#6E2F8A", "bg": "#F5EEF8", "bdr": "#6E2F8A"},
    "region":         {"hdr": "#0E4D91", "bg": "#D6EAF8", "bdr": "#0E4D91"},
    "sales-channel":  {"hdr": "#5D4037", "bg": "#EFEBE9", "bdr": "#5D4037"},
    "stock-location": {"hdr": "#4D4D00", "bg": "#FDFDE7", "bdr": "#4D4D00"},
    "tax":            {"hdr": "#2C2C2C", "bg": "#F2F3F4", "bdr": "#2C2C2C"},
}
DEFAULT_COLOR = {"hdr": "#2C3E50", "bg": "#EAECEE", "bdr": "#2C3E50"}

# ── 노드에서 생략할 노이즈 필드 ───────────────────────────────────────────────
SKIP_FIELDS = {"created_at", "updated_at", "deleted_at", "metadata"}
SKIP_PREFIX = ("raw_",)


# ─────────────────────────────────────────────────────────────────────────────
# 데이터 모델
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParsedField:
    name: str
    base_type: str
    is_optional: bool
    is_list: bool
    # pk / fk / scalar / relation_owner / relation_ref
    kind: str
    # relation_owner 전용
    relation_name: Optional[str] = None
    relation_fk_fields: list = field(default_factory=list)

@dataclass
class ParsedModel:
    name: str
    fields: list[ParsedField] = field(default_factory=list)
    composite_pk: list[str] = field(default_factory=list)

@dataclass
class ParsedSchema:
    models: list[ParsedModel] = field(default_factory=list)
    enum_names: set[str] = field(default_factory=set)


# ─────────────────────────────────────────────────────────────────────────────
# 파서
# ─────────────────────────────────────────────────────────────────────────────

_SCALAR_TYPES = {
    "String", "Int", "Float", "Boolean", "DateTime",
    "Decimal", "Json", "Bytes", "BigInt",
}


def _strip_comment(line: str) -> str:
    """인라인 주석(// ...) 제거. 문자열 내부 // 는 prisma에서 사실상 없으므로 단순 처리."""
    idx = line.find("//")
    return line[:idx].rstrip() if idx != -1 else line.rstrip()


def parse_prisma(text: str) -> ParsedSchema:
    schema = ParsedSchema()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stripped = _strip_comment(lines[i]).strip()

        # enum 블록
        m = re.match(r"^enum\s+(\w+)\s*\{", stripped)
        if m:
            schema.enum_names.add(m.group(1))
            i += 1
            while i < len(lines):
                if _strip_comment(lines[i]).strip() == "}":
                    i += 1
                    break
                i += 1
            continue

        # model 블록
        m = re.match(r"^model\s+(\w+)\s*\{", stripped)
        if m:
            model = ParsedModel(name=m.group(1))
            i += 1
            raw_fields: list[str] = []
            while i < len(lines):
                fline = _strip_comment(lines[i]).strip()
                if fline == "}":
                    i += 1
                    break
                if fline and not fline.startswith("@@"):
                    raw_fields.append(fline)
                # composite pk
                cm = re.match(r"@@id\s*\(\s*\[([^\]]+)\]", fline)
                if cm:
                    model.composite_pk = [f.strip() for f in cm.group(1).split(",")]
                i += 1

            # 1차 파싱: relation_owner 의 fk 필드 이름 수집
            fk_field_names: set[str] = set()
            for raw in raw_fields:
                rm = re.search(r"@relation\s*\((?:\"[^\"]*\"\s*,\s*)?fields\s*:\s*\[([^\]]+)\]", raw)
                if rm:
                    for fn in rm.group(1).split(","):
                        fk_field_names.add(fn.strip())

            # 2차 파싱: 각 필드 분류
            all_model_names: set[str] = set()  # 첫 패스에서 확정 불가 → 후처리
            for raw in raw_fields:
                parts = raw.split()
                if len(parts) < 2:
                    continue
                fname = parts[0]
                ftype_raw = parts[1]

                is_optional = ftype_raw.endswith("?")
                is_list = ftype_raw.endswith("[]")
                base_type = re.sub(r"[\?\[\]]+$", "", ftype_raw)

                rest = " ".join(parts[2:])

                # @relation 여부
                rel_m = re.search(
                    r'@relation\s*\((?:"([^"]*)"\s*,\s*)?(?:fields\s*:\s*\[([^\]]*)\])',
                    rest,
                )
                is_relation_owner = bool(rel_m)

                # 역참조 relation (fields 없음)
                rev_m = re.search(r'@relation\s*\(', rest)
                is_relation_ref_explicit = bool(rev_m) and not is_relation_owner

                is_scalar_type = base_type in _SCALAR_TYPES

                if is_relation_owner:
                    rel_name = rel_m.group(1) if rel_m.group(1) else None
                    fk_fields = [f.strip() for f in rel_m.group(2).split(",")] if rel_m.group(2) else []
                    pf = ParsedField(
                        name=fname,
                        base_type=base_type,
                        is_optional=is_optional,
                        is_list=is_list,
                        kind="relation_owner",
                        relation_name=rel_name,
                        relation_fk_fields=fk_fields,
                    )
                elif not is_scalar_type and not base_type in schema.enum_names:
                    # 역참조 (relation_ref) — 비스칼라인데 relation_owner 아님
                    pf = ParsedField(
                        name=fname,
                        base_type=base_type,
                        is_optional=is_optional,
                        is_list=is_list,
                        kind="relation_ref",
                    )
                else:
                    # pk / fk / scalar 분류
                    if "@id" in rest or fname in model.composite_pk:
                        kind = "pk"
                    elif fname in fk_field_names:
                        kind = "fk"
                    else:
                        kind = "scalar"
                    pf = ParsedField(
                        name=fname,
                        base_type=base_type,
                        is_optional=is_optional,
                        is_list=is_list,
                        kind=kind,
                    )
                model.fields.append(pf)

            schema.models.append(model)
            continue

        i += 1

    # relation_ref / relation_owner 의 base_type 이 실제 모델인지 확인해 scalar 재분류
    model_names = {m.name for m in schema.models}
    for model in schema.models:
        for f in model.fields:
            if f.kind == "relation_ref" and f.base_type not in model_names:
                # enum 이거나 아직 인식 안 된 타입 → scalar 처리
                f.kind = "scalar"

    return schema


# ─────────────────────────────────────────────────────────────────────────────
# DOT 생성
# ─────────────────────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _arrow(card: str) -> str:
    return {"1": "tee", "0..1": "teeodot", "N": "crow", "0..N": "crowodot"}.get(card, "none")


def _card_label(card: str) -> str:
    return card


def _node_label(model: ParsedModel, color: dict) -> str:
    hdr = color["hdr"]
    bg = color["bg"]

    rows = [
        f'<TR><TD BGCOLOR="{hdr}" ALIGN="CENTER" COLSPAN="2" CELLPADDING="4">'
        f'<FONT COLOR="white" POINT-SIZE="9"><B>{_esc(model.name)}</B></FONT></TD></TR>'
    ]

    for f in model.fields:
        if f.kind in ("relation_owner", "relation_ref"):
            continue
        if f.name in SKIP_FIELDS or any(f.name.startswith(p) for p in SKIP_PREFIX):
            continue

        if f.kind == "pk":
            badge, fc, style = "PK", "#0D2D6B", "B"
        elif f.kind == "fk":
            badge, fc, style = "FK", "#8B1A1A", "I"
        else:
            badge, fc, style = "", "#333333", ""

        badge_cell = (
            f'<TD BGCOLOR="{bg}" WIDTH="24" ALIGN="CENTER" CELLPADDING="2">'
            f'<FONT COLOR="{fc}" POINT-SIZE="5.5"><B>{badge}</B></FONT></TD>'
            if badge else
            f'<TD BGCOLOR="{bg}" WIDTH="24" CELLPADDING="2">&nbsp;</TD>'
        )

        type_str = f.base_type + ("?" if f.is_optional else "") + ("[]" if f.is_list else "")
        text = f"{_esc(f.name)}: {_esc(type_str)}"
        if style == "B":
            text = f"<B>{text}</B>"
        elif style == "I":
            text = f"<I>{text}</I>"

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


def build_dot(schema_name: str, schema: ParsedSchema) -> str:
    color = COLOR_MAP.get(schema_name, DEFAULT_COLOR)
    model_names = {m.name for m in schema.models}

    lines: list[str] = [
        f'digraph "{schema_name}" {{',
        f'  graph [rankdir=LR splines=polyline nodesep=0.5 ranksep=1.2',
        f'         pad=0.5 label="{schema_name}" labelloc=t fontsize=16',
        f'         fontname="Helvetica-Bold"]',
        f'  node  [shape=none margin=0]',
        f'  edge  [fontsize=7 fontname="Helvetica" arrowsize=0.75 dir=both]',
        "",
    ]

    # 노드
    for model in schema.models:
        lbl = _node_label(model, color)
        lines.append(f'  {model.name} [label={lbl}]')

    lines.append("")
    lines.append("  // Relations")

    # 엣지: relation_owner 기준
    edge_count: dict[tuple, int] = {}
    edges = []
    for model in schema.models:
        for f in model.fields:
            if f.kind != "relation_owner":
                continue
            if f.base_type not in model_names:
                continue
            parent, child = f.base_type, model.name
            key = (parent, child)
            edge_count[key] = edge_count.get(key, 0) + 1
            edges.append((parent, child, f))

    edge_seen: dict[tuple, int] = {}
    for parent, child, f in edges:
        # FK 스칼라가 optional이면 0..N, 아니면 N
        fk_optional = any(
            fi.is_optional for fi in
            next(m for m in schema.models if m.name == child).fields
            if fi.name in f.relation_fk_fields
        ) if f.relation_fk_fields else True

        child_card = "0..N" if fk_optional else "N"
        parent_card = "1"

        key = (parent, child)
        edge_seen[key] = edge_seen.get(key, 0) + 1
        multi = edge_count[key] > 1

        attrs = [
            f'arrowtail={_arrow(parent_card)}',
            f'arrowhead={_arrow(child_card)}',
            f'taillabel="{_card_label(parent_card)}"',
            f'headlabel="{_card_label(child_card)}"',
        ]
        if f.relation_name:
            short = f.relation_name[:20] + ("…" if len(f.relation_name) > 20 else "")
            attrs.append(f'label=" {short} "')
        if multi and edge_seen[key] > 1:
            attrs.append('style="dashed" constraint=false')

        lines.append(f'  {parent} -> {child} [{" ".join(attrs)}]')

    lines.append("}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if not shutil.which("dot"):
        print("graphviz 없음 — brew install graphviz")
        sys.exit(1)
    if not shutil.which("pdfunite"):
        print("pdfunite 없음 — brew install poppler")
        sys.exit(1)

    OUT_DIR.mkdir(exist_ok=True)
    prisma_files = sorted(BASE.glob("schema.*.prisma"))
    if not prisma_files:
        print("prisma 파일 없음")
        sys.exit(1)

    pdf_files: list[Path] = []
    for pf in prisma_files:
        schema_name = pf.stem.replace("schema.", "")
        print(f"  파싱 중: {pf.name} ...", end=" ", flush=True)

        text = pf.read_text(encoding="utf-8")
        schema = parse_prisma(text)

        dot_src = build_dot(schema_name, schema)
        dot_path = OUT_DIR / f"{schema_name}.dot"
        pdf_path = OUT_DIR / f"{schema_name}.pdf"
        dot_path.write_text(dot_src, encoding="utf-8")

        result = subprocess.run(
            [
                "dot", "-Tpdf",
                f"-Gpage={PAGE_W},{PAGE_H}",
                f"-Gsize={float(PAGE_W) - 1},{float(PAGE_H) - 1}",
                "-Gmargin=0.5",
                "-Gratio=compress",
                f"-o{pdf_path}",
                str(dot_path),
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"오류!\n{result.stderr[:300]}")
            sys.exit(1)

        model_count = len(schema.models)
        print(f"모델 {model_count}개 ✓")
        pdf_files.append(pdf_path)

    print(f"\n  병합 중: {len(pdf_files)}개 PDF → {FINAL_PDF.name} ...", end=" ", flush=True)
    result = subprocess.run(
        ["pdfunite"] + [str(p) for p in pdf_files] + [str(FINAL_PDF)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"오류!\n{result.stderr[:300]}")
        sys.exit(1)
    print("✓")
    print(f"\nERD 생성 완료: {FINAL_PDF}  ({len(pdf_files)}페이지)")


if __name__ == "__main__":
    main()
