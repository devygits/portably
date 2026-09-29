"""Regression tests for Portably."""
from __future__ import annotations

import copy
import html
import json
import re
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_tokens import classify_unused, default_scan_paths, dependency_closure, load_policy, unused_tokens
from build_tokens import collect, generate, token_dependencies
from check import ProjectError, find_project, run_check
from check_handoff import inspect_project
from check_browser import browser_issues, project_themes
from check_system import inspect_system
from design_doc import gather, render as render_design_doc
from design_page import render_page
from fix import PromoteError, fix_project, promote
from framework import framework_problems
from naming import HOME_URL, default_namespace, namespace_for, portably_version, validate_namespace
from project import InitError, create_project
from report import GROUPS, as_data, render


def groups(result):
    return [issue.group for issue in result.issues]


def check(project, **kwargs):
    kwargs.setdefault("browser", False)
    return run_check(project, **kwargs)


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.classes = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if "class" in attr:
            self.classes.extend(attr["class"].split())
        if tag == "link":
            self.links.append(attr.get("href", ""))


class TokenContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT / "starter/tokens/tokens.json").read_text())

    def test_generated_output_is_reproducible(self):
        self.assertEqual(generate(self.source), (ROOT / "starter/tokens/tokens.css").read_text())

    def test_css_is_opt_in_prefixed_and_token_layered(self):
        css = generate(self.source)
        self.assertTrue(css.startswith("/* Generated"))
        self.assertIn("@layer pbly-tokens {", css)
        self.assertIn("\n  .pbly {", css)
        self.assertNotIn("\n:root {", css)
        self.assertIn("--pbly-color-action-primary:", css)

    def test_public_foundation_rules_are_unlayered(self):
        self.assertEqual((ROOT / "foundation/layers.css").read_text().strip(), "@layer pbly-reset, pbly-tokens;")
        self.assertTrue((ROOT / "foundation/reset.css").read_text().lstrip().startswith("@layer pbly-reset {"))
        for name in ("button.css", "accessibility.css"):
            self.assertNotIn("@layer", (ROOT / "foundation" / name).read_text(), name)

    def test_foundation_is_only_shared_essentials(self):
        self.assertEqual(sorted(p.name for p in (ROOT / "foundation").glob("*.css")),
                         ["accessibility.css", "button.css", "layers.css", "reset.css", "system.css"])
        css = "\n".join(p.read_text() for p in (ROOT / "foundation").glob("*.css"))
        for removed in ("pbly-container", "pbly-stack", "pbly-grid", "pbly-mt-", "pbly-text-muted", "pbly-text-heading"):
            self.assertNotIn(removed, css)

    def test_project_styles_are_unlayered_and_scalable(self):
        for path in (ROOT / "starter/css").rglob("*.css"):
            self.assertNotIn("@layer", path.read_text(), path.name)
        self.assertTrue((ROOT / "starter/css/components/site-chrome.css").is_file())
        self.assertTrue((ROOT / "starter/css/components/cards.css").is_file())
        self.assertTrue((ROOT / "starter/css/pages/home.css").is_file())

    def test_baseline_tokens_may_be_unused(self):
        allowed, unexpected = classify_unused(["color.surface.raised", "space.1", "space.1-5", "shadow.sm"], load_policy())
        self.assertEqual(unexpected, [])
        self.assertEqual(len(allowed), 4)

    def test_added_unused_project_token_is_reported(self):
        def experimental(source):
            source["color"]["experimental"] = {"$type": "color", "$value": "{color.palette.accent}"}
        with tempfile.TemporaryDirectory() as tmp:
            result = check(client_project(tmp, tokens=experimental))
        self.assertEqual(groups(result), ["unused-token"])
        self.assertIn("color.experimental", result.issues[0].detail)

    def test_scale_5_is_20px_nominal(self):
        self.assertIn("--pbly-space-5: 1.25rem;", generate(self.source))

    def test_unknown_alias_is_rejected(self):
        changed = copy.deepcopy(self.source)
        changed["color"]["action"]["primary"]["$value"] = "{color.palette.missing}"
        with self.assertRaisesRegex(ValueError, "alias"):
            generate(changed)

    def test_circular_alias_is_rejected(self):
        changed = copy.deepcopy(self.source)
        changed["color"]["palette"]["accent"]["$value"] = "{color.action.primary}"
        with self.assertRaisesRegex(ValueError, "Circular"):
            generate(changed)

    def test_type_mismatch_is_rejected(self):
        changed = copy.deepcopy(self.source)
        changed["color"]["action"]["primary"]["$value"] = "{space.5}"
        with self.assertRaisesRegex(ValueError, "mismatched"):
            generate(changed)

    def test_collision_is_rejected(self):
        changed = copy.deepcopy(self.source)
        changed["hello"] = {"foo-bar": {"$type": "number", "$value": 2}}
        changed["hello-foo"] = {"bar": {"$type": "number", "$value": 1}}
        with self.assertRaisesRegex(ValueError, "collision"):
            generate(changed)

    def test_invalid_color_is_rejected(self):
        changed = copy.deepcopy(self.source)
        changed["color"]["palette"]["accent"]["$value"] = "#12345G"
        with self.assertRaisesRegex(ValueError, "isn't a colour Portably can read"):
            generate(changed)
        changed["color"]["palette"]["accent"]["$value"] = {"colorSpace": "srgb", "components": [0, 0, 0], "hex": "#123456"}
        with self.assertRaisesRegex(ValueError, "Hex"):
            generate(changed)

    def test_colours_can_be_written_the_way_designers_copy_them(self):
        changed = copy.deepcopy(self.source)
        formats = {"a": "#2F6B4F", "b": "rgb(47 107 79)", "c": "hsl(152 39% 30.2%)", "d": "oklch(0.4794 0.078 161.08)",
                   "e": "rgba(47, 107, 79, 0.5)"}
        for name, value in formats.items():
            changed["color"]["palette"][name] = {"$type": "color", "$value": value}
        css = generate(changed)
        self.assertIn("--pbly-color-palette-d: oklch(0.4794 0.078 161.08);", css)
        from colors import parse_color, to_hex
        for name in "abcd":
            self.assertEqual(to_hex(parse_color(formats[name])[0]), "#2F6B4F", name)
        self.assertEqual(parse_color(formats["e"])[1], 0.5)

    def test_check_regenerates_stale_token_css(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp)
            (project / "tokens/tokens.css").write_text("stale")
            result = check(project)
            self.assertEqual(result.issues, [])
            self.assertIn("tokens/tokens.css from tokens.json", result.updated)
            self.assertEqual((project / "tokens/tokens.css").read_text(), (ROOT / "starter/tokens/tokens.css").read_text())

    def test_starter_passes_every_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "starter"
            shutil.copytree(ROOT / "starter", project)
            self.assertEqual(check(project).issues, [])

    def test_framework_contract(self):
        self.assertEqual(list(framework_problems()), [])

    def test_starter_is_self_contained(self):
        p = ROOT / "starter/index.html"
        parser = Markup()
        parser.feed(p.read_text())
        self.assertIn("pbly", parser.classes)
        self.assertIn("pbly-btn--primary", parser.classes)
        self.assertEqual(parser.links[:3], ["foundation/system.css", "tokens/tokens.css", "css/project.css"])
        for css in parser.links[:3]:
            self.assertTrue((p.parent / css).resolve().is_file(), css)
        self.assertTrue((ROOT / "starter/portably.config.json").is_file())

    def test_starter_does_not_imply_secondary_pages(self):
        page_dir = ROOT / "starter/pages"
        pages = list(page_dir.rglob("*.html")) if page_dir.exists() else []
        self.assertEqual(pages, [])
        html = (ROOT / "starter/index.html").read_text()
        self.assertNotIn("about.html", html.lower())
        self.assertIn("Replace this page with the supplied design.", html)

    def test_starter_foundation_matches_canonical(self):
        for source in (ROOT / "foundation").glob("*.css"):
            self.assertEqual((ROOT / "starter/foundation" / source.name).read_text(), source.read_text(), source.name)

    def test_project_resolution_is_client_local(self):
        self.assertEqual(find_project(ROOT / "starter/tokens"), ROOT / "starter")
        self.assertEqual(find_project(ROOT / "starter"), ROOT / "starter")
        self.assertEqual(find_project(ROOT / "docs/tokens"), ROOT / "docs")
        self.assertEqual(find_project(ROOT / "docs"), ROOT / "docs")
        with self.assertRaisesRegex(ProjectError, "doesn't look like a Portably project"):
            find_project(ROOT / "standard")

    def test_project_aware_token_scan_uses_starter_not_docs(self):
        self.assertEqual(default_scan_paths(ROOT / "starter/tokens"), [ROOT / "starter"])
        unused, _, _, _ = unused_tokens(ROOT / "starter/tokens")
        self.assertIsInstance(unused, list)

    def test_handoff_check_passes_starter(self):
        self.assertEqual(inspect_project(ROOT / "starter"), [])

    def test_handoff_check_asks_for_readme_and_agents_guide(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp)
            (project / "README.md").unlink()
            (project / "AGENTS.md").unlink()
            found = inspect_project(project)
        self.assertEqual([(group, where) for group, where, _ in found],
                         [("handoff-file", "AGENTS.md"), ("handoff-file", "README.md")])

    def test_handoff_check_notes_sections_that_skip_the_anatomy(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, html='<section class="pricing"><p>No wrapper</p></section>')
            details = [detail for group, _, detail in inspect_project(project) if group == "anatomy"]
        self.assertTrue(any("no `section` class" in item for item in details), details)
        self.assertTrue(any("no `wrapper` inside" in item for item in details), details)

    def test_handoff_check_accepts_app_shell_screens(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, html='<section class="stats"><div class="app-shell"></div></section>')
            self.assertEqual(inspect_project(project), [])

    def test_handoff_check_catches_broken_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp)
            index = project / "index.html"
            index.write_text(index.read_text().replace('href="#example"', 'href="#missing"', 1))
            found = inspect_project(project)
        self.assertEqual([group for group, *_ in found], ["broken-link"])
        self.assertIn("#missing", found[0][2])
        self.assertRegex(found[0][1], r"index\.html:\d+")

    def test_changed_base_text_size_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check(client_project(tmp, css="html { font-size: 106.25%; }"))
        self.assertEqual(groups(result), ["root-size"])

    def test_promote_letter_spacing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=".a { letter-spacing: 0.14em; }\n.b { letter-spacing: 0.14em; }")
            promote(project, "letter-spacing", "0.14em", "font.tracking.caps")
            css = (project / "css/pages/home.css").read_text()
            result = check(project)
        self.assertEqual(css.count("var(--pbly-font-tracking-caps)"), 2)
        self.assertEqual(result.issues, [])

    def test_links_to_other_sites_are_not_dependencies(self):
        html = ('<section class="section"><div class="wrapper"><a href="https://example.com/">Example</a>'
                '<link rel="stylesheet" href="https://fonts.example.com/a.css"></div></section>')
        with tempfile.TemporaryDirectory() as tmp:
            found = inspect_project(client_project(tmp, html=html))
        self.assertEqual([(group, detail) for group, _, detail in found],
                         [("remote", "Loads https://fonts.example.com/a.css")])

    def test_safety_problems_are_found_with_line_numbers(self):
        html = '<section class="section"><div class="wrapper"><img src="assets/none.png"><a href="#">Buy</a></div></section>'
        with tempfile.TemporaryDirectory() as tmp:
            result = check(client_project(tmp, html=html))
        self.assertEqual(sorted(groups(result)), ["broken-link", "missing-alt", "missing-file"])
        for issue in result.issues:
            self.assertEqual(issue.spec.area, "safety")
            self.assertRegex(issue.where, r"index\.html:\d+")

    def test_starter_uses_page_anatomy_and_readable_markup(self):
        html = (ROOT / "starter/index.html").read_text()
        self.assertIn('<section class="section hero"', html)
        self.assertIn('<div class="wrapper hero__inner">', html)
        self.assertIn('<header class="section-header">', html)
        self.assertIn('class="example-card"', html)
        self.assertIn("pbly-btn--primary", html)
        layout = (ROOT / "starter/css/layout.css").read_text()
        for role in (".section ", ".wrapper ", ".section-header ", ".app-shell ", ".app-shell__main ", ".panel "):
            self.assertIn(role, layout)

    def test_agent_guides_keep_the_field_test_lessons(self):
        root = (ROOT / "AGENTS.md").read_text()
        for phrase in ("Never create extra pages or states to demonstrate Portably", "never inside the Portably folder",
                       "Don't redesign", "normalize small inconsistencies", "exception: hero spacing from the design",
                       "check site --json", "check site --strict", '"source"', '"assumptions"', '"deviations"'):
            self.assertIn(phrase, root)
        project = (ROOT / "starter/AGENTS.md").read_text()
        for phrase in ("components/<concept>.css", "data-js", "section-header", "promote", '"source"', '"assumptions"',
                       "check . --json", "check . --strict", "never edited by hand", "Moving to another stack"):
            self.assertIn(phrase, project)

    def test_docs_are_self_contained(self):
        pages = [ROOT / "docs/index.html", *sorted((ROOT / "docs/pages").glob("*.html"))]
        for p in pages:
            parser = Markup()
            parser.feed(p.read_text())
            prefix = "" if p.parent.name == "docs" else "../"
            self.assertIn("pbly", parser.classes, p.name)
            self.assertEqual(parser.links[:3], [prefix + "foundation/system.css", prefix + "tokens/tokens.css",
                                                prefix + "css/project.css"], p.name)
            for css in parser.links:
                self.assertTrue((p.parent / css).resolve().is_file(), css)
        self.assertTrue((ROOT / "docs/tokens/tokens.json").is_file())
        self.assertTrue((ROOT / "docs/portably.config.json").is_file())

    def test_docs_pages_share_one_navigation(self):
        def navigation(page):
            text = page.read_text()
            nav = text[text.index('<nav class="docs-nav'):text.index("</nav>", text.index('<nav class="docs-nav'))]
            return re.sub(r' aria-current="page"|href="(\.\./|pages/)?', "", nav)
        pages = [page for page in [ROOT / "docs/index.html", *sorted((ROOT / "docs/pages").glob("*.html"))]
                 if page.name != "sample.html"]  # the design-system sample fills the page below the header
        first = navigation(pages[0])
        for page in pages[1:]:
            self.assertEqual(navigation(page), first, page.name)
        for page in pages:
            self.assertEqual(page.read_text().count('aria-current="page"'), 1, page.name)

    def test_docs_pages_carry_a_sharing_preview(self):
        image = "https://devygits.github.io/portably/assets/social-preview.png"
        self.assertTrue((ROOT / "docs/assets/social-preview.png").is_file())
        pages = [ROOT / "docs/index.html", *sorted((ROOT / "docs/pages").glob("*.html"))]
        for page in pages:
            text = page.read_text()
            for tag in (f'<meta property="og:image" content="{image}">', f'<meta name="twitter:image" content="{image}">',
                        '<meta name="twitter:card" content="summary_large_image">'):
                self.assertIn(tag, text, page.name)
            title = re.search(r"<title>(.*?)</title>", text).group(1)
            self.assertIn(f'<meta property="og:title" content="{title}">', text, page.name)
            rel = "" if page.name == "index.html" else f"pages/{page.name}"
            self.assertIn(f'<meta property="og:url" content="https://devygits.github.io/portably/{rel}">', text, page.name)

    def test_docs_hide_the_scroll_bars_of_their_scrolling_parts(self):
        base = (ROOT / "docs/css/base.css").read_text()
        rule = re.search(r"\.pbly :where\(([^)]*)\) \{([^}]*)\}", base[base.index("The parts that scroll"):]).groups()
        for scrolling in (".docs-layout__sticky", ".code-block__pre", ".table-scroll"):
            self.assertIn(scrolling, rule[0])
        self.assertIn("scrollbar-width: none", rule[1])
        self.assertNotIn("scrollbar", (ROOT / "docs/css/layout.css").read_text())

    def test_docs_open_other_sites_in_a_new_tab(self):
        pages = [ROOT / "docs/index.html", *sorted((ROOT / "docs/pages").glob("*.html"))]
        for page in pages:
            for tag, body in re.findall(r'(<a [^>]*href="https?://[^>]*>)(.*?)</a>', page.read_text(), flags=re.S):
                self.assertIn('target="_blank" rel="noopener"', tag, page.name)
                self.assertIn("(opens in a new tab)", body, page.name)
            for tag in re.findall(r'<a [^>]*href="(?!https?://)[^>]*>', page.read_text()):
                self.assertNotIn("_blank", tag, page.name)

    @unittest.skipUnless(__import__("importlib").util.find_spec("playwright"), "Playwright isn't installed")
    def test_docs_code_is_coloured_without_changing_it(self):
        from html import unescape
        from playwright.sync_api import sync_playwright
        from check_browser import chromium_path
        pages = [ROOT / "docs/index.html", *sorted((ROOT / "docs/pages").glob("*.html"))]
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chromium_path(), args=["--no-sandbox"])
            page = browser.new_page()
            seen = set()
            for path in pages:
                source = [unescape(code) for code in re.findall(r'<pre class="code-block__pre"><code>(.*?)</code>', path.read_text(), flags=re.S)]
                page.goto(path.as_uri())
                self.assertEqual(page.eval_on_selector_all(".code-block__pre code", "codes => codes.map(c => c.textContent)"), source, path.name)
                seen.update(page.eval_on_selector_all("[class^='code-block__']", "spans => spans.map(s => s.className)"))
            browser.close()
        for kind in ("keyword", "name", "string", "value", "comment", "tree", "note"):
            self.assertIn(f"code-block__{kind}", seen)

    def test_docs_list_every_finding(self):
        findings = (ROOT / "docs/pages/findings.html").read_text()
        for kind, spec in GROUPS.items():
            self.assertIn(f'id="{kind}"', findings, kind)
            self.assertIn(html.escape(spec.title), findings, kind)

    def test_token_dependency_graph(self):
        graph = token_dependencies(self.source)
        used = dependency_closure({"color.action.primary"}, graph)
        self.assertIn("color.palette.accent", used)
        self.assertEqual(len(collect(self.source)), 84)

    def test_policy_contains_no_wildcard_exemptions(self):
        policy = json.loads((ROOT / "standard/token-policy.json").read_text())
        self.assertTrue(policy["allowUnusedBaselineTokens"])
        self.assertFalse(any("*" in item or "?" in item for item in policy["allowedUnused"]))

    def test_core_does_not_contain_project_or_research_names(self):
        text = "\n".join(p.read_text() for p in (ROOT / "foundation").rglob("*.css"))
        self.assertNotRegex(text, r"(?i)\b(?:sta|restaurant|figma|sugarcube)\b")

    def test_default_namespace_is_portably_brand_prefix(self):
        self.assertEqual(default_namespace(), "pbly")
        self.assertEqual(validate_namespace("acme-ui"), "acme-ui")
        for bad in ("", "PF", "99ui", "acme_ui", "acme ui", "-acme"):
            with self.assertRaises(ValueError, msg=bad):
                validate_namespace(bad)

    def test_generated_project_config_resolves_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = create_project(Path(tmp) / "client", "client-ui")
            self.assertEqual(namespace_for(out / "tokens"), "client-ui")

    def test_custom_namespace_build_is_self_contained_and_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = create_project(Path(tmp) / "acme", "acme")
            self.assertEqual(groups(check(out)), ["source"])
            css = "\n".join(p.read_text() for p in out.rglob("*.css"))
            html = (out / "index.html").read_text()
            guides = (out / "AGENTS.md").read_text() + (out / "README.md").read_text()
            self.assertIn("var(--acme-…)", guides)
            self.assertNotIn("pbly", guides)
            self.assertIn(".acme .acme-btn--primary", css)
            self.assertIn("--acme-color-action-primary", css)
            self.assertIn("@layer acme-reset, acme-tokens;", css)
            self.assertIn('class="acme"', html)
            self.assertNotIn("pbly-", css + html)
            self.assertNotIn("--pbly-", css + html)

    def test_foundation_has_no_decorative_comments(self):
        for p in (ROOT / "foundation").glob("*.css"):
            self.assertNotRegex(p.read_text(), r"/\*\s*[=-]{4,}")


def client_project(tmp, css="", tokens=None, config=None, html=None):
    project = Path(tmp) / "client"
    shutil.copytree(ROOT / "starter", project)
    if css:
        page_css = project / "css/pages/home.css"
        page_css.write_text(page_css.read_text() + "\n" + css + "\n")
    if tokens:
        token_file = project / "tokens/tokens.json"
        source = json.loads(token_file.read_text())
        tokens(source)
        token_file.write_text(json.dumps(source, indent=2))
        (project / "tokens/tokens.css").write_text(generate(source))
    if config:
        path = project / "portably.config.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), **config}))
    if html:
        index = project / "index.html"
        index.write_text(index.read_text().replace("</main>", html + "\n  </main>"))
    return project


def rem(px):
    return {"$type": "dimension", "$value": {"value": px / 16, "unit": "rem"}}


class SystemContract(unittest.TestCase):
    def findings(self, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            return inspect_system(client_project(tmp, **kwargs))[:2]

    def kinds(self, **kwargs):
        return [f.kind for f in self.findings(**kwargs)[0]]

    def test_starter_follows_its_system(self):
        findings, exceptions, stale = inspect_system(ROOT / "starter")
        self.assertEqual(findings + exceptions + stale, [])

    def test_token_value_written_by_hand_is_flagged(self):
        findings, _ = self.findings(css=".x { padding: 16px; }")
        self.assertEqual([f.kind for f in findings], ["token-value"])
        self.assertIn("space.4", findings[0].message)
        self.assertTrue(findings[0].fixable)

    def test_small_inconsistency_snaps_to_nearest_step(self):
        findings, _ = self.findings(css=".x { gap: 15px; font-size: 15px; }")
        self.assertEqual([f.kind for f in findings], ["snap", "snap"])
        self.assertIn("space.4", findings[0].message)
        self.assertIn("font.size.base", findings[1].message)

    def test_value_outside_system_needs_exception_or_step(self):
        findings, _ = self.findings(css=".x { padding-block: 80px; }")
        self.assertEqual([f.kind for f in findings], ["off-system"])
        self.assertEqual(findings[0].command, "spacing 80px")

    def test_exception_comment_accepts_one_off_value(self):
        findings, exceptions = self.findings(css=".x { padding-block: 80px; /* exception: hero spacing from the design */ }")
        self.assertEqual(findings, [])
        self.assertEqual(exceptions[0].reason, "hero spacing from the design")

    def test_exception_at_the_end_of_a_line_excuses_the_value_that_needs_it(self):
        css = ".x { stroke: #5b8f83; opacity: 0.55; } /* exception: decorative line */"
        findings, exceptions = self.findings(css=css)
        self.assertEqual(findings, [])
        self.assertEqual([(e.snippet, e.reason) for e in exceptions], [("stroke: #5b8f83", "decorative line")])

    def test_a_hairline_offset_gets_no_promote_command(self):
        findings, _ = self.findings(css=".x { margin-left: -1px; }")
        self.assertEqual([(f.kind, f.command) for f in findings], [("off-system", None)])

    def test_fluid_sizes_between_two_tokens_need_no_exception(self):
        css = ".x { font-size: clamp(var(--pbly-font-size-2xl), 6vw, var(--pbly-font-size-5xl)); }"
        self.assertEqual(self.findings(css=css), ([], []))

    def test_letter_spacing_tokens_may_use_em(self):
        def tracked(source):
            source["font"]["tracking"]["label"]["$value"] = {"value": 0.08, "unit": "em"}
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, tokens=tracked)
            result = check(project)
            css = (project / "tokens/tokens.css").read_text()
        self.assertEqual(result.issues, [])
        self.assertIn("--pbly-font-tracking-label: 0.08em;", css)

    def test_em_is_only_for_letter_spacing(self):
        def em_space(source):
            source["space"]["4"]["$value"] = {"value": 1, "unit": "em"}
        with tempfile.TemporaryDirectory() as tmp:
            result = check(client_project(tmp, tokens=em_space))
        self.assertIn("`em` works only for letter spacing", " ".join(i.detail for i in result.issues if i.group == "token-error"))

    def test_letter_spacing_comes_from_tracking_tokens(self):
        findings, _ = self.findings(css=".x { letter-spacing: -0.041em; }\n.y { letter-spacing: 0.14em; }")
        self.assertEqual([f.kind for f in findings], ["snap", "off-system"])
        self.assertEqual(findings[1].command, "letter-spacing 0.14em --as font.tracking.NAME")

    def test_repeated_exception_must_become_a_token(self):
        css = ".x { padding-block: 80px; /* exception: hero */ }\n.y { margin-top: 80px; /* exception: footer */ }"
        findings, _ = self.findings(css=css)
        self.assertEqual([f.kind for f in findings], ["promote"])
        self.assertEqual(len(findings[0].places), 2)

    def test_repeated_value_without_exceptions_is_one_promotion(self):
        css = ".a { border-radius: 20px; }\n.b { border-radius: 20px; }\n.c { border-radius: 20px; }"
        findings, _ = self.findings(css=css)
        self.assertEqual([f.kind for f in findings], ["promote"])
        self.assertIn("3 places", findings[0].message)
        self.assertEqual(findings[0].command, "radius 20px --as radius.NAME")

    def test_added_spacing_step_is_part_of_the_system(self):
        def add_step(source):
            source["space"]["20"] = rem(80)
        self.assertEqual(self.kinds(css=".x { padding-block: var(--pbly-space-20); }", tokens=add_step), [])

    def test_spacing_step_names_follow_the_4px_rule(self):
        def misnamed(source):
            source["space"]["20"] = rem(72)
        findings, _ = self.findings(css=".x { padding-block: var(--pbly-space-20); }", tokens=misnamed)
        self.assertEqual([f.kind for f in findings], ["tokens"])
        self.assertIn("space.18", findings[0].message)

    def test_baseline_steps_cannot_change(self):
        def changed(source):
            source["space"]["4"] = rem(18)
        self.assertEqual(self.kinds(tokens=changed), ["tokens"])

    def test_system_must_be_complete(self):
        def no_hover(source):
            del source["color"]["action"]["hover"]
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp)
            token_file = project / "tokens/tokens.json"
            source = json.loads(token_file.read_text())
            no_hover(source)
            token_file.write_text(json.dumps(source))
            findings, *_ = inspect_system(project)
        self.assertIn("color.action.hover", findings[0].message)

    def test_colours_snap_and_translucent_colours_use_tokens(self):
        findings, _ = self.findings(css=".x { color: #2564EA; background: rgba(255, 255, 255, 0.5); border-color: #ff00aa; }")
        self.assertEqual([f.kind for f in findings], ["snap", "token-value", "off-system"])
        self.assertIn("color.surface.raised` at 50% opacity", findings[1].message)
        self.assertEqual(findings[2].command, 'colour "#FF00AA" --as color.palette.NAME')

    def test_ambiguous_colour_roles_are_left_to_a_person(self):
        def two_text_greys(source):
            source["color"]["text"]["soft"]["$value"] = "{color.palette.graphite}"
        findings, _ = self.findings(css=".x { color: #475569; }", tokens=two_text_greys)
        self.assertEqual([f.kind for f in findings], ["token-value"])
        self.assertFalse(findings[0].fixable)
        self.assertIn("pick the role", findings[0].message)

    def test_fix_never_gives_a_colour_the_wrong_kind_of_role(self):
        # #CBD5E1 is only the border role; as text it becomes the plain palette colour, not a border token.
        findings, _ = self.findings(css=".x { color: #CBD5E1; }\n.y { border-color: #CBD5E1; }\n.z { color: #ffffff; }")
        self.assertEqual([f.message for f in findings],
                         ["`#CBD5E1` is `color.palette.line`.", "`#CBD5E1` is `color.border.default`.",
                          "`#ffffff` is `color.palette.white`."])

    def test_token_fallback_is_flagged(self):
        self.assertEqual(self.kinds(css=".x { border-radius: var(--pbly-radius-md, 8px); }"), ["fallback"])

    def test_hidden_token_system_is_flagged(self):
        css = ".pbly { --brand-teal: #098d78; --card-bg: var(--pbly-color-surface-raised); }"
        self.assertEqual(self.kinds(css=css), ["hidden-token"])

    def test_shadows_come_from_tokens(self):
        self.assertEqual(self.kinds(css=".x { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2); }"), ["shadow"])
        self.assertEqual(self.kinds(css=".x { box-shadow: var(--pbly-shadow-md); }"), [])

    def test_breakpoints_come_from_the_system(self):
        css = "@media (max-width: 75rem) { .x { display: none; } }"
        self.assertEqual(self.kinds(css=css), ["breakpoint"])
        self.assertEqual(self.kinds(css=css, config={"breakpoints": {"wideMaxPx": 1200}}), [])

    def test_font_face_descriptors_are_not_checked(self):
        css = '@font-face { font-family: "Brand"; font-weight: 500; src: url("x.woff2"); }'
        self.assertEqual(self.kinds(css=css), [])

    def test_inline_styles_are_checked_with_line_numbers(self):
        findings, _ = self.findings(html='<p style="margin-top: 15px">Inline</p>')
        self.assertEqual([f.kind for f in findings], ["snap"])
        self.assertEqual(findings[0].file, "index.html")
        self.assertGreater(findings[0].line, 1)

    def test_check_reports_every_area_in_one_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=".x { padding: 15px; }", html='<img src="assets/none.png" alt="">')
            (project / "foundation/button.css").write_text("/* changed */")
            (project / "README.md").unlink()
            result = check(project)
        areas = {issue.spec.area for issue in result.issues}
        self.assertEqual(areas, {"safety", "system", "structure", "handoff"})


class WorkflowContract(unittest.TestCase):
    """init → check → fix → promote, the way a person or an agent uses Portably."""

    def test_init_creates_a_project_that_asks_only_for_its_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(Path(tmp) / "new-site")
            self.assertTrue((project / "README.md").read_text().startswith("# new-site"))
            self.assertTrue((project / "AGENTS.md").is_file())
            self.assertFalse((project / "DESIGN-SYSTEM.md").exists())
            self.assertFalse((project / "DESIGN-SYSTEM.html").exists())
            config = json.loads((project / "portably.config.json").read_text())
            self.assertEqual(config, {"portably": portably_version(), "namespace": "pbly", "source": "",
                                      "assumptions": [], "deviations": [], "normalizations": [], "readability": []})
            result = check(project)
            self.assertEqual(groups(result), ["source"])
            self.assertEqual(result.issues[0].spec.level, "note")
            self.assertEqual(result.updated, ["DESIGN-SYSTEM.md", "DESIGN-SYSTEM.html"])
            config["source"] = "Screenshots of the home page, supplied 2026-09-28."
            (project / "portably.config.json").write_text(json.dumps(config))
            self.assertEqual(check(project).issues, [])

    def test_init_refuses_a_folder_that_has_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "keep.txt").write_text("mine")
            with self.assertRaisesRegex(InitError, "isn't empty"):
                create_project(tmp)
        with self.assertRaisesRegex(InitError, "Portably's own files"):
            create_project(ROOT / "starter")

    def test_fix_snaps_and_records_normalizations(self):
        css = (".x { padding: 15px 24px; color: var(--pbly-color-text-muted, #475569); }\n"
               ".y { color: #ffffff; margin: 80px; /* exception: hero */ }")
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=css, html='<p style="margin-top: 15px">Inline</p>')
            done = fix_project(project)
            page_css = (project / "css/pages/home.css").read_text()
            html = (project / "index.html").read_text()
            config = json.loads((project / "portably.config.json").read_text())
            result = check(project)
        self.assertIn(".x { padding: var(--pbly-space-4) var(--pbly-space-6); color: var(--pbly-color-text-muted); }", page_css)
        self.assertIn(".y { color: var(--pbly-color-palette-white); margin: 80px; /* exception: hero */ }", page_css)
        self.assertIn('style="margin-top: var(--pbly-space-4)"', html)
        self.assertEqual(len(done), 4)
        self.assertEqual(config["normalizations"], ["`15px` → `space.4` (padding, css/pages/home.css)",
                                                    "`15px` → `space.4` (margin-top, index.html)"])
        self.assertEqual(sorted(groups(result)), ["inline-style"])

    def test_fix_restores_foundation_and_readme_and_removes_stale_exceptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=".x { padding: 16px; /* exception: old reason */ }")
            (project / "foundation/button.css").write_text("/* changed */")
            (project / "README.md").unlink()
            fix_project(project)
            self.assertEqual(check(project).issues, [])
            self.assertIn(".x { padding: var(--pbly-space-4); }", (project / "css/pages/home.css").read_text())

    def test_promote_adds_the_token_and_uses_it_everywhere(self):
        css = (".a { padding-block: 80px; /* exception: hero */ }\n.b { margin-top: 80px; }\n"
               ".c { border-radius: 20px; }\n.d { border-radius: 20px; }")
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=css)
            self.assertEqual(sorted(groups(check(project))), ["promote", "promote"])
            promote(project, "spacing", "80px")
            with self.assertRaisesRegex(PromoteError, "--as radius.xl"):
                promote(project, "radius", "20px")
            promote(project, "radius", "20px", "xl")
            page_css = (project / "css/pages/home.css").read_text()
            tokens = json.loads((project / "tokens/tokens.json").read_text())
            result = check(project)
            doc = (project / "DESIGN-SYSTEM.md").read_text()
        self.assertIn(".a { padding-block: var(--pbly-space-20); }", page_css)
        self.assertIn(".d { border-radius: var(--pbly-radius-xl); }", page_css)
        self.assertEqual(list(tokens["radius"])[-2:], ["xl", "full"])
        self.assertEqual(result.issues, [])
        self.assertIn("| `space.20` | 80px |", doc)

    def test_promote_colour_and_breakpoint(self):
        css = ".a { color: #e11d48; }\n.b { border-color: #E11D48; }\n@media (max-width: 1200px) { .a { color: inherit; } }"
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=css)
            promote(project, "colour", "#E11D48", "brand-rose")
            promote(project, "breakpoint", "1200px", "wide")
            config = json.loads((project / "portably.config.json").read_text())
            page_css = (project / "css/pages/home.css").read_text()
            result = check(project)
        self.assertEqual(config["breakpoints"], {"wide": 1200})
        self.assertIn(".b { border-color: var(--pbly-color-palette-brand-rose); }", page_css)
        self.assertEqual(groups(result), [])

    def test_promote_leaves_close_but_different_values_alone(self):
        css = (".a { color: #E11D48; }\n.b { border-color: #E11D48; }\n"
               ".c { outline-color: #E31E4A; /* exception: close on purpose */ }")
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=css)
            lines = promote(project, "colour", "#E11D48", "brand-rose")
            page_css = (project / "css/pages/home.css").read_text()
        self.assertIn(".b { border-color: var(--pbly-color-palette-brand-rose); }", page_css)
        self.assertIn(".c { outline-color: #E31E4A; /* exception: close on purpose */ }", page_css)
        self.assertIn("used it in 2 places", lines[0])
        self.assertIn("Left 1 close but different value as written: `#E31E4A` (css/pages/home.css:28)", "\n".join(lines))

    def test_promote_refuses_values_that_break_the_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp)
            with self.assertRaisesRegex(PromoteError, "move in 2px"):
                promote(project, "spacing", "81px")
            with self.assertRaisesRegex(PromoteError, "already exists"):
                promote(project, "radius", "20px", "md")
            with self.assertRaisesRegex(PromoteError, "can't be promoted"):
                promote(project, "word-spacing", "1px")

    def test_unreadable_tokens_are_explained_not_crashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp)
            token_file = project / "tokens/tokens.json"
            token_file.write_text(token_file.read_text().replace('"canvas": {', '"canvas": {,', 1))
            result = check(project)
        self.assertEqual(groups(result), ["token-error"])
        self.assertIn("isn't valid JSON", result.issues[0].detail)

    def test_shadow_and_line_height_match_their_tokens(self):
        css = (".a { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12); line-height: 1.3; }\n"
               ".b { box-shadow: 0 4px 12px #0000001f; line-height: 1.5; }")
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=css)
            kinds = sorted(groups(check(project)))
            fix_project(project)
            page_css = (project / "css/pages/home.css").read_text()
            after = check(project)
        self.assertEqual(kinds, ["snap", "token-value", "token-value", "token-value"])
        self.assertIn(".a { box-shadow: var(--pbly-shadow-md); line-height: var(--pbly-font-line-height-snug); }", page_css)
        self.assertIn(".b { box-shadow: var(--pbly-shadow-md);", page_css)
        self.assertEqual(after.issues, [])

    def test_promote_line_height_and_shadow_keep_tokens_readable(self):
        css = (".a { line-height: 1.4; box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3); }\n"
               ".b { line-height: 1.4; box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3); }")
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=css)
            before = len((project / "tokens/tokens.json").read_text().splitlines())
            findings = check(project).issues
            promote(project, "line-height", "1.4", "comfortable")
            promote(project, "shadow", "0 2px 6px rgba(0, 0, 0, 0.3)", "card")
            lines = (project / "tokens/tokens.json").read_text().splitlines()
            result = check(project)
        self.assertEqual([i.command for i in findings if i.group == "promote"],
                         ["line-height 1.4 --as font.line-height.NAME", 'shadow "0 2px 6px rgba(0, 0, 0, 0.3)" --as shadow.NAME'])
        self.assertEqual(result.issues, [])
        self.assertLess(len(lines), before + 12)  # one token per line, not one value per line
        self.assertIn('    "card": {"$type":"shadow"', "\n".join(lines))

    def test_colour_roles_that_are_hard_to_read_together(self):
        def pale(source):
            source["color"]["palette"]["graphite"]["$value"] = "#B0B8C0"
        with tempfile.TemporaryDirectory() as tmp:
            result = check(client_project(tmp, tokens=pale))
        details = [i.detail for i in result.issues if i.group == "contrast-roles"]
        self.assertEqual(len(details), 2)
        self.assertIn("`color.text.muted` on `color.background` (text)", details[0])

    @unittest.skipUnless(__import__("importlib").util.find_spec("playwright"), "Playwright isn't installed")
    def test_browser_measures_text_contrast(self):
        html = ('<section class="section"><div class="wrapper"><p class="faint" style="color: var(--pbly-color-palette-line)">'
                'Faint words</p></div></section>')
        with tempfile.TemporaryDirectory() as tmp:
            result = run_check(client_project(tmp, html=html))
        found = [i.detail for i in result.issues if i.group == "low-contrast"]
        self.assertEqual(len(found), 1, result.skipped)
        self.assertIn("<p.faint> “Faint words” at 390px: #CBD5E1 on #F8FAFC", found[0])
        self.assertIn("The closest text colour that passes: #", found[0])

    @unittest.skipUnless(__import__("importlib").util.find_spec("playwright"), "Playwright isn't installed")
    def test_browser_measures_text_over_images_and_finds_cut_off_text(self):
        # A positioned <img> behind the text used to be invisible to the contrast check.
        css = (".pbly .photo { position: relative; }\n"
               ".pbly .photo img { position: absolute; inset: 0; width: 100%; height: 100%; }\n"
               ".pbly .photo p { position: relative; color: var(--pbly-color-text-primary); }\n"
               ".pbly .clip { overflow: hidden; }\n"
               ".pbly .huge { font-size: var(--pbly-font-size-5xl); }")
        html = ('<section class="section"><div class="wrapper"><div class="photo"><img src="assets/dark.svg" alt="">'
                '<p class="on-photo">Dark words</p></div>'
                '<div class="clip"><p class="huge">Supercalifragilisticexpialidocious</p></div></div></section>')
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=css, html=html)
            (project / "assets/dark.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
                                                     '<rect width="10" height="10" fill="#111111"/></svg>')
            result = run_check(project)
        contrast = " ".join(i.detail for i in result.issues if i.group == "low-contrast")
        self.assertIn("<p.on-photo> “Dark words”", contrast)
        self.assertIn("<p.huge> “Supercalifragilisticexpialidocious” runs past the edge at 390px.",
                      [i.detail for i in result.issues if i.group == "cut-off"])

    @unittest.skipUnless(__import__("importlib").util.find_spec("playwright"), "Playwright isn't installed")
    def test_text_scrolled_out_of_its_box_is_not_measured_against_the_page(self):
        css = (".pbly .code { width: 50%; overflow-x: auto; background: var(--pbly-color-text-primary); }\n"
               ".pbly .code code { color: var(--pbly-color-background); white-space: pre; }")
        html = ('<section class="section"><div class="wrapper"><pre class="code"><code>'
                + "light text on a dark box " * 12 + '</code></pre></div></section>')
        with tempfile.TemporaryDirectory() as tmp:
            result = run_check(client_project(tmp, css=css, html=html))
        self.assertNotIn("low-contrast", groups(result), result.skipped)

    def test_themes_are_found_in_the_project_css(self):
        cases = {
            '.pbly[data-theme="dark"] { --pbly-color-background: var(--pbly-color-palette-ink); }': ['data-theme="dark"'],
            "html.dark .pbly { --pbly-color-background: var(--pbly-color-palette-ink); }": ['class "dark"'],
            "@media (prefers-color-scheme: dark) { .pbly { --pbly-color-background: var(--pbly-color-palette-ink); } }":
                ["prefers-color-scheme: dark"],
            ".pbly .ground-dark { --pbly-color-background: var(--pbly-color-palette-ink); }": [],
            '.pbly[data-theme="dark"] { gap: var(--pbly-space-4); }': [],
        }
        for css, labels in cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                self.assertEqual([theme["label"] for theme in project_themes(client_project(tmp, css=css))], labels, css)

    @unittest.skipUnless(__import__("importlib").util.find_spec("playwright"), "Playwright isn't installed")
    def test_every_theme_is_measured(self):
        css = ('.pbly[data-theme="dark"] { --pbly-color-background: var(--pbly-color-palette-ink); }\n'
               "@media (prefers-color-scheme: dark) { .pbly { --pbly-color-text-primary: var(--pbly-color-palette-canvas);"
               " --pbly-color-text-muted: var(--pbly-color-palette-canvas); } }")
        with tempfile.TemporaryDirectory() as tmp:
            result = run_check(client_project(tmp, css=css))
        contrast = [i.detail for i in result.issues if i.group == "low-contrast"]
        self.assertTrue(any('with data-theme="dark"' in detail for detail in contrast), contrast)
        self.assertTrue(any("with prefers-color-scheme: dark" in detail for detail in contrast), contrast)
        self.assertFalse(any(" with " not in detail.split(": ")[0] for detail in contrast), contrast)

    @unittest.skipUnless(__import__("importlib").util.find_spec("playwright"), "Playwright isn't installed")
    def test_the_generated_design_system_pages_are_readable(self):
        for project in (ROOT / "starter", ROOT / "docs"):
            found, _ = browser_issues(project, pages=[project / "DESIGN-SYSTEM.html"])
            self.assertEqual([(i.group, i.detail) for i in found], [], project.name)

    @unittest.skipUnless(__import__("importlib").util.find_spec("playwright"), "Playwright isn't installed")
    def test_browser_check_finishes_on_a_page_that_cannot_scroll(self):
        css = "html { overflow: hidden; }"
        html = '<section class="section"><div class="wrapper"><p class="tall">Tall</p></div></section>'
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=css, html=html)
            index = project / "index.html"
            index.write_text(index.read_text().replace("<p class=\"tall\">Tall</p>", "<p>Line</p>" * 200))
            result = run_check(project)
        self.assertNotIn("browser-skipped", groups(result))

    @unittest.skipUnless(__import__("importlib").util.find_spec("playwright"), "Playwright isn't installed")
    def test_a_page_that_breaks_the_browser_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch("check_browser.page_issues", side_effect=RuntimeError("net::ERR_ABORTED\nmore")):
            result = run_check(client_project(tmp))
        skipped = [(i.where, i.detail) for i in result.issues if i.group == "browser-skipped"]
        self.assertEqual(skipped, [("index.html", "The browser checks couldn't finish at 390px: net::ERR_ABORTED")])

    def test_skipped_browser_checks_fail_a_strict_check(self):
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
            result = run_check(client_project(tmp))
        skipped = [i for i in result.issues if i.group == "browser-skipped"]
        self.assertEqual([i.detail for i in skipped], ["Playwright isn't installed."])
        self.assertEqual(skipped[0].spec.level, "note")

    def test_colour_roles_suggest_the_closest_passing_shade(self):
        def pale_brand(source):
            source["color"]["palette"]["accent"] = {"$type": "color", "$value": "#00915E"}
            source["color"]["action"]["primary"]["$value"] = "{color.palette.accent}"
        with tempfile.TemporaryDirectory() as tmp:
            result = check(client_project(tmp, tokens=pale_brand))
        details = [i.detail for i in result.issues if i.group == "contrast-roles"]
        self.assertEqual(details, ["`color.action.on-primary` on `color.action.primary` (button text) is 4.0:1; it needs 4.5:1. "
                                   "The closest shade that passes: `color.palette.accent` → #008855."])

    def test_readability_changes_are_listed_in_the_design_system(self):
        change = "color.palette.accent #00915E → #008855: white button text needs 4.5:1"
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, config={"readability": [change]})
            check(project)
            doc = (project / "DESIGN-SYSTEM.md").read_text()
        self.assertIn(f"## Changed for readability\n\nColours from the design that were adjusted", doc)
        self.assertIn(f"- {change}\n", doc)

    def test_button_shape_comes_from_tokens(self):
        def rounder(source):
            source["button"]["radius"]["$value"] = "{radius.lg}"
            source["button"]["padding-inline"]["$value"] = "{space.5}"
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, tokens=rounder)
            result = check(project)
            css = (project / "tokens/tokens.css").read_text()
            doc = (project / "DESIGN-SYSTEM.md").read_text()
        self.assertEqual(result.issues, [])
        self.assertIn("--pbly-button-radius: var(--pbly-radius-lg);", css)
        self.assertIn("| `button.radius` | `radius.sm` (4px) | `radius.lg` (16px) |", doc)

    def test_older_projects_are_told_to_add_button_tokens(self):
        def no_button(source):
            del source["button"]
        with tempfile.TemporaryDirectory() as tmp:
            result = check(client_project(tmp, tokens=no_button))
        self.assertIn("button.radius", " ".join(i.detail for i in result.issues if i.group == "tokens"))

    def test_misspelled_token_is_reported_with_its_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check(client_project(tmp, css=".x { padding: var(--pbly-space-44); }"))
        self.assertEqual(groups(result), ["unknown-variable"])
        self.assertRegex(result.issues[0].where, r"css/pages/home\.css:\d+")

    def test_every_finding_kind_has_plain_language_help(self):
        for name, group in GROUPS.items():
            self.assertTrue(group.title and group.why and group.todo, name)
            self.assertIn(group.area, {"safety", "system", "structure", "handoff"})
        kinds = {"tokens", "token-value", "snap", "off-system", "promote", "fallback", "hidden-token", "shadow",
                 "breakpoint", "stale-exception"}
        self.assertLessEqual(kinds, set(GROUPS))

    def test_report_separates_problems_from_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=".a { padding: 15px; }\n.b { margin: 80px; }")
            text = render(check(project).issues, "site", "python portably.py")
        self.assertIn("1 to fix (all automatically) · 1 to decide", text)
        self.assertIn("→ python portably.py promote site spacing 80px", text)
        self.assertIn("Next: `python portably.py fix site` fixes 1 of them automatically.", text)

    def test_design_system_doc_is_current_for_the_starter(self):
        system = __import__("check_system").load_system(ROOT / "starter")[0]
        self.assertEqual((ROOT / "starter/DESIGN-SYSTEM.md").read_text(), render_design_doc(ROOT / "starter", system, []))
        self.assertEqual((ROOT / "starter/DESIGN-SYSTEM.html").read_text(), render_page(gather(ROOT / "starter", system, [])))

    def test_design_system_page_draws_with_the_projects_tokens(self):
        context = {"source": "Figma: Shop & Co, frame `Home`.", "deviations": ["<Inter> replaces Graphik."]}
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, config=context,
                                     css=".a { padding-block: 80px; /* exception: hero spacing from the design */ }")
            check(project)
            page = (project / "DESIGN-SYSTEM.html").read_text()
        self.assertIn('<link rel="stylesheet" href="tokens/tokens.css">', page)
        self.assertIn('<body class="pbly">', page)
        self.assertIn('style="background: var(--pbly-color-action-primary)"', page)
        self.assertIn('style="border-radius: var(--pbly-radius-md)"', page)
        self.assertIn('<button class="pbly-btn pbly-btn--primary" type="button">Primary</button>', page)
        self.assertIn('scrollbar-width: thin; scrollbar-color: var(--pbly-color-text-soft) transparent', page)
        self.assertIn('.ds-embedded .pbly .ds-sidebar, .ds-embedded .pbly .ds-table { scrollbar-width: none; }', page)
        self.assertIn("Figma: Shop &amp; Co, frame <code>Home</code>.", page)
        self.assertIn("&lt;Inter&gt; replaces Graphik.", page)
        self.assertIn("hero spacing from the design", page)
        self.assertEqual(len(__import__("re").findall(r"<td>\d+\.\d:1</td><td>[\d.]+:1 · passes</td>", page)), 11)
        self.assertIn('<a href="index.html">Portably project starter</a>', page)

    def test_design_system_page_switches_between_the_projects_themes(self):
        dark = '.pbly[data-theme="dark"] { --pbly-color-background: var(--pbly-color-palette-ink); }'
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=dark)
            check(project)
            page = (project / "DESIGN-SYSTEM.html").read_text()
            plain = client_project(Path(tmp) / "plain")
            check(plain)
            plain_page = (plain / "DESIGN-SYSTEM.html").read_text()
        self.assertIn(dark.replace(" }", "}").replace("{ ", "{"), page.replace("{ ", "{").replace(" }", "}"))
        # the starter's default is light, so the button offers the dark theme
        self.assertIn('data-js="ds-theme" aria-label="Dark theme" aria-pressed="false">', page)
        self.assertIn('<p class="ds-where" data-js="ds-where"><strong>Project name</strong> · Design system</p>', page)
        self.assertIn(f'Generated by <a href="{HOME_URL}"', page)
        self.assertIn('<a class="ds-sidebar-link ds-sidebar-link--sub" href="#colours-palette">Palette</a>', page)
        self.assertIn('<h3 id="colours-palette">Palette</h3>', page)
        self.assertNotIn('<button class="ds-icon-button" type="button" data-js="ds-theme"', plain_page)
        self.assertNotIn('ds-back', page + plain_page)  # no way back: the page belongs to no other site

    @unittest.skipUnless(__import__("importlib").util.find_spec("playwright"), "Playwright isn't installed")
    def test_design_system_page_opens_in_the_theme_it_is_given(self):
        from playwright.sync_api import sync_playwright
        from check_browser import chromium_path
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chromium_path(), args=["--no-sandbox"])
            page = browser.new_page()
            page.goto((ROOT / "docs/DESIGN-SYSTEM.html").as_uri() + "?theme=light")
            self.assertEqual(page.evaluate("document.documentElement.dataset.theme"), "light")
            page.click('[data-js="ds-theme"]')
            self.assertIsNone(page.evaluate("document.documentElement.dataset.theme"))
            self.assertTrue(page.url.endswith("?theme=dark"))
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertFalse(page.is_visible("#ds-sidebar"))
            page.click('[data-js="ds-menu"]')
            page.click("#ds-sidebar >> text=Palette")
            self.assertFalse(page.is_visible("#ds-sidebar"))
            self.assertTrue(page.url.endswith("#colours-palette"))
            page.goto((ROOT / "docs/DESIGN-SYSTEM.html").as_uri() + "?embed")
            self.assertFalse(page.is_visible('[data-js="ds-theme"]'))

            # the docs show it below their own header, and their theme button switches both
            page.set_viewport_size({"width": 1440, "height": 900})
            page.goto((ROOT / "docs/pages/sample.html").as_uri())
            frame = page.frame_locator('[data-js="sample-frame"]')
            self.assertFalse(frame.locator('[data-js="ds-theme"]').is_visible())
            page.click('[data-js="theme-toggle"]')
            page.wait_for_timeout(500)
            self.assertEqual(frame.locator("html").get_attribute("data-theme"), "light")
            browser.close()

    def test_design_system_page_is_not_a_project_page(self):
        def experimental(source):
            source["color"]["experimental"] = {"$type": "color", "$value": "{color.palette.accent}"}
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, tokens=experimental)
            check(project)  # writes DESIGN-SYSTEM.html, which uses every token
            self.assertIn("--pbly-color-experimental", (project / "DESIGN-SYSTEM.html").read_text())
            self.assertEqual(groups(check(project)), ["unused-token"])
            self.assertEqual([p.name for p in __import__("check_system").html_pages(project)], ["index.html"])

    @unittest.skipUnless(__import__("importlib").util.find_spec("playwright"), "Playwright isn't installed")
    def test_design_system_page_passes_the_browser_checks(self):
        import check_browser
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(Path(tmp) / "acme", "acme")
            check(project)
            with unittest.mock.patch.object(check_browser, "html_pages", lambda p: [p / "DESIGN-SYSTEM.html"]):
                issues, _ = check_browser.browser_issues(project)
        self.assertEqual([(i.group, i.detail) for i in issues], [])

    def test_design_context_is_listed_in_the_design_system(self):
        context = {"source": "Figma: Booking app, frames Home and Search (2026-09-28).",
                   "assumptions": ["The mobile menu follows the desktop colours; no mobile design was supplied."],
                   "deviations": ["Inter replaces the licensed Graphik font."]}
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, config=context)
            result = check(project)
            doc = (project / "DESIGN-SYSTEM.md").read_text()
        self.assertEqual(result.issues, [])
        self.assertIn("## Where this design came from\n\nSource: Figma: Booking app, frames Home and Search (2026-09-28).", doc)
        self.assertIn("- The mobile menu follows the desktop colours; no mobile design was supplied.\n", doc)
        self.assertIn("- Inter replaces the licensed Graphik font.\n", doc)

    def test_design_system_maps_stylesheets_to_pages(self):
        css = ".pbly .price-card { padding: var(--pbly-space-4); }\n.pbly .price-card__amount { color: inherit; }"
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp)
            (project / "css/components/price-card.css").write_text(css)
            check(project)
            doc = (project / "DESIGN-SYSTEM.md").read_text()
        self.assertIn("| `css/components/cards.css` | `example-card` `example-grid` | `index.html` |", doc)
        self.assertIn("| `css/components/price-card.css` | `price-card` | _no page yet_ |", doc)
        self.assertIn("Pages: `index.html` (Portably project starter)", doc)

    def test_unreadable_design_notes_and_other_versions_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check(client_project(tmp, config={"portably": "0.15", "assumptions": "one sentence"}))
        found = {i.group: i.detail for i in result.issues}
        self.assertEqual(found, {"version": f"It records Portably 0.15; this is Portably {portably_version()}.",
                                 "context-format": "\"assumptions\" isn't a list of sentences."})
        self.assertEqual(GROUPS["version"].level, "note")

    def test_a_newer_minor_version_of_the_same_major_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check(client_project(tmp, config={"portably": "1.7"}))
        self.assertNotIn("version", groups(result))

    def test_fix_recreates_the_handoff_files_for_the_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(Path(tmp) / "acme", "acme")
            (project / "AGENTS.md").unlink()
            done = fix_project(project)
            guide = (project / "AGENTS.md").read_text()
        self.assertEqual(done, ["Created AGENTS.md from the Portably template."])
        self.assertIn("`acme-btn`", guide)
        self.assertNotIn("pbly", guide)

    def test_json_report_carries_what_the_text_report_says(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = client_project(tmp, css=".a { padding: 15px; }\n.b { margin: 80px; }\n.c { margin: 80px; }")
            result = check(project)
            data = as_data(result.issues, "site", "python portably.py", version="1.0")
            text = render(result.issues, "site", "python portably.py")
        self.assertEqual(data["counts"], {"problems": 1, "decisions": 1, "notes": 0, "fixable": 1})
        self.assertFalse(data["ready"])
        self.assertEqual(data["next"], "python portably.py fix site")
        self.assertEqual(data["generatedArtifacts"],
                         ["tokens/tokens.css", "DESIGN-SYSTEM.md", "DESIGN-SYSTEM.html"])
        snap, promotion = data["issues"]
        self.assertEqual((snap["kind"], snap["area"], snap["level"], snap["file"], snap["fixable"], snap["decision"]),
                         ("snap", "system", "problem", "css/pages/home.css", True, False))
        self.assertIsInstance(snap["line"], int)
        self.assertEqual(snap["command"], "python portably.py fix site")
        self.assertEqual((promotion["kind"], promotion["decision"], promotion["command"]),
                         ("promote", True, "python portably.py promote site spacing 80px"))
        self.assertEqual(len(promotion["places"]), 2)
        for item in data["issues"]:
            self.assertIn(item["title"], text)
            self.assertIn(item["detail"], text)
            self.assertIn(item["action"], text)

    def test_command_line(self):
        import subprocess
        run = lambda *args: subprocess.run([sys.executable, str(ROOT / "portably.py"), *args],
                                           capture_output=True, text=True)
        with tempfile.TemporaryDirectory() as tmp:
            target = str(Path(tmp) / "site")
            created = run("init", target)
            self.assertEqual(created.returncode, 0, created.stderr)
            self.assertIn("Ready. Start building", created.stdout)
            passed = run("check", target, "--no-browser")
            self.assertEqual(passed.returncode, 0, passed.stdout)
            self.assertIn("Ready for handoff", passed.stdout)
            self.assertIn("Browser checks were turned off with --no-browser", passed.stdout)
            strict_without_browser = run("check", target, "--strict", "--no-browser")
            self.assertEqual(strict_without_browser.returncode, 1, strict_without_browser.stdout)
            self.assertIn("Browser checks were turned off with --no-browser", strict_without_browser.stdout)
            page = Path(target) / "css/pages/home.css"
            page.write_text(page.read_text() + "\n.x { margin: 80px; }\n")
            self.assertEqual(run("check", target, "--no-browser").returncode, 1)
            self.assertEqual(run("check", tmp).returncode, 2)
            report = run("check", target, "--no-browser", "--json")
            data = json.loads(report.stdout)
            self.assertEqual(report.returncode, 1)
            self.assertEqual((data["format"], data["portably"], data["ready"]), (1, portably_version(), False))
            self.assertEqual(data["generatedArtifacts"],
                             ["tokens/tokens.css", "DESIGN-SYSTEM.md", "DESIGN-SYSTEM.html"])
            self.assertEqual([i["kind"] for i in data["issues"]], ["browser-skipped", "off-system", "source"])
            fixed = json.loads(run("fix", target, "--no-browser", "--json").stdout)
            self.assertEqual(fixed["fixed"], [])
            failed = run("check", tmp, "--json")
            self.assertEqual(failed.returncode, 2)
            self.assertIn("doesn't look like a Portably project", json.loads(failed.stdout)["error"])


if __name__ == "__main__":
    unittest.main()