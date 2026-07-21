import { readFile } from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";

const spec = new URL("../../openapi.m8.json", import.meta.url);
const generated = new URL("../generated/openapi.ts", import.meta.url);
const expected = astToString(await openapiTS(spec));
const current = await readFile(generated, "utf8");

const normalize = (value) => value
  .replaceAll("\r\n", "\n")
  .replace(/^\/\*\*[\s\S]*?Do not make direct changes to the file\.\n \*\/\n+/, "")
  .trim();

if (normalize(current) !== normalize(expected)) {
  console.error("Generated OpenAPI types are stale. Run pnpm openapi:generate.");
  process.exitCode = 1;
} else {
  console.log("Generated OpenAPI types match openapi.m8.json.");
}
