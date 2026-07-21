# Document Processing Guide

M7 accepts PDF, DOCX, and UTF-8 TXT. Extension, MIME, and signature must agree. PDF page counts are bounded; DOCX archives are checked for unsafe expansion, excessive entries, and macros. No attachment execution, external link fetching, or OCR occurs.

Extraction and coarse classification are deterministic. Embedded instructions are treated as untrusted text and flagged. The provider summarizes a sanitized excerpt; missing sections, risks, questions, and action-item candidates remain structured fields.
