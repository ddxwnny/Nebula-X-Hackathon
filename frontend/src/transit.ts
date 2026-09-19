import type { RouteLeg } from "./types";

// Colour families follow LTA's system map. Codes/text remain visible independently of colour.
export const lines = [
  { code: "NS", name: "North South", color: "#d42e35" },
  { code: "EW", name: "East West", color: "#00843d" },
  { code: "NE", name: "North East", color: "#913c9e" },
  { code: "CC", name: "Circle", color: "#fa9e0d" },
  { code: "DT", name: "Downtown", color: "#005ec4" },
  { code: "TE", name: "Thomson East Coast", color: "#9d5b25" },
];
export function lineInfo(name = "") {
  const normalized = name.toUpperCase().replace(/[^A-Z0-9]/g, "");
  return (
    lines.find(
      (line) =>
        normalized.startsWith(line.code) ||
        normalized.includes(line.name.toUpperCase().replace(/ /g, "")),
    ) ?? (normalized.startsWith("CG") ? lines[1] : undefined)
  );
}
export function legColor(leg: RouteLeg) {
  return leg.mode.toLowerCase() === "walk"
    ? "#778092"
    : leg.mode.toLowerCase() === "bus"
      ? "#286a61"
      : (lineInfo(leg.line_name ?? leg.line)?.color ?? "#566177");
}
export function legLabel(leg: RouteLeg) {
  const name = leg.line_name ?? leg.line;
  if (leg.mode.toLowerCase() === "walk") return "Walk";
  if (leg.mode.toLowerCase() === "bus")
    return name ? `Bus ${name.replace(/^bus\s*/i, "")}` : "Bus";
  const line = lineInfo(name);
  return line
    ? `${line.code} · ${line.name} Line`
    : (name ?? leg.mode.toUpperCase());
}
export const minutes = (value: number) => `${Math.ceil(value)} min`;
export const clockTime = (value: Date | string) =>
  new Date(value).toLocaleTimeString("en-SG", {
    timeZone: "Asia/Singapore",
    hour: "2-digit",
    minute: "2-digit",
  });
export function singaporeNow() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Singapore",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date());
  const get = (type: string) => parts.find((p) => p.type === type)?.value;
  return {
    date: `${get("year")}-${get("month")}-${get("day")}`,
    time: `${get("hour")}:${get("minute")}`,
  };
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(
    `${import.meta.env.VITE_API_URL ?? ""}/api/v1${path}`,
    { ...init, signal: init.signal ?? AbortSignal.timeout(25000) },
  );
  if (!response.ok)
    throw new Error(
      response.status === 503
        ? "Journey information is temporarily unavailable. Please try again shortly."
        : response.status === 404
          ? "No matching journey was found. Check the locations and try again."
          : "We couldn’t complete this request. Please try again.",
    );
  return response.json();
}
export const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
