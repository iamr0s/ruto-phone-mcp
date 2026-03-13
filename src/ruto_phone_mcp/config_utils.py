from __future__ import annotations

from pathlib import Path


def project_root_from_module(module_file: str) -> Path:
    return Path(module_file).resolve().parents[2]


def resolve_default_config_file(module_file: str, filename: str) -> Path:
    root = project_root_from_module(module_file)
    primary = root / "config" / filename
    fallback = root / "config-example" / filename
    if primary.exists():
        return primary.resolve()
    if fallback.exists():
        return fallback.resolve()
    return primary.resolve()
