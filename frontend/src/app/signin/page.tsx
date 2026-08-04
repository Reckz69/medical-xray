"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Zap, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";

type Mode = "signin" | "register";

const inputClass =
  "w-full h-11 rounded-xl border border-[oklch(0.91_0.015_285)] bg-white px-4 text-sm text-[oklch(0.14_0.02_275)] placeholder:text-[oklch(0.55_0.04_280)] outline-none transition-colors focus:border-[oklch(0.52_0.22_155)] focus:ring-2 focus:ring-[oklch(0.52_0.22_155)/0.2]";

function Field({
  id,
  label,
  type = "text",
  value,
  onChange,
  placeholder,
  autoComplete,
  required = true,
}: {
  id: string;
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoComplete?: string;
  required?: boolean;
}) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-[oklch(0.55_0.04_280)]">
        {label}
      </span>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        required={required}
        className={inputClass}
      />
    </label>
  );
}

export default function SignInPage() {
  const router = useRouter();
  const { signIn, signUp } = useAuth();

  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organization, setOrganization] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const switchMode = (next: Mode) => {
    setMode(next);
    setError("");
    setSuccess("");
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setSubmitting(true);
    try {
      const current =
        mode === "signin"
          ? await signIn(email.trim(), password)
          : await signUp(name.trim(), email.trim(), password, organization.trim() || undefined);
      setSuccess(`Welcome${current.name ? `, ${current.name}` : ""}! Redirecting…`);
      window.setTimeout(() => router.push("/denoise"), 600);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[oklch(0.98_0.005_285)] orb-bg flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-md">
        <div className="glass-card rounded-2xl p-8 shadow-sm border border-[oklch(0.91_0.015_285)]">
          <div className="flex flex-col items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-2xl btn-purple flex items-center justify-center">
              <Zap className="w-6 h-6 text-white" strokeWidth={2.5} />
            </div>
            <h1 className="text-2xl font-extrabold text-[oklch(0.14_0.02_275)]">
              {mode === "signin" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="text-sm text-[oklch(0.55_0.04_280)] text-center">
              {mode === "signin"
                ? "Sign in to upload X-rays and access your results."
                : "Create an account to start denoising chest X-rays."}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {mode === "register" && (
              <Field
                id="name"
                label="Full Name"
                value={name}
                onChange={setName}
                placeholder="Dr. Jane Doe"
                autoComplete="name"
              />
            )}

            <Field
              id="email"
              label="Email"
              type="email"
              value={email}
              onChange={setEmail}
              placeholder="you@hospital.org"
              autoComplete="email"
            />

            <Field
              id="password"
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              placeholder={mode === "register" ? "At least 8 characters" : "Your password"}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
            />

            {mode === "register" && (
              <Field
                id="organization"
                label="Organization (optional)"
                value={organization}
                onChange={setOrganization}
                placeholder="City General Hospital"
                autoComplete="organization"
                required={false}
              />
            )}

            {error && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-3 flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}

            {success && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 flex items-start gap-2.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-emerald-700">{success}</p>
              </div>
            )}

            <Button
              id={mode === "signin" ? "signin-submit" : "register-submit"}
              type="submit"
              disabled={submitting}
              className="btn-purple w-full h-12 rounded-xl text-base font-bold gap-2 shadow-lg shadow-purple-500/20"
            >
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              {submitting
                ? "Please wait…"
                : mode === "signin"
                  ? "Sign In"
                  : "Create Account"}
            </Button>
          </form>
        </div>

        <div className="mt-6 text-center">
          {mode === "signin" ? (
            <p className="text-sm text-[oklch(0.55_0.04_280)]">
              New here?{" "}
              <button
                id="show-register"
                onClick={() => switchMode("register")}
                className="font-semibold text-[oklch(0.44_0.22_155)] hover:text-[oklch(0.36_0.20_155)] transition-colors"
              >
                Create an account
              </button>
            </p>
          ) : (
            <p className="text-sm text-[oklch(0.55_0.04_280)]">
              Already have an account?{" "}
              <button
                id="show-signin"
                onClick={() => switchMode("signin")}
                className="font-semibold text-[oklch(0.44_0.22_155)] hover:text-[oklch(0.36_0.20_155)] transition-colors"
              >
                Sign in
              </button>
            </p>
          )}
        </div>

        <p className="mt-4 text-xs text-[oklch(0.55_0.04_280)] text-center">
          By continuing you agree to our{" "}
          <Link href="/about" className="underline underline-offset-2">
            terms
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
