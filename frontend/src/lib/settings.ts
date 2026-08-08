"use client";

export type GridDensity = "comfortable" | "compact";
export type ThemePref = "light" | "dark" | "system";

export interface AppSettings {
  pollIntervalSeconds: number;
  gridDensity: GridDensity;
  theme: ThemePref;
}

const SETTINGS_KEY = "denoisex_settings";

export const DEFAULT_SETTINGS: AppSettings = {
  pollIntervalSeconds: 5,
  gridDensity: "comfortable",
  theme: "system",
};

export const POLL_INTERVAL_MIN = 2;
export const POLL_INTERVAL_MAX = 120;

export function getSettings(): AppSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    return {
      pollIntervalSeconds:
        typeof parsed.pollIntervalSeconds === "number" &&
        parsed.pollIntervalSeconds >= POLL_INTERVAL_MIN &&
        parsed.pollIntervalSeconds <= POLL_INTERVAL_MAX
          ? Math.round(parsed.pollIntervalSeconds)
          : DEFAULT_SETTINGS.pollIntervalSeconds,
      gridDensity: parsed.gridDensity === "compact" ? "compact" : DEFAULT_SETTINGS.gridDensity,
      theme:
        parsed.theme === "light" || parsed.theme === "dark" || parsed.theme === "system"
          ? parsed.theme
          : DEFAULT_SETTINGS.theme,
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(settings: AppSettings): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}
