"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Zap,
  LogOut,
  UserRound,
  ChevronDown,
  Menu,
  X,
  LayoutDashboard,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

const SIGNED_OUT_LINKS = [
  { href: "/", label: "Home" },
  { href: "/denoise", label: "Use Denoise" },
  { href: "/about", label: "About" },
  { href: "/feedback", label: "Feedback" },
];

const SIGNED_IN_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/denoise", label: "Use Denoise" },
  { href: "/gallery", label: "Gallery" },
  { href: "/status", label: "Status" },
  { href: "/about", label: "About" },
  { href: "/feedback", label: "Feedback" },
];

const USER_MENU_LINKS = [
  { href: "/profile", label: "Profile" },
  { href: "/settings", label: "Settings" },
];

function navId(label: string): string {
  return `nav-${label.toLowerCase().replace(/\s+/g, "-")}`;
}

function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export default function Navbar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement | null>(null);

  const navLinks = user ? SIGNED_IN_LINKS : SIGNED_OUT_LINKS;

  useEffect(() => {
    if (!userMenuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setUserMenuOpen(false);
    };
    const onClick = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [userMenuOpen]);

  const handleSignOut = () => {
    setUserMenuOpen(false);
    setMobileOpen(false);
    void signOut();
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-white/70 backdrop-blur-xl border-b border-[oklch(0.91_0.015_285)]">
      <nav className="max-w-7xl mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link id="nav-logo" href="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg btn-purple flex items-center justify-center transition-transform group-hover:scale-110 shadow-lg shadow-emerald-500/20">
            <Zap className="w-4 h-4 text-white" strokeWidth={2.5} />
          </div>
          <span className="font-bold text-xl tracking-tight text-[oklch(0.14_0.02_275)]">
            Denoise<span className="text-gradient"> X</span>
          </span>
        </Link>

        {/* Desktop links */}
        <div className="hidden lg:flex items-center gap-7">
          {navLinks.map((link) => {
            const active = isActive(link.href, pathname);
            return (
              <Link
                key={link.href}
                id={navId(link.label)}
                href={link.href}
                onClick={() => setUserMenuOpen(false)}
                className={`text-sm font-medium transition-all relative py-1 ${
                  active
                    ? "text-[oklch(0.52_0.22_155)]"
                    : "text-[oklch(0.45_0.05_280)] hover:text-[oklch(0.52_0.22_155)]"
                }`}
              >
                {link.label}
                {active && (
                  <span className="absolute bottom-0 left-0 w-full h-0.5 bg-[oklch(0.52_0.22_155)] rounded-full" />
                )}
              </Link>
            );
          })}
        </div>

        {/* Desktop actions */}
        <div className="hidden lg:flex items-center gap-4">
          {user ? (
            <div className="relative" ref={userMenuRef}>
              <button
                id="nav-user-menu"
                onClick={() => setUserMenuOpen((v) => !v)}
                aria-expanded={userMenuOpen}
                aria-haspopup="menu"
                className="flex items-center gap-1.5 text-sm font-medium text-[oklch(0.45_0.05_280)] hover:text-[oklch(0.52_0.22_155)] transition-colors rounded-full px-3 py-1.5 hover:bg-[oklch(0.94_0.05_155)]"
              >
                <UserRound className="w-4 h-4 text-[oklch(0.52_0.22_155)]" />
                <span className="max-w-[12rem] truncate">{user.name || user.email}</span>
                <ChevronDown className={`w-4 h-4 transition-transform ${userMenuOpen ? "rotate-180" : ""}`} />
              </button>

              {userMenuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 top-full mt-2 w-56 rounded-xl border border-[oklch(0.91_0.015_285)] bg-white shadow-xl p-1.5 z-50"
                >
                  <div className="px-3 py-2 border-b border-[oklch(0.91_0.015_285)] mb-1">
                    <p className="text-sm font-semibold text-[oklch(0.14_0.02_275)] truncate">
                      {user.name || "Signed in"}
                    </p>
                    <p className="text-xs text-[oklch(0.55_0.04_280)] truncate">{user.email}</p>
                  </div>
                  {USER_MENU_LINKS.map((link) => (
                    <Link
                      key={link.href}
                      id={`nav-${link.label.toLowerCase()}`}
                      href={link.href}
                      role="menuitem"
                      onClick={() => setUserMenuOpen(false)}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-[oklch(0.45_0.05_280)] hover:bg-[oklch(0.96_0.01_285)] hover:text-[oklch(0.52_0.22_155)] transition-colors"
                    >
                      {link.label}
                    </Link>
                  ))}
                  <button
                    id="nav-signout"
                    onClick={handleSignOut}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold text-[oklch(0.44_0.22_155)] hover:bg-red-50 transition-colors"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign Out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              <Link href="/signin">
                <Button id="nav-signin" variant="ghost" className="rounded-full font-semibold text-[oklch(0.44_0.22_155)]">
                  Sign In
                </Button>
              </Link>
              <Link href="/denoise">
                <Button id="nav-cta" className="btn-purple rounded-full px-6 font-semibold">
                  Get Started
                </Button>
              </Link>
            </>
          )}
        </div>

        {/* Mobile toggle */}
        <button
          id="nav-mobile-toggle"
          onClick={() => setMobileOpen((v) => !v)}
          aria-label="Toggle navigation menu"
          aria-expanded={mobileOpen}
          className="lg:hidden w-10 h-10 rounded-xl flex items-center justify-center text-[oklch(0.45_0.05_280)] hover:bg-[oklch(0.96_0.01_285)] transition-colors"
        >
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </nav>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="lg:hidden border-t border-[oklch(0.91_0.015_285)] bg-white/95 backdrop-blur-xl">
          <div className="max-w-7xl mx-auto px-6 py-4 flex flex-col gap-1">
            {user && (
              <div className="flex items-center gap-2.5 px-3 py-2.5 mb-1 rounded-xl bg-[oklch(0.97_0.01_285)]">
                <div className="w-9 h-9 rounded-lg btn-purple flex items-center justify-center flex-shrink-0">
                  <UserRound className="w-4 h-4 text-white" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-[oklch(0.14_0.02_275)] truncate">
                    {user.name || "Signed in"}
                  </p>
                  <p className="text-xs text-[oklch(0.55_0.04_280)] truncate">{user.email}</p>
                </div>
              </div>
            )}
            {navLinks.map((link) => {
              const active = isActive(link.href, pathname);
              return (
                <Link
                  key={link.href}
                  id={navId(link.label)}
                  href={link.href}
                  onClick={() => setMobileOpen(false)}
                  className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                    active
                      ? "bg-[oklch(0.94_0.05_155)] text-[oklch(0.44_0.22_155)]"
                      : "text-[oklch(0.45_0.05_280)] hover:bg-[oklch(0.96_0.01_285)]"
                  }`}
                >
                  {link.href === "/dashboard" && <LayoutDashboard className="w-4 h-4" />}
                  {link.label}
                </Link>
              );
            })}
            {user ? (
              <>
                {USER_MENU_LINKS.map((link) => (
                  <Link
                    key={link.href}
                    id={`nav-${link.label.toLowerCase()}`}
                    href={link.href}
                    onClick={() => setMobileOpen(false)}
                    className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium text-[oklch(0.45_0.05_280)] hover:bg-[oklch(0.96_0.01_285)] transition-colors"
                  >
                    {link.label}
                  </Link>
                ))}
                <button
                  id="nav-signout"
                  onClick={handleSignOut}
                  className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-semibold text-[oklch(0.44_0.22_155)] hover:bg-red-50 transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                  Sign Out
                </button>
              </>
            ) : (
              <>
                <div className="h-px bg-[oklch(0.91_0.015_285)] my-1" />
                <Link href="/signin" className="block">
                  <Button id="nav-signin" variant="outline" className="w-full rounded-xl font-semibold">
                    Sign In
                  </Button>
                </Link>
                <Link href="/denoise" className="block">
                  <Button id="nav-cta" className="btn-purple w-full rounded-xl font-semibold">
                    Get Started
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
