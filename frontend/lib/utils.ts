import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function compactId(value: string | null | undefined, size = 8) {
  if (!value) return "Not available";
  return value.length <= size ? value : `${value.slice(0, size)}...`;
}
