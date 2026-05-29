# FraudLensGov Design System

FraudLensGov uses a Material 3 inspired system without adding frontend runtime dependencies.

## References

- Material 3 get started: https://m3.material.io/get-started
- Material 3 design tokens: https://m3.material.io/foundations/design-tokens/overview
- Material 3 color roles: https://m3.material.io/styles/color/roles
- Material 3 typography: https://m3.material.io/styles/typography/overview
- Material 3 navigation drawer: https://m3.material.io/components/navigation-drawer/overview

## Product Posture

This is an audit console, not a marketing surface. The interface should be dense, quiet, table-first, and easy to scan under pressure.

## Token Rules

- Use `--md-sys-color-*` variables for color decisions.
- Map legacy aliases such as `--surface`, `--ink`, and `--line` to Material 3 tokens only for compatibility.
- Keep surfaces neutral and let risk state colors appear only where they carry meaning.
- Keep panel/card radius at `8px` or lower for corporate density.
- Use type roles by function: headline for page title, title for panels, body for table content, label for metadata and badges.

## Component Rules

- Navigation drawer uses an active container, not a left accent stripe.
- Buttons include icons when they represent commands.
- Filters use outlined fields with visible focus state.
- Tables remain the primary investigative surface.
- Pagination controls must preserve filter query strings and stay visually attached to the table.
