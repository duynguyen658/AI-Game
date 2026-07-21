# Prompt Management Guide

A prompt template is a stable business task; a prompt version is immutable content. Create a template, add a `DRAFT` version, submit it to `TESTING`, approve it as a human manager/admin, then activate it. Activation retires the prior active version while holding the template lock. Activation and rollback require the latest `expected_template_version`; a successful change increments that version so concurrent stale requests receive `409`. Rollback reactivates an approved or retired historical version.

Rendering rejects missing and unknown variables, secrets, oversized prompts, and private-reasoning requests. Runtime resolution uses database IDs and never accepts a file path. Data analysis, document processing, image generation, and video storyboards resolve an active version when the task is created and retain that exact version/hash through execution.

Experiments accept only template/version IDs, dataset, provider/model, sample size, and deterministic settings. `PROMPT_EXPERIMENT_RUN` executes both variants on identical cases and calculates output quality, schema validity, success/failure, review/revision, latency, token, cost, tool-call, and action-proposal metrics server-side. Results never promote a version; activation remains a separate human decision.
