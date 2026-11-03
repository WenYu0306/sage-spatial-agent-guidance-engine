"""M0 契约校验（make validate）。

检查项：
1. error-codes.yaml：码表全局唯一、每个码落在所属段 range 内、message 非空
2. schemas/*.schema.json：合法的 JSON Schema（draft 2020-12 元校验），自带 examples 全部通过自身校验
3. headers.yaml：ARCHITECTURE.md 8.3 的 5 个请求头全部登记
4. openapi/common.yaml：OpenAPI 3.1 骨架必备字段存在
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

BASE = Path(__file__).resolve().parent.parent  # packages/api-contract
SCHEMAS = BASE / "schemas"

REQUIRED_HEADERS = {"X-Tenant-Id", "X-Trace-Id", "Authorization", "X-Device-Id", "X-Client"}

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)
    print(f"  [FAIL] {msg}")


def ok(msg: str) -> None:
    print(f"  [ ok ] {msg}")


def check_error_codes() -> None:
    doc = yaml.safe_load((SCHEMAS / "error-codes.yaml").read_text(encoding="utf-8"))
    segments = doc.get("segments") or []
    if not segments:
        err("error-codes.yaml: segments 为空")
        return
    seen: dict[int, str] = {}
    for seg in segments:
        lo, hi = seg["range"]
        if not (0 <= lo <= hi <= 9999):
            err(f"段 {seg.get('name')}: range 非法 {seg['range']}")
            continue
        codes = seg.get("codes") or []
        if not codes:
            err(f"段 [{lo}-{hi}] {seg.get('name')}: 未登记任何错误码")
            continue
        for item in codes:
            code, message = item.get("code"), (item.get("message") or "").strip()
            if code in seen:
                err(f"错误码 {code} 重复登记（{seen[code]} 与 [{lo}-{hi}]）")
                continue
            if not (lo <= code <= hi):
                err(f"错误码 {code}（{message}）不在所属段 [{lo}-{hi}] 内")
                continue
            if not message:
                err(f"错误码 {code}: message 为空")
                continue
            seen[code] = f"[{lo}-{hi}]"
    if not any("error-codes" in e for e in errors):
        ok(f"error-codes.yaml：{len(segments)} 个段、{len(seen)} 个错误码，唯一性与分段检查通过")


def check_json_schemas() -> None:
    schema_files = sorted(SCHEMAS.glob("*.schema.json"))
    if not schema_files:
        err("schemas/ 下没有任何 .schema.json")
        return
    for f in schema_files:
        schema = json.loads(f.read_text(encoding="utf-8"))
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as e:  # noqa: BLE001
            err(f"{f.name}: 不是合法的 JSON Schema（{e}）")
            continue
        validator = Draft202012Validator(schema)
        for i, example in enumerate(schema.get("examples", [])):
            for v_err in validator.iter_errors(example):
                err(f"{f.name}: examples[{i}] 不符合自身 schema：{v_err.message}")
        ok(f"{f.name}：schema 合法，examples 自校验通过")


def check_headers() -> None:
    doc = yaml.safe_load((SCHEMAS / "headers.yaml").read_text(encoding="utf-8"))
    names = {h.get("name") for h in doc.get("headers", [])}
    missing = REQUIRED_HEADERS - names
    if missing:
        err(f"headers.yaml 缺少必登记请求头：{sorted(missing)}")
    else:
        ok("headers.yaml：5 个必带请求头齐全")


def check_openapi_skeleton() -> None:
    doc = yaml.safe_load((BASE / "openapi" / "common.yaml").read_text(encoding="utf-8"))
    failed = False
    for key in ("openapi", "info", "paths", "components"):
        if key not in doc:
            err(f"openapi/common.yaml 缺少必备字段：{key}")
            failed = True
    if not str(doc.get("openapi", "")).startswith("3.1"):
        err(f"openapi/common.yaml 应为 OpenAPI 3.1.x，当前：{doc.get('openapi')}")
        failed = True
    if not failed:
        ok("openapi/common.yaml：3.1 骨架字段齐全")


def main() -> int:
    print("== M0 契约校验 ==")
    check_error_codes()
    check_json_schemas()
    check_headers()
    check_openapi_skeleton()
    if errors:
        print(f"\nvalidate 失败：{len(errors)} 处问题")
        return 1
    print("\nvalidate 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
