# DESIGN.md - ballast.

## Context (from discovery)

- Artifact type: composite. Region 1 is a product landing page for advisory firms; region 2 is an embedded product demo (guided replay of the genome); region 3 is a live operations dashboard (`/live`).
- Positioning: technical with a humane voice. A financial-services product that has to read as accountable, not flashy.
- Audience: registered investment advisers (RIAs) and the households they serve; hackathon judges from Meta and Google DeepMind. Primary action: understand in seconds how the agent improves and why it can be trusted, then step through the replay.
- Adjectives: accountable, precise, alive, calm.
- Visual word translations:
  - accountable -> every number has a source, a sign and a direction glyph; every mutation shows its cause and its measured effect.
  - precise -> tabular figures, right-aligned numerals, mono for tickers and IDs, an 8px spacing grid, two radius values.
  - alive -> the genome is a slowly turning helix that changes when Muse edits it; the live view streams real runs.
  - calm -> flat surfaces, one accent, no ambient glow, no decorative grid, motion only when state changes.
- Aesthetic essence: living ledger genome.
- Single-minded proposition: the playbook is the agent's genome, and you can see every mutation, why it happened and what it proved.
- References: admire greenroom-studio (the hero object is the product's own metaphor and it is interactive), Bloomberg and TradingView (numeric discipline), Stripe (one projection, hard color stops); avoid generic neon-on-black AI dashboards and isometric stock illustration.
- Mode: both (dark default, light via tokens and a toggle). Density: balanced on the landing regions, dense on `/live`.
- Constraints: vanilla HTML/CSS/JS, no build step, FastAPI static serving; WCAG 2.2 AA; must keep the track line, "Powered by Muse", the SubQ emphasis and the disclaimer.

## Aesthetic

- Direction: bespoke "living ledger". A dark green ledger surface, a single mint accent, and one structural 2.5D object.
- Defining trait: structure carries meaning. The helix is the playbook, each base pair is a playbook element, each color is a mutation kind, each axonometric diagram is a real system diagram.
- Signature move: the genome helix. Each base pair is one playbook element (prompt, each skill, max_turns). Inserted pairs are mint with a plus, edited pairs are gold with a tilde, removed pairs are red ghosts with a minus, drafts are Muse-blue dashes. Mutations that fail the gate stay on a dashed strand that never joins the lineage.

## Typography

- Display: Unbounded | Google Fonts | OFL. Wide geometric, used only for headings, numerals and the wordmark.
- Body: Hanken Grotesk | Google Fonts | OFL.
- Mono: JetBrains Mono | Google Fonts | OFL. Tickers, case IDs, run IDs, YAML, log lines.
- Scale: ratio 1.25 (Major Third), base 16px.

| step | size | line-height | use |
|------|------|-------------|-----|
| display | 49px (clamp 34-49) | 1.08 | page headline |
| h2 | 31px (clamp 24-31) | 1.15 | section |
| h3 | 20px | 1.25 | panel title, step title |
| body | 16px | 1.6 | text |
| small | 14px | 1.5 | meta, table cells |
| micro | 12px | 1.4 | captions, chart labels |

- Weights: 400/500/700 body, 700/800 display. Measure: 62-72ch. Tracking: display -0.02em, never tighter.

## Color

- Strategy: money green is the category's expected hue, so the system commits to it fully as the dominant (surfaces are green-tinted, not neutral black) and lets one bright mint carry every positive signal. Muse is a sky blue at H 240, outside the indigo/violet band. Semantic states are always paired with a glyph (plus, minus, up and down triangles, check and cross).
- Distribution: 60 green-tinted neutrals / 30 brand green / 10 mint accent plus semantic states.
- Palette (dark, role -> OKLCH | hex):
  - bg: oklch(0.165 0.022 165) | #07160f
  - surface: oklch(0.205 0.026 165) | #0c1f17
  - surface-2: oklch(0.24 0.03 165) | #12281f
  - fg: oklch(0.965 0.012 160) | #ecf8f1
  - muted: oklch(0.70 0.035 160) | #93ad9f
  - border: oklch(0.34 0.04 165) | #284337
  - accent / positive: oklch(0.86 0.17 158) | #6ff0b1
  - accent-fg: oklch(0.165 0.022 165) | #07160f
  - warning / gate: oklch(0.84 0.14 85) | #e9c45d
  - error / negative: oklch(0.70 0.19 18) | #f2606f
  - muse: oklch(0.80 0.11 240) | #8fc2f2
  - subq: oklch(0.86 0.11 195) | #77e0e3
- Light overrides: bg oklch(0.975 0.008 160), surface oklch(0.995 0.004 160), fg oklch(0.22 0.03 165), muted oklch(0.48 0.035 165), border oklch(0.86 0.02 160), accent oklch(0.50 0.13 158), warning oklch(0.56 0.12 75), error oklch(0.53 0.2 22), muse oklch(0.50 0.13 245), subq oklch(0.52 0.1 205), accent-fg #ffffff.

## Spacing, radius, shadow

- Spacing base: 8px; scale 4, 8, 12, 16, 24, 32, 48, 64, 96.
- Radius: two values, 8px (surfaces, tiles, inputs) and pill (buttons, chips).
- Shadow approach: defined edge only. Surfaces step by lightness and carry a 1px border; no drop shadows, no glows.

## Layout and composition

- Grid: 12-column, max 1200px, 16px mobile gutter. Sections separated by 96px, groups inside by 16-24px.
- Signature layout move: the replay stage splits story (left, 5 columns) and genome (right, 7 columns); under it, a three-column mutation strip reads left to right as cause, change, effect, followed by a full-width before/after line.
- Density: balanced (landing), dense (`/live`). Scanning: Z on the intro, F on panels.
- Responsive: desktop-first layout, mobile verified at 375px; the helix keeps its geometry and moves labels into an HTML base-pair list; the replay controls stick to the bottom.

## Components and states

- Buttons: primary filled mint (one per region), secondary filled surface with border, tertiary text. States: hover lightens surface, active translates 1px, focus 2px ring via box-shadow in the warning token, disabled 40% opacity, pressed (Play) swaps to the warning fill.
- Chips (steps, lineage rail): pill, surface fill, current step inverted; each carries a kind glyph.
- Tables: text left, numbers right, tabular-nums, 1px separators, 40px rows.
- Overlays: native `<dialog>` sheets, Escape closes, focus returns to the trigger, backdrop click closes.
- Empty: one line stating the condition plus the next action. Loading: one line naming what is loading. Error: what failed plus the fix, under 10 words where possible.
- Live states: connecting, live, stale (no rows for 2 minutes), offline; the dot only animates in the live state.

## Motion

- Duration scale: 120ms (hover), 200ms (state), 320ms (sheet), 4.5s (helix revolution step).
- Easing: --ease-out cubic-bezier(0.22, 1, 0.36, 1); --ease-in-out cubic-bezier(0.65, 0, 0.35, 1). No overshoot.
- What animates: transform and opacity only, plus the helix phase (SVG attributes, rAF, paused offscreen).
- Reduced motion: helix freezes at a fixed phase, scan beams and the loop packet are removed, stamps appear without movement.
- Signature motion: the helix turns slowly; when a mutation lands, the new base pair fades in.

## Iconography

- Set: typographic glyphs only (plus, tilde, minus, up and down triangles, check, cross) set in the body face; no icon font. Diamonds (45deg squares) mark kinds in chips.

## Imagery and illustration

- Mode: product visuals only. Every illustration is a live diagram drawn from data: the genome helix, the loop diagram, the exploded stack, the score curve.
- Avoid: stock imagery, mascots, gradient blobs, glossy isometric scenes that do not encode data.

## Dark mode

- Base bg L 0.165, surfaces step +0.04 L, borders lighter than surfaces. Accents keep chroma but stay under L 0.87; in light mode accents drop to L ~0.5 to keep 4.5:1.

## Accessibility

- Contrast: AA in both modes (muted text L 0.70 on bg L 0.165; light muted L 0.48 on L 0.975).
- Focus: visible ring on every interactive element; sticky bars do not cover focused content (scroll-padding-top).
- Keyboard: arrows step the replay, tabs follow the ARIA tabs pattern, dialogs trap and return focus.
- Targets: at least 32px; replay controls 44px on mobile.
- Color independence: every pass/fail, mutation and delta carries a glyph or word.
- Reduced motion: honored as above.

## Tokens (source of truth)

See `web/static/app.css` `:root` and `[data-theme="light"]`. Adapter: plain CSS custom properties.

## Cards and surfaces

- One surface level per region: panels are surface + 1px border + 8px radius + 24px padding. No cards inside cards; inner groups use dividers or a background step.

## Slop audit

- Date: 2026-11-07 | Result: pass, 9/10. Fixed 11 tells from v2; 2 deliberate exceptions recorded.
- Fixed from v2: decorative blueprint grid and diagonal streak behind the page; radial spotlight glows behind the stage; glowing colored box-shadows and SVG glow filters; side-tab accent borders (fact callout, trace items); eyebrow pill above the headline; full-sentence 68px headline (now 6 words at 49px); overshoot easing on slabs and stamps; repeating-stripe error tiles; backdrop-blur glass on the top bar and controls; radii of 14 to 28px (now 8px and pill); color-only pass/fail (tiles and lists now carry check, cross, plus, minus, up and down glyphs).
- Deliberate exceptions: (1) the helix turns continuously; it is the signature object, it pauses offscreen and in background tabs, and reduced motion freezes it. (2) The intro uses a three-column definition strip (who, what, why); it is text with dividers, not cards, and it answers the brief's three questions directly.
- Financial UI checks: tabular figures on every number; numbers right-aligned in tables; explicit + and − signs with up and down triangles on every delta; tickers, case IDs and rule IDs in JetBrains Mono; semantic tokens only, no raw hex in components; light theme from the same tokens; live view shows connecting, live, stale and offline.
- Accessibility gate: pass. Focus ring on every control; arrow keys step the replay; tabs follow the ARIA pattern; dialogs are native and return focus; targets 32px or more (44px replay controls); AA contrast checked on token pairs in both themes.
- Copy (deslop-ui), main changes:

| # | Original | Type | Replacement |
|---|---|---|---|
| 1 | A portfolio agent for every client that gets measurably better with every run. | overlong | Every client gets their own agent. |
| 2 | Watch it learn | verbose | The genome |
| 3 | How it works | overlong | The loop |
| 4 | Improve every run | overlong | Improve |
| 5 | Clients and their agents | overlong | Clients |
| 6 | What Muse changed in the playbook | overlong | What changed |
| 7 | Every part has one job. Pick a layer to see what it does. | verbose | Every part has one job. Pick a layer to see it. |
| 8 | Data didn't load. Check that the API is running, then reload. | verbose | Data didn't load. Reload the page. |
| 9 | Every case lands here as the agent finishes it. Open any cell for the full trace. | verbose | Each case appears when the agent finishes it. Open a tile for the full trace. |
| 10 | Muse writes a fix (step chip) | superlative-free but vague | Muse drafts a fix |

  Slop score: original 34/50, rewrite 44/50 (directness 9, concision 9, trust 9, authenticity 8, clarity 9).

## Changelog

- 2026-11-07: v3.2. Lessons ledger ("What it has learned"): each lesson in first person at display size, with learned-from (trigger, date, root cause, the failing detail) and proven-on (rule failures on unseen clients before and after, holdout journey checkpoints); raw YAML behind "View playbook". Client journeys: a checkpoint timeline (market regime band, life events, generic agent vs the client's own agent, lessons where learned) with three tile states (clean, soft miss, hard fail) carrying glyphs. Coverage map in The loop: learned, seen, not seen yet, plus the unknown-event path (Snap flags, re-run first, Muse learns). Live defaults to ballast_muse and works without a loop log. Benchmark reads real runs.
- 2026-11-07: v3.1. SubQ Snap decision gates: replay step before drift, probability bars beside the rule checker's verdict, Live gates table, Stack split into Snap and Preview.
- 2026-11-07: v3. Genome helix replaces the slab stack; OKLCH tokens with a light theme; removed decorative grid, streak, glows, side-tab borders, overshoot easing and the eyebrow pill; business copy for advisory firms; mutation strip (why, change, learned).
