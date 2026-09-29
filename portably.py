#!/usr/bin/env python3
"""Portably gives an AI agent a predictable system to build a design into, and leaves behind a repository that anyone can continue.

    python portably.py init my-project        create a project from the Portably starter
    python portably.py check my-project       check everything and explain what needs attention
    python portably.py check my-project --json
                                              the same findings as data, for AI agents and tools
    python portably.py fix my-project         fix the safe things automatically, then check
    python portably.py promote my-project spacing 80px
                                              add a repeated value to the design system
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

from check import ProjectError, run_check  # noqa: E402
from fix import PromoteError, fix_project, promote  # noqa: E402
from naming import portably_version  # noqa: E402
from project import InitError, create_project  # noqa: E402
from report import Issue, as_data, render  # noqa: E402


def label(path):
    """A path as short as possible: relative when it's nearby, absolute otherwise; quoted if it has spaces."""
    path = Path(path).resolve()
    try:
        shown = os.path.relpath(path)
    except ValueError:
        shown = str(path)
    if shown.startswith(os.path.join("..", "..", "")):
        shown = str(path)
    return shown if " " not in shown else f'"{shown}"'


def program():
    """How the user ran this script, so every suggested command can be copied as is."""
    return f"python {label(sys.argv[0])}"


def report(args, prog, fixed=None):
    result = run_check(args.project, framework=args.framework, browser=not args.no_browser)
    if args.no_browser:
        result.skipped = []
        result.issues.append(Issue("browser-skipped", "", "Browser checks were turned off with --no-browser."))
    if args.json:
        data = as_data(result.issues, label(args.project), prog, updated=result.updated, skipped=result.skipped,
                       fixed=fixed, version=portably_version())
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        if fixed is not None:
            if fixed:
                print(f"Made {len(fixed)} change{'s' if len(fixed) != 1 else ''}:")
                for line in fixed:
                    print(f"  {line}")
            else:
                print("Nothing to fix automatically.")
            print()
        print(render(result.issues, label(args.project), prog, show_all=args.all,
                     updated=result.updated, skipped=result.skipped))
    blocking = [i for i in result.issues if i.spec.level != "note" or args.strict]
    return 1 if blocking else 0


def main(argv=None):
    prog = program()
    parser = argparse.ArgumentParser(prog=prog, description="Portably gives an AI agent a predictable system to build a design into, and leaves behind a repository that anyone can continue.",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="Run a command with --help for its options.")
    parser.add_argument("--version", action="version", version=f"Portably {portably_version()}")
    commands = parser.add_subparsers(dest="command", metavar="command")

    init = commands.add_parser("init", help="create a new project from the Portably starter")
    init.add_argument("project", help="folder to create, for example my-site")
    init.add_argument("--namespace", help="prefix for Portably classes and variables (default: pbly)")

    for name, text in (("check", "check everything and explain what needs attention"),
                       ("fix", "fix the safe things automatically, then check")):
        command = commands.add_parser(name, help=text)
        command.add_argument("project", nargs="?", default=".", help="the project folder (default: this folder)")
        command.add_argument("--all", action="store_true", help="list every finding instead of the first 12 per group")
        command.add_argument("--strict", action="store_true", help="also fail on notes (use before a final handoff)")
        command.add_argument("--no-browser", action="store_true", help="skip the browser checks")
        command.add_argument("--json", action="store_true", help="print the findings as JSON (for AI agents and tools)")
        command.add_argument("--framework", action="store_true", help=argparse.SUPPRESS)

    grow = commands.add_parser("promote", help="add a repeated value to the design system",
                               description="Add a value to the design system and use the new token everywhere it appears.")
    grow.add_argument("project", help="the project folder")
    grow.add_argument("kind", help="spacing, radius, font-size, line-height, letter-spacing, shadow, colour or breakpoint")
    grow.add_argument("value", help="the value, for example 80px or #E11D48")
    grow.add_argument("--as", dest="name", help="the new token's name, for example radius.xl")

    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    try:
        if args.command == "init":
            target = create_project(args.project, args.namespace)
            shown = label(target)
            print(f"Ready. Start building in {'this folder' if shown == '.' else shown}.\n")
            print("Next:")
            print(f"  1. Record where the design comes from: \"source\" in {shown}/portably.config.json.")
            print(f"  2. Put the design's colours, fonts and sizes in {shown}/tokens/tokens.json.")
            print("     Anything the design doesn't define keeps a sensible default.")
            print(f"  3. Replace the placeholder page in {shown}/index.html and style it in {shown}/css/.")
            print(f"  4. Check your work any time:  {prog} check {shown}")
            print(f"\nWorking with an AI agent? Point it at {shown}/AGENTS.md.")
            return 0
        if args.command == "check":
            return report(args, prog)
        if args.command == "fix":
            return report(args, prog, fixed=fix_project(args.project))
        if args.command == "promote":
            for line in promote(args.project, args.kind, args.value, args.name):
                print(line)
            print(f"\nRun `{prog} check {label(args.project)}` to see what's left.")
            return 0
        parser.print_help()
        return 0
    except (ProjectError, InitError, PromoteError) as exc:
        return failure(args, str(exc))
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        return failure(args, f"Portably couldn't finish: {exc}")


def failure(args, message):
    """Report a project that can't be checked at all: as JSON when asked, otherwise on stderr."""
    if getattr(args, "json", False):
        print(json.dumps({"format": 1, "portably": portably_version(), "error": message}, indent=2, ensure_ascii=False))
    else:
        print(message, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())