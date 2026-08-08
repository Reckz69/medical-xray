"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, LogOut, ShieldCheck, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { ApiError, me, type User } from "@/lib/api";

export default function ProfilePage() {
  const router = useRouter();
  const { user, loading: authLoading, signOut } = useAuth();
  const [profile, setProfile] = useState<User | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    me()
      .then((data) => {
        if (!cancelled) setProfile(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load profile");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const handleSignOut = async () => {
    await signOut();
    router.replace("/");
  };

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
            <UserRound className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
            Sign in to view your <span className="text-gradient">profile</span>
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

  const data = profile ?? user;

  return (
    <div className="min-h-screen bg-[oklch(0.98_0.005_285)] orb-bg pb-20">
      <div className="max-w-2xl mx-auto px-6 md:px-12 py-12 flex flex-col gap-8">
        <div>
          <div className="flex items-center gap-3 mb-3">
            <div className="pill-badge">
              <UserRound className="w-3 h-3" />
              Account
            </div>
          </div>
          <h1 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)] mb-2">
            Your <span className="text-gradient">Profile</span>
          </h1>
          <p className="text-[oklch(0.45_0.05_280)]">Account details tied to your scans and results.</p>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
        )}

        <div className="glass-card rounded-2xl p-6 border border-[oklch(0.91_0.015_285)] shadow-sm">
          <div className="flex items-center gap-4 mb-6">
            <div className="w-14 h-14 rounded-2xl btn-purple flex items-center justify-center flex-shrink-0">
              <UserRound className="w-7 h-7 text-white" />
            </div>
            <div>
              <p className="font-bold text-lg text-[oklch(0.14_0.02_275)]">
                {data.name || "Unnamed user"}
              </p>
              <p className="text-sm text-[oklch(0.55_0.04_280)]">{data.email}</p>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            {[
              { label: "Name", value: data.name || "—" },
              { label: "Email", value: data.email },
              { label: "Role", value: data.role },
              { label: "User ID", value: data.id, mono: true },
            ].map((row) => (
              <div key={row.label} className="flex items-center justify-between px-4 py-2.5 rounded-xl bg-[oklch(0.97_0.01_285)]">
                <span className="text-sm font-medium text-[oklch(0.35_0.05_280)]">{row.label}</span>
                <span className={`text-sm font-semibold text-[oklch(0.14_0.02_275)] ${row.mono ? "font-mono text-xs" : ""}`}>
                  {row.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-emerald-800">
            Your scans and outputs are private to your account and organization.
          </p>
        </div>

        <Button id="profile-signout" onClick={() => void handleSignOut()} variant="outline" className="rounded-xl font-semibold">
          <LogOut className="w-4 h-4" />
          Sign Out
        </Button>
      </div>
    </div>
  );
}
