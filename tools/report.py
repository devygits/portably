"""What `portably check` found, grouped and explained in plain language."""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field

AREAS = {
    "safety": ("Safety", "nothing broken or inaccessible found"),
    "system": ("Design system", "every value comes from the design system"),
    "structure": ("Structure", "follows the Portably structure"),
    "handoff": ("Handoff", "ready for the next person"),
}

PROBLEM, DECISION, NOTE = "problem", "decision", "note"


@dataclass(frozen=True)
class Group:
    area: str
    level: str
    title: str
    why: str
    todo: str


GROUPS = {
    # Safety: things visitors notice.
    "missing-alt": Group("safety", PROBLEM, "Images without a text description",
                         "Screen-reader users get no description, and nothing shows if the image fails to load.",
                         "Add alt=\"…\" describing the image, or alt=\"\" if it is purely decorative."),
    "broken-link": Group("safety", PROBLEM, "Links that go nowhere",
                         "Visitors click and land on a missing page or section.",
                         "Point each link at a page that exists or an id on the page."),
    "missing-file": Group("safety", PROBLEM, "Missing files",
                          "The page asks for an image, stylesheet or script that isn't in the project, so something won't show.",
                          "Add the file to the project (images go in assets/) or correct the path."),
    "bad-image": Group("safety", PROBLEM, "Images saved with the wrong file type",
                       "The file's content doesn't match its extension; some browsers and servers refuse it.",
                       "Re-export the image in the format its name says, or rename it."),
    "overflow": Group("safety", PROBLEM, "Pages wider than the screen",
                      "Visitors have to scroll sideways, usually on phones.",
                      "Find the element that is too wide at that screen width and let it wrap or shrink."),
    "cut-off": Group("safety", PROBLEM, "Text cut off at the edge of the screen",
                     "Visitors can't read the part that's cut off, and they can't scroll to it.",
                     "Let the text wrap or shrink at that width, for example a smaller size on phones with "
                     "clamp(var(--small-token), 6vw, var(--large-token))."),
    "image-failed": Group("safety", PROBLEM, "Images that fail to load in the browser",
                          "Visitors see an empty space or a broken-image icon.",
                          "Check the file and its path."),
    "script-error": Group("safety", PROBLEM, "JavaScript errors",
                          "Interactions on the page may stop working.",
                          "Open the page with the browser's developer console open and fix the error shown."),
    "low-contrast": Group("safety", PROBLEM, "Text that's hard to read",
                          "Low-contrast text is hard or impossible to read for people with low vision, in sunlight or on a dim screen. "
                          "The accessibility guideline (WCAG AA) asks for 4.5:1 for normal text and 3:1 for large text.",
                          "Make the text darker or the background lighter (or the other way round) until the ratio shown is met. "
                          "On a photo, darken the overlay behind the text or give the text a solid background. "
                          "If you change a colour from the design, record it under \"readability\" in portably.config.json."),
    "contrast-roles": Group("safety", PROBLEM, "Colour roles that are hard to read together",
                            "These colours are meant to be used together, so every page that uses them inherits the problem.",
                            "Use the shade shown (or adjust one of the two colours) in tokens.json. If it changes a colour "
                            "from the design, add a line to \"readability\" in portably.config.json, for example "
                            "\"color.palette.green #00915E → #008855: white button text needs 4.5:1\"."),
    "fake-button": Group("safety", NOTE, "Clickable elements that aren't real buttons",
                         "Keyboard users can't reach or press them unless extra code handles focus, Enter and Space.",
                         "Use a real <button>, or confirm the element handles focus, Enter and Space."),
    "console-error": Group("safety", NOTE, "Errors in the browser console",
                           "Something on the page didn't load or run as expected.",
                           "Open the page with the developer console open and read the message."),

    # Design system: values that drift from the tokens.
    "token-error": Group("system", PROBLEM, "The design system file can't be read",
                         "Without a readable tokens.json, no colour, size or spacing in the project can be checked or updated.",
                         "Correct tokens/tokens.json using the message below; the rest of the design-system check runs once it reads."),
    "tokens": Group("system", PROBLEM, "Incomplete design system",
                    "Every Portably project keeps the full set of colour roles, type sizes, spacing, radii, shadows and layout widths, so the next screen always has a value to reach for.",
                    "Restore what's missing from the Portably starter (starter/tokens/tokens.json), changing the value if the design needs a different one."),
    "token-value": Group("system", PROBLEM, "Values typed by hand that already exist as tokens",
                         "They look right today but won't follow when the token changes.",
                         "Use the token instead. `fix` does this for you."),
    "snap": Group("system", PROBLEM, "Values almost the same as a token",
                  "Near-identical values, like 15px next to a 16px step, are usually slips, and they make the design drift.",
                  "Snap them to the token. `fix` does this for you and records each one in DESIGN-SYSTEM.md."),
    "fallback": Group("system", PROBLEM, "Token values repeated as fallbacks",
                      "`var(--token, 8px)` keeps a second copy of the value, which goes stale when the token changes.",
                      "Keep only the token. `fix` removes the copy."),
    "root-size": Group("system", PROBLEM, "A changed base text size",
                       "Portably's sizes assume the browser's 16px base. Changing it quietly rescales every token, so "
                       "the system no longer means what it says (a 1440px width becomes 1530px).",
                       "Remove it and put the design's real sizes in tokens.json (its body size in font.size.base)."),
    "hidden-token": Group("system", PROBLEM, "Design values kept outside tokens.json",
                          "A second, hidden set of values means tokens.json is no longer the one place the design lives.",
                          "Move the value into tokens.json, then point the variable at the token."),
    "unknown-variable": Group("system", PROBLEM, "References to tokens that don't exist",
                              "The browser ignores them, so the style silently disappears.",
                              "Correct the name, or add the token to tokens.json."),
    "unused-token": Group("system", PROBLEM, "Tokens you added but never use",
                          "An unused token usually means the design moved on, or something was built without it.",
                          "Use it where the design needs it, or delete it from tokens.json."),
    "promote": Group("system", DECISION, "Repeated values that aren't in the system yet",
                     "A value used in several places is a design decision. Recording it once keeps every use in sync.",
                     "If it's intentional, add it to the system with the command shown. If it's drift, change each place to an existing token."),
    "off-system": Group("system", DECISION, "One-off values outside the system",
                        "Portably can't tell whether each one is a deliberate choice or drift.",
                        "Deliberate: add /* exception: reason */ at the end of the line. Drift: use the closest token."),
    "shadow": Group("system", DECISION, "Shadows written by hand",
                    "Hand-written shadows drift apart from each other over time.",
                    "Use shadow.sm, shadow.md or shadow.lg, add a repeated one with the command shown, or mark a deliberate one-off with /* exception: reason */."),
    "breakpoint": Group("system", DECISION, "Screen widths outside the project's breakpoints",
                        "Layouts that change at many slightly different widths are hard to test and maintain.",
                        "Use a project breakpoint, add a repeated one with the command shown, or mark a one-off with /* exception: reason */ on the @media line."),
    "stale-exception": Group("system", NOTE, "Exception comments that are no longer needed",
                             "The value now follows the system, so the comment only adds noise to the exception list.",
                             "Remove the comment. `fix` does this for you."),

    # Structure: the familiar Portably shape.
    "missing-path": Group("structure", PROBLEM, "Missing project files",
                          "Every Portably project has the same files, so anyone can find their way around.",
                          "Restore them. A fresh `python portably.py init` folder has a copy of each one to take from."),
    "foundation-changed": Group("structure", PROBLEM, "Portably foundation files that were changed or are missing",
                                "foundation/ is shared Portably code (reset, button, skip link). Changes there are hard to find and get lost on update.",
                                "`fix` restores the originals. Put project styles in css/ instead."),
    "css-entry": Group("structure", PROBLEM, "Stylesheets out of the Portably order",
                       "The order decides which rules win; a different order makes styles behave differently in each project.",
                       "Keep css/project.css importing base.css, layout.css, components.css and pages.css, in that order."),
    "css-layer": Group("structure", PROBLEM, "Cascade layers in project CSS",
                       "Project styles must stay outside @layer so they reliably override the foundation.",
                       "Remove the @layer wrapper from the file."),
    "page-setup": Group("structure", PROBLEM, "Pages not set up the Portably way",
                        "Without the namespace class on <body> and the three stylesheets in order, tokens and foundation styles don't apply.",
                        "Give <body> the class shown and load foundation/system.css, tokens/tokens.css and css/project.css, in that order."),
    "anatomy": Group("structure", NOTE, "Sections outside the page anatomy",
                     "Every Portably page uses section > wrapper, so spacing and widths stay consistent and the markup looks familiar.",
                     "Give each <section> in <main> the `section` class and put its content in <div class=\"wrapper\">. App screens use app-shell instead."),
    "inline-style": Group("structure", NOTE, "Inline styles",
                          "Styles inside the HTML are easy to miss when the design changes.",
                          "Move them into a stylesheet in css/ unless JavaScript sets them."),
    "framework": Group("structure", PROBLEM, "Portably's own source is out of sync",
                       "The starter, foundation and docs must agree for new projects to start correctly.",
                       "Fix the file named below."),

    # Handoff: what the next person needs.
    "handoff-file": Group("handoff", PROBLEM, "Missing README.md or AGENTS.md",
                          "README.md tells the next person what was built and what's missing; AGENTS.md tells the next "
                          "person or AI agent how to work on the project and check it.",
                          "`fix` creates them from the Portably templates. Fill in the README's pages and known gaps."),
    "context-format": Group("handoff", PROBLEM, "Design notes that can't be read",
                            "DESIGN-SYSTEM.md lists them for the next person; in another shape they are lost.",
                            "In portably.config.json, write \"source\" as a sentence, and \"assumptions\", \"deviations\", "
                            "\"normalizations\" and \"readability\" as lists of sentences."),
    "source": Group("handoff", NOTE, "The design source isn't recorded",
                    "Without it, the next person or AI agent can't compare the implementation with what it was built from.",
                    "Add \"source\" to portably.config.json: where the design came from (a Figma file and its frames, "
                    "screenshots, a website, a brief) and when."),
    "version": Group("handoff", NOTE, "A different or unrecorded Portably version",
                     "Portably's rules only change between major versions; the version tells the next person which ones the project follows.",
                     "Read the CHANGELOG entries marked Breaking since the project's version, check again, then set "
                     "\"portably\" in portably.config.json to the version shown."),
    "browser-skipped": Group("safety", NOTE, "The browser checks didn't run",
                             "Sideways scrolling, images that fail to load, script errors and the contrast of the text "
                             "on screen weren't checked.",
                             "Install Playwright (pip install playwright, then: playwright install chromium) and check again. "
                             "If this machine can't run it, check with --no-browser and say so in the README."),
    "remote": Group("handoff", NOTE, "Files loaded from other websites",
                    "The project breaks if that site changes or goes offline, and the files may need a licence.",
                    "Download them into assets/ where you can; otherwise list them in the README."),
    "host-root": Group("handoff", NOTE, "Paths that start with /",
                       "They only work when the site sits at the root of a domain, so they can't be checked here.",
                       "Use relative paths (assets/logo.svg) unless the host needs /."),
}


@dataclass
class Issue:
    group: str
    where: str
    detail: str
    snippet: str = ""
    fixable: bool = False
    command: str | None = None
    places: list = field(default_factory=list)

    @property
    def spec(self):
        return GROUPS[self.group]


class Style:
    def __init__(self, stream):
        self.on = stream.isatty() and not os.environ.get("NO_COLOR")

    def __call__(self, text, code):
        return f"\033[{code}m{text}\033[0m" if self.on else text

    def bold(self, text):
        return self(text, "1")

    def dim(self, text):
        return self(text, "2")

    def red(self, text):
        return self(text, "31")

    def green(self, text):
        return self(text, "32")

    def yellow(self, text):
        return self(text, "33")


def counts(issues):
    total = defaultdict(lambda: {PROBLEM: 0, DECISION: 0, NOTE: 0, "fixable": 0})
    for issue in issues:
        area = total[issue.spec.area]
        area[issue.spec.level] += 1
        area["fixable"] += issue.fixable and issue.spec.level == PROBLEM
    return total


def plural(n, word, many=None):
    return f"{n} {word if n == 1 else (many or word + 's')}"


def area_summary(numbers):
    parts = []
    if numbers[PROBLEM]:
        text = f"{numbers[PROBLEM]} to fix"
        fixable = numbers["fixable"]
        if fixable:
            text += " (all automatically)" if fixable == numbers[PROBLEM] else f" ({fixable} automatically)"
        parts.append(text)
    if numbers[DECISION]:
        parts.append(f"{numbers[DECISION]} to decide")
    if numbers[NOTE]:
        parts.append(plural(numbers[NOTE], "note"))
    return " · ".join(parts)


def render(issues, project_label, prog, show_all=False, updated=(), skipped=(), stream=None):
    """Return the report text for a list of Issues."""
    style = Style(stream or sys.stdout)
    out = []
    add = out.append
    add(style.bold(f"Portably check · {project_label}"))
    for note in updated:
        add(style.dim(f"Updated {note}"))
    add("")

    totals = counts(issues)
    width = max(len(title) for title, _ in AREAS.values())
    for area, (title, fine) in AREAS.items():
        numbers = totals.get(area)
        if not numbers or not (numbers[PROBLEM] or numbers[DECISION] or numbers[NOTE]):
            add(f"  {style.green('✓')} {title:<{width}}   {style.dim(fine)}")
        elif numbers[PROBLEM]:
            add(f"  {style.red('✗')} {title:<{width}}   {area_summary(numbers)}")
        elif numbers[DECISION]:
            add(f"  {style.yellow('?')} {title:<{width}}   {area_summary(numbers)}")
        else:
            add(f"  {style.dim('•')} {title:<{width}}   {area_summary(numbers)}")
    for note in skipped:
        add(style.dim(f"    {note}"))

    by_group = defaultdict(list)
    for issue in issues:
        by_group[issue.group].append(issue)
    levels = (PROBLEM, DECISION, NOTE)
    for area, (title, _) in AREAS.items():
        groups = [g for g, spec in GROUPS.items() if spec.area == area and by_group.get(g)]
        if not groups:
            continue
        groups.sort(key=lambda g: levels.index(GROUPS[g].level))
        add("")
        add(style.bold(title))
        for group in groups:
            spec, items = GROUPS[group], by_group[group]
            mark = {PROBLEM: style.red("✗"), DECISION: style.yellow("?"), NOTE: style.dim("•")}[spec.level]
            add("")
            add(f"  {mark} {style.bold(spec.title)} ({len(items)})")
            add(f"    {style.dim('Why:')} {spec.why}")
            add(f"    {style.dim('Do: ')} {spec.todo}")
            shown = items if show_all else items[:12]
            for issue in shown:
                add("")
                head = f"    {issue.where}" if issue.where else "   "
                if issue.snippet:
                    head += f"   {style.dim(issue.snippet)}"
                add(head)
                add(f"      {issue.detail}")
                if issue.places and len(issue.places) > 1:
                    add(f"      {style.dim('Used in: ' + ', '.join(issue.places))}")
                if issue.command:
                    add(f"      → {prog} promote {project_label} {issue.command}")
            if len(items) > len(shown):
                add("")
                add(style.dim(f"    …and {len(items) - len(shown)} more. Run `{prog} check {project_label} --all` to see every one."))

    add("")
    total = {level: sum(1 for i in issues if i.spec.level == level) for level in levels}
    fixable = sum(1 for i in issues if i.fixable and i.spec.level == PROBLEM)
    if not total[PROBLEM] and not total[DECISION]:
        verdict = "Everything follows the system. Ready for handoff."
        if total[NOTE]:
            verdict += f" {plural(total[NOTE], 'note')} above {'is' if total[NOTE] == 1 else 'are'} worth a look."
        add(style.green(verdict))
    else:
        parts = []
        if total[PROBLEM]:
            parts.append(plural(total[PROBLEM], "problem") + " to fix")
        if total[DECISION]:
            parts.append(plural(total[DECISION], "decision") + " to make")
        add(style.bold("Not ready for handoff yet: " + " and ".join(parts) + "."))
        if fixable:
            add(f"Next: `{prog} fix {project_label}` fixes {fixable} of them automatically.")
    return "\n".join(out)


JSON_FORMAT = 1
GENERATED_ARTIFACTS = ("tokens/tokens.css", "DESIGN-SYSTEM.md", "DESIGN-SYSTEM.html")
LOCATION = re.compile(r"^(.*):(\d+)$")


def as_data(issues, project_label, prog, updated=(), skipped=(), fixed=None, version=None):
    """The same findings as `render`, as plain data for tools and AI agents (`check --json`)."""
    levels = (PROBLEM, DECISION, NOTE)
    total = {level: sum(1 for i in issues if i.spec.level == level) for level in levels}
    fixable = sum(1 for i in issues if i.fixable and i.spec.level == PROBLEM)
    fix_command = f"{prog} fix {project_label}"
    items = []
    for issue in sorted(issues, key=lambda i: (list(AREAS).index(i.spec.area), levels.index(i.spec.level))):
        spec = issue.spec
        found = LOCATION.match(issue.where or "")
        command = None
        if issue.command:
            command = f"{prog} promote {project_label} {issue.command}"
        elif issue.fixable:
            command = fix_command
        items.append({
            "kind": issue.group,
            "area": spec.area,
            "level": spec.level,
            "title": spec.title,
            "file": found.group(1) if found else (issue.where or None),
            "line": int(found.group(2)) if found else None,
            "detail": issue.detail,
            "snippet": issue.snippet or None,
            "places": list(issue.places),
            "fixable": issue.fixable,
            "decision": spec.level == DECISION,
            "command": command,
            "why": spec.why,
            "action": spec.todo,
        })
    data = {
        "format": JSON_FORMAT,
        "portably": version,
        "project": project_label,
        "ready": not total[PROBLEM] and not total[DECISION],
        "readyStrict": not issues,
        "counts": {"problems": total[PROBLEM], "decisions": total[DECISION], "notes": total[NOTE], "fixable": fixable},
        "next": fix_command if fixable else None,
        "updated": list(updated),
        "skipped": list(skipped),
        "generatedArtifacts": list(GENERATED_ARTIFACTS),
        "issues": items,
    }
    if fixed is not None:
        data["fixed"] = list(fixed)
    return data