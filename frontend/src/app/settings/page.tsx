"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { useTheme } from "next-themes";
import { Loader2, RotateCcw, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import {
  AppSettings,
  DEFAULT_SETTINGS,
  POLL_INTERVAL_MAX,
  POLL_INTERVAL_MIN,
  getSettings,
  saveSettings,
  type GridDensity,
  type ThemePref,
} from "@/lib/settings";

function RadioGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; description?: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-semibold text-[oklch(0.14_0.02_275)] mb-1">{label}</legend>
      {options.map((opt) => (
        <label
          key={opt.value}
          className={`flex items-center gap-3 px-4 py-3 rounded-xl border cursor-pointer transition-colors ${
            value === opt.value
              ? "border-[oklch(0.52_0.22_155)] bg-[oklch(0.94_0.05_155)]"
              : "border-[oklch(0.91_0.015_285)] bg-white hover:bg-[oklch(0.97_0.01_285)]"
          }`}
        >
          <input
            type="radio"
            name={label}
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
            className="accent-[oklch(0.52_0.22_155)]"
          />
          <span className="flex flex-col">
            <span className="text-sm font-medium text-[oklch(0.14_0.02_275)]">{opt.label}</span>
            {opt.description && (
              <span className="text-xs text-[oklch(0.55_0.04_280)]">{opt.description}</span>
            )}
          </span>
        </label>
      ))}
    </fieldset>
  );
}

export default function SettingsPage() {
  const { user, loading: authLoading } = useAuth();
  const { theme, setTheme } = useTheme();
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => {
      setSettings(getSettings());
      setLoaded(true);
    }, 0);
    return () => window.clearTimeout(t);
  }, []);

  if (authLoading) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-[oklch(0.98_0.005_285)] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[oklch(0.52_0.22_155)] animate-spin" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-[oklch(0.98_0.005_285)] orb-bg flex items-center justify-center px-6">
        <div className="glass-card rounded-2xl p-10 max-w-md text-center shadow-sm border border-[oklch(0.91_0.015_285)]">
          <div className="w-12 h-12 rounded-2xl btn-purple flex items-center justify-center mx-auto mb-4">
            <Settings2 className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
            Sign in to manage your <span className="text-gradient">settings</span>
          </h1>
          <Link href="/signin" className="inline-block">
            <Button id="go-signin" className="btn-purple rounded-xl px-8 h-11 font-bold">
              Sign In / Create Account
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  if (!loaded) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-[oklch(0.98_0.005_285)] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[oklch(0.52_0.22_155)] animate-spin" />
      </div>
    );
  }

  const update = (next: AppSettings) => {
    setSettings(next);
    saveSettings(next);
  };

  const setPollInterval = (value: number) => {
    const clamped = Math.min(POLL_INTERVAL_MAX, Math.max(POLL_INTERVAL_MIN, Math.round(value)));
    update({ ...settings, pollIntervalSeconds: clamped });
    toast.success(`Live updates every ${clamped}s`);
  };

  const setDensity = (value: GridDensity) => {
    update({ ...settings, gridDensity: value });
    toast.success(value === "compact" ? "Compact grid enabled" : "Comfortable grid enabled");
  };

  const setThemePref = (value: ThemePref) => {
    update({ ...settings, theme: value });
    setTheme(value);
    toast.success(`Theme set to ${value}`);
  };

  const reset = () => {
    setSettings(DEFAULT_SETTINGS);
    saveSettings(DEFAULT_SETTINGS);
    setTheme(DEFAULT_SETTINGS.theme);
    toast.success("Settings restored to defaults");
  };

  return (
    <div className="min-h-screen bg-[oklch(0.98_0.005_285)] orb-bg pb-20">
      <div className="max-w-2xl mx-auto px-6 md:px-12 py-12 flex flex-col gap-8">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-3">
              <div className="pill-badge">
                <Settings2 className="w-3 h-3" />
                Preferences
              </div>
            </div>
            <h1 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
              <span className="text-gradient">Settings</span>
            </h1>
            <p className="text-[oklch(0.45_0.05_280)]">
              Stored in your browser and applied across the app.
            </p>
          </div>
          <Button id="settings-reset" variant="outline" onClick={reset} className="rounded-xl font-semibold">
            <RotateCcw className="w-4 h-4" />
            Reset defaults
          </Button>
        </div>

        <div className="glass-card rounded-2xl p-6 border border-[oklch(0.91_0.015_285)] shadow-sm">
          <h2 className="font-bold text-[oklch(0.14_0.02_275)] mb-4">Live Updates</h2>
          <label className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-[oklch(0.14_0.02_275)]">Poll interval</span>
              <span className="text-xs text-[oklch(0.55_0.04_280)] tabular-nums">
                {settings.pollIntervalSeconds}s
              </span>
            </div>
            <input
              id="settings-poll-interval"
              type="range"
              min={POLL_INTERVAL_MIN}
              max={POLL_INTERVAL_MAX}
              step={1}
              value={settings.pollIntervalSeconds}
              onChange={(e) => setPollInterval(Number(e.target.value))}
              className="accent-[oklch(0.52_0.22_155)] w-full"
            />
            <span className="text-xs text-[oklch(0.55_0.04_280)]">
              How often the dashboard, gallery, and status pages refresh.
            </span>
          </label>
        </div>

        <div className="glass-card rounded-2xl p-6 border border-[oklch(0.91_0.015_285)] shadow-sm">
          <RadioGroup
            label="Gallery grid density"
            value={settings.gridDensity}
            onChange={setDensity}
            options={[
              { value: "comfortable", label: "Comfortable", description: "Spacious cards, one per row" },
              { value: "compact", label: "Compact", description: "Denser cards, more on screen" },
            ]}
          />
        </div>

        <div className="glass-card rounded-2xl p-6 border border-[oklch(0.91_0.015_285)] shadow-sm">
          <RadioGroup
            label="Theme"
            value={(theme ?? "system") as ThemePref}
            onChange={setThemePref}
            options={[
              { value: "system", label: "System", description: "Follow your device" },
              { value: "light", label: "Light", description: "Always light" },
              { value: "dark", label: "Dark", description: "Always dark" },
            ]}
          />
        </div>
      </div>
    </div>
  );
}
