# Prompt Management Guide

A prompt template is a stable business task; a prompt version is immutable content. Create a template, add a `DRAFT` version, submit it to `TESTING`, approve it as a human manager/admin, then activate it. Activation retires the prior active version while holding the template lock. Rollback reactivates an approved or retired historical version.

Rendering rejects missing and unknown variables, secrets, oversized prompts, and private-reasoning requests. Runtime resolution uses database IDs and never accepts a file path. Experiments compare control and candidate metrics but do not promote the winner; activation remains a separate human decision.
