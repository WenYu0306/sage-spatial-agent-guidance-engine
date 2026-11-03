"""M0 契约代码生成（make gen）。

从 schemas/*.schema.json 生成两端类型：
- Python：datamodel-code-generator → generated/python/<name>_models.py（Pydantic v2）
- TypeScript：json-schema-to-typescript（经 pnpm exec）→ generated/ts/<name>.d.ts

生成物入库；CI 用 git diff 检查"契约改了但没重新 gen"（契约先行）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # packages/api-contract
SCHEMAS = BASE / "schemas"
PY_OUT = BASE / "generated" / "python"
TS_OUT = BASE / "generated" / "ts"


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=BASE.parent.parent, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"gen 失败：{' '.join(cmd)}")
    if result.stdout.strip():
        print(result.stdout.strip()[-500:])


def main() -> int:
    schema_files = sorted(SCHEMAS.glob("*.schema.json"))
    if not schema_files:
        raise SystemExit("schemas/ 下没有 .schema.json")
    PY_OUT.mkdir(parents=True, exist_ok=True)
    TS_OUT.mkdir(parents=True, exist_ok=True)

    for f in schema_files:
        name = f.name.removesuffix(".schema.json")
        run([
            "uv", "run", "--package", "api-contract", "datamodel-codegen",
            "--input", str(f.relative_to(BASE.parent.parent)),
            "--input-file-type", "jsonschema",
            "--output", str((PY_OUT / f"{name}_models.py").relative_to(BASE.parent.parent)),
            "--output-model-type", "pydantic_v2.BaseModel",
            "--force",
        ])
        run([
            "pnpm", "exec", "json2ts",
            "--input", str(f.relative_to(BASE.parent.parent)),
            "--output", str((TS_OUT / f"{name}.d.ts").relative_to(BASE.parent.parent)),
        ])

    (PY_OUT / "__init__.py").write_text(
        '"""M0 生成的 Pydantic 模型（由 make gen 生成，禁止手改）。"""\n', encoding="utf-8"
    )
    print(f"\ngen 完成：{len(schema_files)} 个契约文件 → generated/python/ + generated/ts/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
