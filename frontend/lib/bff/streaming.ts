export class BodyLimitError extends Error {
  constructor() {
    super("Request body exceeds the configured limit");
    this.name = "BodyLimitError";
  }
}

export function parseContentLength(value: string | null): number | null {
  if (value === null) return null;
  if (!/^\d+$/.test(value)) throw new BodyLimitError();
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) throw new BodyLimitError();
  return parsed;
}

export function streamWithByteLimit(
  stream: ReadableStream<Uint8Array>,
  limit: number,
  onLimit: () => void,
) {
  const reader = stream.getReader();
  let bytes = 0;
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      const next = await reader.read();
      if (next.done) {
        controller.close();
        return;
      }
      bytes += next.value.byteLength;
      if (bytes > limit) {
        onLimit();
        await reader.cancel(new BodyLimitError());
        controller.error(new BodyLimitError());
        return;
      }
      controller.enqueue(next.value);
    },
    cancel(reason) {
      return reader.cancel(reason);
    },
  });
}

export function isBodyLimitError(error: unknown): boolean {
  let current: unknown = error;
  for (let depth = 0; depth < 4 && current; depth += 1) {
    if (current instanceof BodyLimitError) return true;
    current = typeof current === "object" && "cause" in current
      ? (current as { cause?: unknown }).cause
      : null;
  }
  return false;
}
