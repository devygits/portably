#!/usr/bin/env python3
"""Namespace helpers for Portably's generated public CSS contract."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "portably.config.json"
HOME_URL = "https://github.com/devygits/portably"
NAMESPACE_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


def validate_namespace(value: str) -> str:
    """Return a valid CSS-safe namespace or raise ValueError."""
    if not isinstance(value, str) or not NAMESPACE_RE.fullmatch(value):
        raise ValueError(
            "Namespace must start with a lowercase letter and contain only "
            "lowercase letters, numbers, and single hyphen-separated segments"
        )
    return value


def default_namespace() -> str:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    return validate_namespace(data["defaultNamespace"])


def portably_version() -> str:
    """The Portably version a project records in its portably.config.json ("portably": "1.0")."""
    return json.loads(CONFIG.read_text(encoding="utf-8"))["version"]


def namespace_for(path: Path | str) -> str:
    """Resolve a project namespace from the nearest portably.config.json.

    A generated project uses {"namespace": "..."}; the framework repository uses
    {"defaultNamespace": "pbly"}. If no config is found, the shipped default is used.
    """
    path = Path(path).resolve()
    start = path if path.is_dir() else path.parent
    for directory in (start, *start.parents):
        config = directory / "portably.config.json"
        if config.is_file():
            data = json.loads(config.read_text(encoding="utf-8"))
            value = data.get("namespace", data.get("defaultNamespace"))
            if value is None:
                raise ValueError(f"Missing namespace/defaultNamespace in {config}")
            return validate_namespace(value)
    return default_namespace()


def replace_namespace(text: str, source: str, target: str) -> str:
    """Rewrite Portably-owned namespace identifiers in text.

    The namespace is intentionally a project-setup concern, not a runtime theme.
    Portably reserves the configured root class, class prefix, custom-property
    prefix, and low-precedence layer prefix as one namespace family.
    """
    source = validate_namespace(source)
    target = validate_namespace(target)
    if source == target:
        return text

    text = text.replace(f"--{source}-", f"--{target}-")
    text = text.replace(f"{source}-", f"{target}-")
    text = re.sub(rf"(?<![A-Za-z0-9_-]){re.escape(source)}(?![A-Za-z0-9_-])", target, text)
    return text
