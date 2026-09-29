# Accessibility contract

Accessibility is part of how every component is built, not a final audit step. This checklist is the minimum for the foundation and for every interactive component in a project; a project may add more.

## Foundation

- use semantic HTML before ARIA
- preserve recognizable links, lists and native control behavior unless a component intentionally replaces presentation
- provide visible `:focus-visible` treatment
- respect `prefers-reduced-motion`
- do not set a fixed pixel root font size; allow user text-size preferences to scale `rem`-based type/spacing
- avoid color as the only carrier of meaning
- maintain sufficient contrast for the project theme: 4.5:1 for normal text, 3:1 for large text and for field borders. `portably.py check` tests the colour roles in `tokens.json` and, with Playwright installed, every piece of rendered text (`SYSTEM.md`, section 8)
- preserve sensible zoom/reflow and keyboard navigation

## Every interactive component

- choose the correct native element (`button` for actions, `a[href]` for navigation)
- provide an accessible name
- verify keyboard operation and focus order
- define hover, focus-visible, active and disabled/unavailable states where applicable
- do not use `aria-disabled` as a substitute for actually preventing an action
- use ARIA only when native semantics are insufficient, and keep state attributes synchronized with behavior
- avoid unexpected focus movement
- make motion non-essential and reducible
- test at high zoom/narrow viewport and with keyboard-only interaction

## Button contract

- use `<button type="button">` unless submit/reset behavior is deliberately required
- links styled as buttons remain links and must have a valid `href`
- disabled native buttons use `disabled`; a visually disabled link needs project-specific behavior and semantics rather than a fake universal disabled class
- icon-only buttons require an accessible name
- focus-visible styling must remain visible in every project theme

A component is not ready merely because its CSS renders correctly: it also needs the right semantics, keyboard behaviour, states and accessible names.
