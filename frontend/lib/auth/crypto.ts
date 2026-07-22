import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { requireServerEnv } from "@/lib/env/server";

function key(secretName: "SESSION_SECRET" | "OIDC_SESSION_ENCRYPTION_KEY") {
  const configured = process.env[secretName] ?? (
    process.env.NODE_ENV === "production"
      ? requireServerEnv(secretName)
      : "local-development-session-secret-not-for-production"
  );
  if (configured.length < 32) throw new Error(`${secretName} must be at least 32 characters`);
  return createHash("sha256").update(configured).digest();
}

export function seal(value: object, secretName: "SESSION_SECRET" | "OIDC_SESSION_ENCRYPTION_KEY") {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key(secretName), iv);
  const ciphertext = Buffer.concat([cipher.update(JSON.stringify(value), "utf8"), cipher.final()]);
  return [iv, cipher.getAuthTag(), ciphertext].map((part) => part.toString("base64url")).join(".");
}

export function unseal<T>(
  value: string | undefined,
  secretName: "SESSION_SECRET" | "OIDC_SESSION_ENCRYPTION_KEY",
): T | null {
  if (!value) return null;
  try {
    const [ivValue, tagValue, ciphertextValue] = value.split(".");
    if (!ivValue || !tagValue || !ciphertextValue) return null;
    const decipher = createDecipheriv(
      "aes-256-gcm",
      key(secretName),
      Buffer.from(ivValue, "base64url"),
    );
    decipher.setAuthTag(Buffer.from(tagValue, "base64url"));
    const plaintext = Buffer.concat([
      decipher.update(Buffer.from(ciphertextValue, "base64url")),
      decipher.final(),
    ]).toString("utf8");
    return JSON.parse(plaintext) as T;
  } catch {
    return null;
  }
}
