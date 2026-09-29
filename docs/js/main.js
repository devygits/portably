const root = document.documentElement;

// Theme: dark by default; the choice is remembered on this device.
const themeToggle = document.querySelector('[data-js="theme-toggle"]');
const sample = document.querySelector('[data-js="sample-frame"]');

// The design-system sample follows the site's theme. Its page is changed directly where the browser allows it,
// and reopened in the theme where it doesn't (pages opened as files).
const showSampleTheme = (light) => {
  if (!sample) return;
  try {
    const page = sample.contentDocument && sample.contentDocument.documentElement;
    if (page && page.classList.contains('ds-embedded')) {
      if (light) page.dataset.theme = 'light';
      else delete page.dataset.theme;
      return;
    }
  } catch (error) { /* not reachable from here */ }
  sample.src = `${sample.src.split('?')[0]}?embed&theme=${light ? 'light' : 'dark'}`;
};

if (sample && root.dataset.theme === 'light') showSampleTheme(true);

if (themeToggle) {
  const showTheme = () => {
    const light = root.dataset.theme === 'light';
    themeToggle.setAttribute('aria-pressed', String(light));
  };

  themeToggle.addEventListener('click', () => {
    const light = root.dataset.theme !== 'light';
    if (light) root.dataset.theme = 'light';
    else delete root.dataset.theme;
    try { localStorage.setItem('portably-theme', light ? 'light' : 'dark'); } catch (error) { /* storage unavailable */ }
    showTheme();
    showSampleTheme(light);
  });

  showTheme();
}

// "Back to docs" returns to the docs page the reader came from.
document.querySelectorAll('[data-js="back-to-docs"]').forEach((link) => {
  try {
    const from = new URL(document.referrer);
    if (from.origin === location.origin && from.pathname !== location.pathname) link.href = from.href;
  } catch (error) { /* opened directly: the link keeps the first page */ }
});

// Navigation on small screens.
const navToggle = document.querySelector('[data-js="nav-toggle"]');

if (navToggle) {
  const navigation = document.getElementById(navToggle.getAttribute('aria-controls'));

  const setOpen = (open) => {
    navToggle.setAttribute('aria-expanded', String(open));
    if (navigation) navigation.dataset.open = String(open);
  };

  if (navigation) {
    navToggle.addEventListener('click', () => setOpen(navToggle.getAttribute('aria-expanded') !== 'true'));

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && navToggle.getAttribute('aria-expanded') === 'true') {
        setOpen(false);
        navToggle.focus();
      }
    });
  }
}

// Syntax colours for code blocks that name their language (data-lang). Each rule is a pattern and the
// class its matches get; the first rule that matches at a position wins.
const SYNTAX = {
  bash: [
    [/#.*/, 'comment'],
    [/"[^"\n]*"|'[^'\n]*'/, 'string'],
    [/^(?:python|python3|pip|git|playwright|cd)\b/, 'keyword'],
    [/(?<=\s)--?[\w-]+/, 'name'],
  ],
  html: [
    [/<!--[\s\S]*?-->/, 'comment'],
    [/<\/?[\w-]+|\/?>/, 'keyword'],
    [/[\w:-]+(?==)/, 'name'],
    [/"[^"]*"/, 'string'],
  ],
  css: [
    [/\/\*[\s\S]*?\*\//, 'comment'],
    [/"[^"\n]*"/, 'string'],
    [/[^{}\s;][^{};]*?(?=\s*\{)/, 'keyword'],
    [/(?<=[{;]\s*)[\w-]+(?=\s*:)/, 'name'],
    [/--[\w-]+/, 'name'],
    [/#[\da-fA-F]{3,8}\b|(?<![\w-])-?\d*\.?\d+(?:[a-z]+|%)?/, 'value'],
  ],
  json: [
    [/"(?:[^"\\\n]|\\.)*"(?=\s*:)/, 'name'],
    [/"(?:[^"\\\n]|\\.)*"/, 'string'],
    [/-?\d+(?:\.\d+)?|\btrue\b|\bfalse\b|\bnull\b/, 'value'],
  ],
  js: [
    [/\/\/.*|\/\*[\s\S]*?\*\//, 'comment'],
    [/"[^"\n]*"|'[^'\n]*'|`[^`]*`/, 'string'],
    [/\b(?:const|let|function|return|export|import|from|default|if|else)\b|<\/?[\w.]+|\/?>/, 'keyword'],
    [/[\w-]+(?==)/, 'name'],
    [/(?<![\w-])\d+(?:\.\d+)?/, 'value'],
  ],
};

const span = (text, kind) => {
  const element = document.createElement('span');
  element.className = `code-block__${kind}`;
  element.textContent = text;
  return element;
};

const highlight = (source, rules) => {
  const pattern = new RegExp(rules.map(([rule]) => `(${rule.source})`).join('|'), 'gm');
  const parts = [];
  let last = 0;
  for (const match of source.matchAll(pattern)) {
    if (!match[0]) continue;
    const rule = match.slice(1).findIndex((group) => group !== undefined);
    parts.push(source.slice(last, match.index), span(match[0], rules[rule][1]));
    last = match.index + match[0].length;
  }
  parts.push(source.slice(last));
  return parts;
};

// A file tree: the lines, then the name, then what it is.
const highlightTree = (source) => source.split('\n').flatMap((line, index) => {
  const [, lines, name, gap, note] = line.match(/^([\s│├└─]*)(\S+(?: \S+)*)?(\s*)(.*)$/);
  return [index ? '\n' : '', span(lines, 'tree'), name || '', gap, note ? span(note, 'note') : ''];
});

document.querySelectorAll('[data-js="code-block"][data-lang]').forEach((block) => {
  const code = block.querySelector('code');
  const lang = block.dataset.lang;
  if (!code || !(lang === 'tree' || SYNTAX[lang])) return;
  const source = code.textContent;
  code.replaceChildren(...(lang === 'tree' ? highlightTree(source) : highlight(source, SYNTAX[lang])));
});

// A copy button on every code block.
document.querySelectorAll('[data-js="code-block"]').forEach((block) => {
  const code = block.querySelector('code');
  if (!code || !navigator.clipboard) return;

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'code-block__copy';
  button.textContent = 'Copy';
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(code.textContent);
      button.textContent = 'Copied';
    } catch (error) {
      button.textContent = 'Copy failed';
    }
    setTimeout(() => { button.textContent = 'Copy'; }, 2000);
  });
  block.append(button);
});

// "On this page": mark the section being read.
const tocLinks = [...document.querySelectorAll('[data-js="toc-link"]')];

if (tocLinks.length && 'IntersectionObserver' in window) {
  const byId = new Map(tocLinks.map((link) => [link.hash.slice(1), link]));
  const visible = new Set();

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) visible.add(entry.target.id);
      else visible.delete(entry.target.id);
    });
    const current = [...byId.keys()].find((id) => visible.has(id));
    if (!current) return;
    tocLinks.forEach((link) => link.removeAttribute('aria-current'));
    byId.get(current).setAttribute('aria-current', 'true');
  }, { rootMargin: '-64px 0px -60% 0px' });

  byId.forEach((link, id) => {
    const section = document.getElementById(id);
    if (section) observer.observe(section);
  });
}
