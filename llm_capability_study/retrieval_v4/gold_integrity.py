"""Resolve local private Gold hash without modifying the public benchmark manifest."""
from __future__ import annotations
import json
from pathlib import Path


def expected_gold_sha(root: Path, manifest: dict) -> str:
    local = root / "private" / "gold_registry.json"
    if not local.exists():
        return manifest["gold_sha256"]
    registry = json.loads(local.read_text(encoding="utf-8"))
    for name in ("cases_sha256", "annex_sha256"):
        if registry.get(name) != manifest.get(name):
            raise ValueError("로컬 Gold 등록정보와 공개 벤치마크 데이터가 다릅니다: " + name)
    value = registry.get("gold_sha256")
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("로컬 Gold SHA256 등록정보가 잘못되었습니다")
    return value
