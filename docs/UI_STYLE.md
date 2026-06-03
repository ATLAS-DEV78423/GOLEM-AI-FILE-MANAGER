GOLEM UI Style Guide

This document describes the design tokens and recommended usage for GOLEM's UI components.

Tokens (see `golem/ui_theme.py`)
- Colors: `COLORS` (bg, fg, accent, border, state, category)
- Spacing: `SPACING` (xxs..xxxl, gutter)
- Radii: `RADII` (none, sm, DEFAULT, md, lg, pill)
- Typography: `TYPOGRAPHY` (display, title, body, caption, micro, code, kbd)
- Motion: `MOTION` (instant, fast, DEFAULT, slow, max; reduced_motion)
- Shadows: `SHADOWS` (popover, dialog, chip)
- Icon sizes: `ICON_SIZE` (micro..xl)

Principles
- Keep contrast high: use `COLORS.fg.primary` on dark surfaces.
- Prefer `ttk` components styled via `apply_theme(root)`.
- Use `PrimaryButton` for main CTAs, `SecondaryButton` for secondary actions.
- Use `make_panel()` for bordered panels, and `EmptyState` for centered empty views.
- Respect `MOTION.reduced_motion` for accessibility; wrap rapid changes in `reduced_motion()` during tests.

Quick examples
- Apply theme:

  ```py
  from golem.ui_theme import apply_theme
  apply_theme(root)
  ```

- Create a primary CTA:

  ```py
  from golem.ui_components import PrimaryButton
  btn = PrimaryButton(parent, "Do it", command=do_it)
  btn.pack()
  ```

- Use animated popover:

  ```py
  from golem.ui_anim import fade_in, slide_in
  fade_in(popover, duration_ms=180)
  slide_in(popover, duration_ms=220, from_dy=10)
  ```

Guidance for contributors
- Add tokens to `golem/ui_theme.py` rather than hardcoding colors or sizes.
- Use named ttk styles (e.g., `Primary.TButton`) for visual consistency.
- When introducing animations, use `golem/ui_anim.py` primitives and honor `MOTION.reduced_motion`.
- Write tests in `tests/` when changing component behavior; keep visual-only tweaks minimal.

Contact
- For questions about visual details, open an issue in the repo or ping the UI owner.