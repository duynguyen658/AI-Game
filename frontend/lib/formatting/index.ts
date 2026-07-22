export function formatDate(value: string | null | undefined, withTime = true) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    ...(withTime ? { timeStyle: "short" as const } : {}),
  }).format(date);
}

export function formatNumber(value: string | number | null | undefined, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Unknown";
  return new Intl.NumberFormat("en", { maximumFractionDigits: digits }).format(number);
}

export function formatPercent(value: string | number | null | undefined) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Unknown";
  return new Intl.NumberFormat("en", { style: "percent", maximumFractionDigits: 1 }).format(number);
}

export function formatCurrency(value: string | number | null | undefined) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Unknown";
  return new Intl.NumberFormat("en", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(number);
}
