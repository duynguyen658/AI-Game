# Test Plan

## Unit and component

Vitest and React Testing Library cover permissions, navigation, API error mapping,
status formatting, polling termination, campaign validation, feedback invariants,
prompt lifecycle affordances, media review, file constraints, and impact semantics.
MSW covers loading, empty, validation, conflict, forbidden, rate limit, unavailable,
cancellation, partial provider failure, unknown acceptance, and media failure.

## Browser

Playwright covers demo login/logout, campaign vertical slice, experiments, provider
comparison, CSV, document, image review, storyboard, impact, and operator views. Stable
screenshots are captured for the ten prompt-required surfaces at desktop and selected
tablet/mobile sizes. Automated accessibility smoke checks keyboard focus, landmarks,
labels, dialog behavior, and major axe violations.

## Build and regression

Run lint, typecheck, unit tests, production build, generated OpenAPI drift, Playwright,
frontend Docker build/smoke, backend quality gates, migrations, full PostgreSQL tests,
dependency audit, and image security scans. No real provider calls are permitted.
