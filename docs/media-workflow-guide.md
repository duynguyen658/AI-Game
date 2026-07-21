# Media Workflow Guide

Image requests create a media audit row and typed job. The worker invokes Mock or the configured OpenAI adapter outside a database transaction, checks output presence, MIME signature, dimensions, provider flags, cost, and storage URI, then marks the asset `READY_FOR_REVIEW`.

A reviewer, manager, or admin must approve or reject the immutable result. Approval emits an outbox event but never publishes externally. Storyboards follow the same review boundary. Real video generation remains disabled and is not implemented as a publishing path.
