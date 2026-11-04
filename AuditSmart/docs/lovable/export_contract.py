"""Export the engine OpenAPI contract and a compact endpoint list for the Lovable prompts.

Run from the repo root:  engine/.venv/bin/python docs/lovable/export_contract.py
Writes docs/lovable/engine_openapi.json and docs/lovable/engine_endpoints.txt.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))
from app.main import create_app  # noqa: E402

spec = create_app().openapi()
out = ROOT / "docs" / "lovable"
(out / "engine_openapi.json").write_text(json.dumps(spec, indent=2, sort_keys=False) + "\n")
schemas = spec.get("components", {}).get("schemas", {})


def ref_name(s):
    if not s:
        return None
    if "$ref" in s:
        return s["$ref"].split("/")[-1]
    for k in ("anyOf", "allOf", "oneOf"):
        for x in s.get(k, []):
            n = ref_name(x)
            if n:
                return n
    return None


def fields(name):
    sc = schemas.get(name, {})
    req = set(sc.get("required", []))
    return ", ".join(p if p in req else p + "?" for p in sc.get("properties", {}))


lines = []
for path, ops in spec["paths"].items():
    for method, op in ops.items():
        if method not in ("get", "post", "put", "patch", "delete"):
            continue
        s = f"- {method.upper()} {path}: {(op.get('description') or op.get('summary') or '').strip().splitlines()[0].rstrip('.')}"
        q = [p["name"] + ("" if p.get("required") else "?") for p in op.get("parameters", []) if p.get("in") == "query"]
        if q:
            s += ". Query: " + ", ".join(q)
        body = op.get("requestBody", {}).get("content", {})
        for ct, c in body.items():
            n = ref_name(c.get("schema"))
            if n:
                s += f". Body ({ct}) {n}: {fields(n)}"
            break
        for code in ("200", "201", "202"):
            r = op.get("responses", {}).get(code)
            if r:
                n = ref_name(r.get("content", {}).get("application/json", {}).get("schema"))
                if n and schemas.get(n, {}).get("properties"):
                    s += f". Returns{' ' + code if code != '200' else ''} {n}: {fields(n)}"
                break
        lines.append(s)
(out / "engine_endpoints.txt").write_text("\n".join(lines) + "\n")
print(len(lines), "operations")

# Compact list used inside the 4.1 paste block (one Lovable message): no schema names,
# "q:" = query, "{...}" = JSON or form body fields, "->" = response fields, "?" = optional.
compact = []
for path, ops in spec["paths"].items():
    for method, op in ops.items():
        if method not in ("get", "post", "put", "patch", "delete"):
            continue
        s = f"{method.upper()} {path}"
        q = [p["name"] + ("" if p.get("required") else "?") for p in op.get("parameters", []) if p.get("in") == "query"]
        if q:
            s += " q:" + ",".join(q)
        for ct, c in op.get("requestBody", {}).get("content", {}).items():
            n = ref_name(c.get("schema"))
            if n:
                s += " {" + fields(n).replace(", ", ",") + "}" + (" multipart" if "multipart" in ct else "")
            break
        for code in ("200", "201", "202"):
            r = op.get("responses", {}).get(code)
            if r:
                n = ref_name(r.get("content", {}).get("application/json", {}).get("schema"))
                if n and schemas.get(n, {}).get("properties"):
                    s += f" ->{'' if code == '200' else code + ' '}" + fields(n).replace(", ", ",")
                break
        compact.append(s)
(out / "engine_endpoints_compact.txt").write_text("\n".join(compact) + "\n")
