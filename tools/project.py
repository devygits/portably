"""`portably init`: create a new project from the Portably starter."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from build_tokens import generate
from naming import default_namespace, portably_version, replace_namespace, validate_namespace

ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "starter"
TEXT_SUFFIXES = {".html", ".css", ".js", ".md", ".json", ".txt", ".svg"}
SKIP = {Path("tokens/tokens.css"), Path("portably.config.json"), Path("DESIGN-SYSTEM.md"), Path("DESIGN-SYSTEM.html")}
# Files every project keeps for the next person or agent; `fix` recreates them from the starter.
HANDOFF_FILES = ("README.md", "AGENTS.md")


class InitError(Exception):
    """The project can't be created; the message says why."""


def template(name, project, namespace):
    """A starter handoff file (README.md, AGENTS.md) written for this project and namespace."""
    text = replace_namespace((STARTER / name).read_text(encoding="utf-8"), default_namespace(), namespace)
    return text.replace("Project name", Path(project).name, 1)


def new_config(namespace):
    """The starter's portably.config.json with this project's namespace and no design source yet."""
    config = json.loads((STARTER / "portably.config.json").read_text(encoding="utf-8"))
    config.update({"portably": portably_version(), "namespace": namespace, "source": ""})
    return config


def create_project(target, namespace=None):
    """Copy the starter into an empty folder, with the project's namespace applied."""
    namespace = validate_namespace(namespace or default_namespace())
    source_ns = default_namespace()
    target = Path(target).resolve()
    if target == ROOT or ROOT in target.parents and target.relative_to(ROOT).parts[0] in {
            "foundation", "starter", "tools", "standard", "tests", "docs"}:
        raise InitError(f"{target} is inside Portably's own files. Pick a folder outside them, "
                        f"for example a my-site folder next to the Portably folder.")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise InitError(f"{target} already exists and isn't empty. Pick a new folder name.")
    target.mkdir(parents=True, exist_ok=True)

    for source in sorted(STARTER.rglob("*")):
        relative = source.relative_to(STARTER)
        if not source.is_file() or relative in SKIP or relative.parts[0] == "foundation":
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if relative.as_posix() in HANDOFF_FILES:
            destination.write_text(template(relative.as_posix(), target, namespace), encoding="utf-8")
        elif source.suffix.lower() in TEXT_SUFFIXES:
            destination.write_text(replace_namespace(source.read_text(encoding="utf-8"), source_ns, namespace),
                                   encoding="utf-8")
        else:
            shutil.copy2(source, destination)

    (target / "foundation").mkdir(exist_ok=True)
    for source in sorted((ROOT / "foundation").glob("*.css")):
        text = replace_namespace(source.read_text(encoding="utf-8"), source_ns, namespace)
        (target / "foundation" / source.name).write_text(text, encoding="utf-8")

    tokens = json.loads((STARTER / "tokens/tokens.json").read_text(encoding="utf-8"))
    (target / "tokens/tokens.css").write_text(generate(tokens, namespace=namespace), encoding="utf-8")
    (target / "portably.config.json").write_text(json.dumps(new_config(namespace), indent=2) + "\n", encoding="utf-8")
    return target
