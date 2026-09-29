"""Find tokens a project added but never uses."""
from __future__ import annotations

import fnmatch
import json
import re
from collections import defaultdict, deque
from pathlib import Path

from build_tokens import collect, emitted_variables, token_dependencies
from naming import namespace_for

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "standard" / "token-policy.json"
BASELINE = ROOT / "starter" / "tokens" / "tokens.json"


def resolve_token_directory(path):
    path = Path(path).resolve()
    if path.is_file():
        path = path.parent
    if (path / "tokens.json").is_file():
        return path
    if (path / "tokens" / "tokens.json").is_file():
        return path / "tokens"
    raise ValueError(f"Could not find tokens.json from {path}")


def project_root_for(directory):
    return resolve_token_directory(directory).parent


def variable_pattern(namespace):
    return re.compile(rf"var\(\s*(--{re.escape(namespace)}-[\w-]+)")


def iter_source_files(paths):
    seen = set()
    for item in paths:
        path = Path(item).resolve()
        if path.is_file():
            candidates = [path]
        elif path.is_dir():
            candidates = path.rglob("*")
        else:
            continue
        for child in candidates:
            if (
                child.is_file()
                and child.name not in {"tokens.css", "DESIGN-SYSTEM.html"}  # generated from the tokens themselves
                and child.suffix.lower() in {".css", ".html"}
                and child not in seen
            ):
                seen.add(child)
                yield child


def scan_variable_usage(paths, namespace):
    result = defaultdict(list)
    pattern = variable_pattern(namespace)
    for path in iter_source_files(paths):
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            for name in pattern.findall(line):
                result[name].append((path, line_no))
    return result


def dependency_closure(roots, graph):
    seen = set()
    queue = deque(roots)
    while queue:
        token = queue.popleft()
        if token in seen:
            continue
        seen.add(token)
        queue.extend(graph.get(token, ()))
    return seen


def default_scan_paths(directory):
    return [project_root_for(directory)]


def load(directory, namespace=None):
    directory = resolve_token_directory(directory)
    source = json.loads((directory / "tokens.json").read_text(encoding="utf-8"))
    namespace = namespace or namespace_for(directory)
    return source, collect(source), token_dependencies(source), emitted_variables(source, namespace=namespace)


def unused_tokens(directory, paths=None):
    directory = resolve_token_directory(directory)
    paths = paths or default_scan_paths(directory)
    namespace = namespace_for(directory)
    source, tokens, graph, variables = load(directory, namespace=namespace)
    usage = scan_variable_usage(paths, namespace=namespace)
    directly_used = {variables[name] for name in usage if name in variables}
    reachable = dependency_closure(directly_used, graph)
    return sorted(set(tokens) - reachable), directly_used, reachable, tokens


def load_policy(path=POLICY):
    data = json.loads(path.read_text(encoding="utf-8"))
    patterns = data.get("allowedUnused", [])
    if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
        raise ValueError("token-policy.json allowedUnused must be an array of glob strings")

    if data.get("allowUnusedBaselineTokens", False):
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        patterns = sorted(set(patterns) | set(collect(baseline)))

    return patterns


def classify_unused(unused, patterns):
    allowed, unexpected = [], []
    for token in unused:
        if any(fnmatch.fnmatchcase(token, pattern) for pattern in patterns):
            allowed.append(token)
        else:
            unexpected.append(token)
    return allowed, unexpected
