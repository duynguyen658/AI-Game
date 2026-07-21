# Document Processing Guide

M7 accepts PDF, DOCX, and UTF-8 TXT. Extension, MIME, and signature must agree. PDF page counts are bounded; DOCX archives are checked for unsafe expansion, excessive entries, and macros. No attachment execution, external link fetching, or OCR occurs.

Extraction and coarse classification are deterministic. Embedded instructions are treated as untrusted text and flagged. The provider summarizes a sanitized excerpt; missing sections, risks, questions, and action-item candidates remain structured fields.

The task records the active `document_processing` prompt version/hash and the worker renders only that version. Deterministic consistency checks flag conflicting dates/deadlines, repeated labels, budgets/currencies, product or campaign names, priorities, requirements, and totals. A schema-validated model-assisted pass may add objective/action, requirement, audience, claim, or dependency findings. Every finding includes severity, source locations, evidence summary, detection method, confidence, and suggested resolution; model-assisted findings are not presented as deterministic facts. Checks do not perform OCR or prove semantic correctness beyond the supplied excerpt.
