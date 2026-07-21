# Provider Integration Guide

The registry exposes normalized capabilities and clients for Mock, OpenAI, Gemini, and Anthropic. Adapters normalize text, structured output, tool calls, usage, timeout, rate-limit, unavailable, rejected, and malformed-response behavior. Provider response objects never leave adapters.

Provider URLs are fixed in code. Fallback is empty by default and only follows an explicitly configured bounded chain for timeout, rate-limit, or unavailable errors. Validation and policy errors never fall back. CI uses Mock and HTTP fixtures only.
