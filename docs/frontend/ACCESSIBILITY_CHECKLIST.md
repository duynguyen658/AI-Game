# Accessibility Checklist

- Keyboard access for navigation, dialogs, forms, tables, and decisions.
- Visible focus indicators and a skip link to the workspace content.
- Semantic page headings, labels, fieldsets, tables, and dialog titles.
- Status meaning expressed with icon and text, never color alone.
- Error summaries use `role=alert`; async job state uses a live region.
- Icon-only controls have accessible names and unfamiliar actions have text or tooltips.
- Charts include a text description and an equivalent data table.
- Touch targets retain at least 40px height on compact mobile layouts.
- Reduced-motion preferences disable nonessential transitions.
- Desktop, tablet, and mobile layouts are checked for overflow and overlap.
- Playwright runs an axe critical/serious smoke; color contrast also receives manual visual review.

This checklist describes the implemented target and review procedure. It is not a claim of formal WCAG certification.
