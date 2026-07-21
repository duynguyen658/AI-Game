# Design System

## Foundation

- Framework: Next.js App Router with strict TypeScript.
- Components: owned shadcn-style primitives backed by Radix UI.
- Icons: Lucide, required by the project implementation guidance.
- Theme: light operational workspace with a dark graphite navigation rail.
- Accent: signal cyan `#087E8B`; accent never substitutes semantic status color.

## Tokens

- Type: Geist Sans for interface copy and Geist Mono for IDs and technical values.
- Body size: 14px at dense desktop surfaces, 16px for long-form result text.
- Spacing: 4px base with 8, 12, 16, 24, and 32px primary intervals.
- Radius: 6px controls and 8px cards/dialogs; no oversized capsules.
- Border: neutral gray, one pixel; separators group dense regions.
- Elevation: reserved for navigation overlays, dialogs, and menus.
- Motion: 120-180ms opacity or transform feedback; disabled for reduced motion.

## Data surfaces

Tables use 40px rows, visible headers, horizontal overflow, and labeled row actions.
Forms use compact vertical groups and visible descriptions. Charts use cyan, green,
amber, red, and neutral tokens with text summaries and tabular fallback. Statuses use
icon, label, and color together.

## Responsive behavior

- Large desktop: persistent 248px sidebar and full analytical layouts.
- Laptop: compact 220px sidebar and reduced secondary columns.
- Tablet: navigation drawer, two-column forms, scrollable dense tables.
- Mobile: summary, approvals, alerts, task result, and feedback are prioritized.

Focus rings are always visible. Dialogs trap focus. Async changes use live regions.
The design targets WCAG 2.1 AA behavior without claiming certification.
