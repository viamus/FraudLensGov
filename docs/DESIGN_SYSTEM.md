# FraudLensGov Design System

FraudLensGov uses a local CSS design system inspired by government and Material 3 patterns without adding frontend runtime dependencies.

## References

- GOV.BR Design System: https://www.gov.br/ds/
- Material 3 get started: https://m3.material.io/get-started
- Material 3 design tokens: https://m3.material.io/foundations/design-tokens/overview
- Material 3 color roles: https://m3.material.io/styles/color/roles
- Material 3 typography: https://m3.material.io/styles/typography/overview
- Material 3 navigation drawer: https://m3.material.io/components/navigation-drawer/overview
- U.S. Web Design System color guidance: https://designsystem.digital.gov/design-tokens/color/overview/
- GOV.UK colour guidance: https://design-system.service.gov.uk/styles/colour/

## Product Posture

This is an audit console, not a marketing surface. The interface should be dense, quiet, table-first, and easy to scan under pressure. Pages must teach the user what they are seeing with short labels, restrained copy, and one primary task per route.

## Token Rules

- Use `--md-sys-color-*` variables for color decisions.
- Map legacy aliases such as `--surface`, `--ink`, and `--line` to Material 3 tokens only for compatibility.
- Keep surfaces neutral and let risk state colors appear only where they carry meaning.
- Use dark neutral surfaces first. Blue, amber, green, and red are functional state colors, not decoration.
- Keep panel/card radius at `8px` or lower for corporate density.
- Use type roles by function: headline for page title, title for panels, body for table content, label for metadata and badges.

## Component Rules

- Navigation drawer uses an active container, not a left accent stripe.
- Buttons include icons when they represent commands.
- Filters use outlined fields with visible focus state.
- Tables remain the primary investigative surface.
- Pagination controls must preserve filter query strings and stay visually attached to the table.
- A page should expose one primary data table. Split secondary tables into sibling routes instead of stacking unrelated investigations.
- Operational ingestion tables must show source, status, read/write volume, parameters, time window, and error state.
