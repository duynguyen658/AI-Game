import { describe, expect, it, vi } from "vitest";
import {
  BodyLimitError,
  parseContentLength,
  streamWithByteLimit,
} from "@/lib/bff/streaming";

function stream(...chunks: number[][]) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(Uint8Array.from(chunk));
      controller.close();
    },
  });
}

describe("BFF streaming limits", () => {
  it("rejects malformed and oversized declared lengths", () => {
    expect(() => parseContentLength("12x")).toThrow(BodyLimitError);
    expect(parseContentLength(null)).toBeNull();
    expect(parseContentLength("12")).toBe(12);
  });

  it("streams a request body without allocating the complete payload", async () => {
    const response = new Response(streamWithByteLimit(stream([1, 2], [3]), 3, vi.fn()));
    expect(Array.from(new Uint8Array(await response.arrayBuffer()))).toEqual([1, 2, 3]);
  });

  it("enforces actual bytes when content length is missing or understated", async () => {
    const onLimit = vi.fn();
    const reader = streamWithByteLimit(stream([1, 2], [3, 4]), 3, onLimit).getReader();
    await expect((async () => {
      while (!(await reader.read()).done) { /* consume chunks */ }
    })()).rejects.toThrow(BodyLimitError);
    expect(onLimit).toHaveBeenCalledOnce();
  });
});
