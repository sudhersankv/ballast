# DESIGN.md - ballast.

## Context (from discovery)

- Artifact type: composite. Product landing page for advisory firms, an embedded replay of the training lineage, a lessons ledger, client journeys, and a live operations view (`/live`).
- Positioning: technical, accountable. A financial-services agent that proves every claim with a number.
- Audience: registered investment advisers (RIAs) and their households; hackathon judges from Meta and Google DeepMind. Viewed on phones as often as laptops.
- Primary action: see in seconds that the agent improves on unseen clients, catches drift, and learns per client; then step through the replay.
- Adjectives: precise, accountable, instrumented, calm.
- Visual word translations:
  - precise -> every figure is mono, tabular, slashed-zero, three decimals for scores, signed deltas with triangles.
  - accountable -> every number names its source (live db, demo replay, n of N clients).
  - instrumented -> tapes with graduations, magenta target bugs at gate thresholds, a barber-pole band for drift, registration marks on every module.
  - calm -> dark ink, square geometry, no glows, motion only when state changes.
- Aesthetic essence: instrument panel ledger.
- Single-minded proposition: the agent's improvement is a measured, sourced number, version by version.
- References (2026-11-07): Bloomberg Terminal (one identity color carried by text, dense rules, green up / red down, figures as hero); Teenage Engineering OP-1 (one constrained screen, a geometric motif and color per mode); avionics primary flight displays (moving tapes with high values at the top, labeled major ticks every fifth graduation, magenta target bugs, red barber-pole limit bands). Avoid: neon-on-black AI dashboards, rounded SaaS cards, gradient decoration.
- Mode: dark only. Density: balanced on the story regions, dense on `/live` and the journey lattice.
- Constraints: vanilla HTML/CSS/JS served by FastAPI; WCAG 2.2 AA; keep the track line, "Powered by Muse", SubQ emphasis, disclaimer.

## Aesthetic

- Direction: bespoke "instrument panel ledger".
- Defining trait: geometry is the data. The rule radar plots each version as a polygon over the 10 policy rules; the genome lattice plots versions as columns and playbook elements as rows, with a number on every pair; tapes and ticks carry every score.
- Signature move: the rule radar. Each version is a polygon on a 0.50 to 1.00 polar scale; the current version is filled and its sub-1.00 vertices are labeled; drift breaks are crossed on the rim; SubQ's patterns appear as cyan diamonds at their failure rates.

## Typography

- Display: Chakra Petch (600/700) | Google Fonts | OFL. Angular technical sans for headings and the wordmark.
- Body: IBM Plex Sans (400/500/600) | Google Fonts | OFL.
- Figures and labels: IBM Plex Mono (400/500/600) | Google Fonts | OFL. All numbers, tickers, IDs, rule names, buttons, nav.
- Scale: ratio 1.25, base 15px. display 52 (clamp 34-52) / h2 36 / h3 22-28 / body 15 / meta 13 / micro 11-12. Hero numeral 112px mono, replay numeral 84px mono.
- Numerals: tabular-nums + slashed-zero everywhere; scores to 3 decimals; deltas signed with ▲ ▼.

## Color (OKLCH, dark only)

- Strategy: cool graphite ink, so no single hue owns the page; each semantic role gets one color and keeps it everywhere. The luminous green means aligned or positive and nothing else.
- Palette (role -> OKLCH | approx hex):
  - bg (ink): oklch(0.155 0.012 250) | #0b0f14
  - surface (panel): oklch(0.19 0.014 250) | #12171e
  - surface-2: oklch(0.225 0.016 250) | #191f27
  - border/rule: oklch(0.33 0.02 250) | #333b46
  - page grid: oklch(0.22 0.014 250)
  - fg: oklch(0.95 0.008 250) | #eef1f5
  - fg-2: oklch(0.80 0.014 250) | #c0c6cf
  - muted: oklch(0.66 0.018 250) | #8f98a4
  - signal (aligned, positive): oklch(0.87 0.15 152) | #78e8a8
  - gold (gates, money): oklch(0.84 0.13 85) | #e9c46a
  - red (drift, negative): oklch(0.69 0.19 22) | #f0606a
  - cyan (SubQ): oklch(0.84 0.11 205) | #6fd3e0
  - blue (Muse): oklch(0.76 0.12 245) | #7fb1ee
  - magenta (target bugs): oklch(0.72 0.18 345) | #e86aa8
- Contrast: fg on bg about 16:1; muted on bg about 6:1; signal on bg about 13:1; on-accent (bg) on signal about 13:1.

## Spacing, radius, shadow

- Spacing base 4px; rhythm 6 / 10 / 14 / 22 / 28 / 88. Tight inside instruments, 88px between sections.
- Radius: 0 everywhere (square geometry); 2px reserved token unused.
- Shadow: none. Defined edges only: 1px rule borders plus registration-mark corner ticks on every module.

## Layout and composition

- Grid: a visible 12-column grid behind `main` (4 columns under 1000px); sections are numbered 01 / to 05 / (they are a sequence down the page).
- Signature layout move: hero splits copy (6 cols) and the live instrument board (6 cols); the replay stage splits story (4 cols) and the radar + lattice pair (8 cols); the mutation strip reads cause, change, effect.
- Responsive: verified at 520px (all phone breakpoints active) and 1440px; replay controls stick to the bottom on phones; the journey lattice scrolls sideways with a sticky label column.

## Components and states

- Buttons: square, mono labels; primary filled signal, secondary panel with rule border; hover lightens, active nudges 1px, focus 2px gold ring via box-shadow, disabled 40%, pressed (Play) gold.
- Tapes: 10% minor ticks, 50% major ticks, fill for the value, magenta bug for the gate threshold.
- Tables: text left, numbers right, mono figures, 1px rules.
- Tiles (live cells, journey checkpoints): square; ✓ clean, ◐ soft miss, ✕ hard fail, ! error, blinking gold only while a case is actually running.
- Live states: connecting, live (blinking diamond only while rows arrive), stale (gold, with "last run N min ago"), offline (red, retry every 3 s).
- Empty states: one sentence plus what makes it fill.

## Motion

- 120ms hover, 200ms state, 280ms sheet; ease-out cubic-bezier(0.22, 1, 0.36, 1); no overshoot.
- Only transform and opacity animate (plus the loop packet's SVG position). The helix rotation is gone; nothing moves unless state changed or data is live.
- Reduced motion: all animation collapses to instant.

## Iconography

- Typographic and geometric only: diamonds for kinds, squares for gates, triangles for deltas, crosses for breaks.

## Imagery

- No imagery. Every visual is plotted data: radar, lattice, tapes, curve, loop diagram, exploded stack, journey lattice.

## Accessibility

- AA contrast verified on token pairs; visible focus everywhere; arrow keys step the replay; ARIA tabs; native dialogs.
- Color independence: glyphs on every state (✓ ✕ ◐ ▲ ▼ + ~ −), labels beside every bar.
- Targets: 36px minimum, 44px for replay controls.

## Tokens (source of truth)

`web/static/app.css` `:root`. Adapter: plain CSS custom properties.

## Slop audit (v4, 2026-11-07)

- frontend-design-deslop checklist: 9/10.
  - Pass: no indigo/violet accent, no gradient text, no cream, no glowing shadows, no radial spotlight; Chakra Petch + Plex pairing (not Inter/Space Grotesk/Geist); no eyebrow pill; numbered markers only on a true sequence; no side-tab borders; border XOR shadow; radius 0; no glassmorphism; no stock imagery; full button and live state matrices; numbers right-aligned and tabular.
  - Deliberate exceptions (structural, per the user's brief): the visible 12-column page grid (a measurement grid with section coordinates, not texture); the barber-pole hatching on drift bands and crash regimes (the avionics limit convention, it encodes "limit exceeded").
- financial-ui-patterns verification: every number tabular (yes); semantic tokens only (yes); light theme (dropped by explicit user request; tokens remain centralized); tick flash (not used: data updates at most every 3 s and per case, so the live tiles appear as new cells instead); stale state visible (yes); + sign on positive deltas (yes); numbers right, labels left (yes); tickers and IDs mono (yes); no dynamic Tailwind (n/a, plain CSS); color paired with glyph (yes); status pills for run states (yes, square tiles with glyphs); density (5+ rows visible on a laptop in every table).
- deslop-ui: buttons <= 3 words (Back, Next step, Play, Next hop, View playbook); section headers 1-4 words; errors state the cause and the fix ("Can't read ballast_muse: ... Retrying every 3 s."); empty states one sentence ("No lessons yet. They appear when Muse ships its first upgrade."). Score 45/50 (directness 9, concision 9, trust 9, authenticity 9, clarity 9).
- Accuracy fix in this round: the regression gate copy said "must stay at 100%"; the real runtime ships when regression is held relative to the parent. All copy and gates now say "must not drop below the parent".

## Changelog

- 2026-11-07: v4. Full visual overhaul to the "instrument panel ledger" direction: dark-only cool graphite OKLCH palette, Chakra Petch + IBM Plex Sans + IBM Plex Mono, square geometry with registration marks and a visible 12-column grid, live scoreboard hero (real ballast_muse generations), rule radar and genome lattice replace the helix, tick-scaled curve with magenta gate bug and barber-pole drift band, ledger led by proof figures, journey lattice with 12-month backtest row (min cash months, drawdown, forced sales) and learn/reject markers from the real journey runtime.
- 2026-11-07: v3.2. Lessons ledger, client journeys, coverage map, live on ballast_muse.
- 2026-11-07: v3.1. SubQ Snap decision gates.
- 2026-11-07: v3. Genome helix, OKLCH tokens, business copy.
