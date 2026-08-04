"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Zap, LogOut, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

const BASE_NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/denoise", label: "Use Denoise" },
  { href: "/about", label: "About" },
  { href: "/feedback", label: "Feedback" },
];

export default function Navbar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();

  const navLinks = user
    ? [
        { href: "/", label: "Home" },
        { href: "/denoise", label: "Use Denoise" },
        { href: "/gallery", label: "Gallery" },
        { href: "/about", label: "About" },
        { href: "/feedback", label: "Feedback" },
      ]
    : BASE_NAV_LINKS;

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

        {/* Links */}
        <div className="hidden md:flex items-center gap-8">
          {navLinks.map((link) => {
            const isActive = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                id={`nav-${link.label.toLowerCase().replace(/\s+/g, "-")}`}
                href={link.href}
                className={`text-sm font-medium transition-all relative py-1 ${
                  isActive
                    ? "text-[oklch(0.52_0.22_155)]"
                    : "text-[oklch(0.45_0.05_280)] hover:text-[oklch(0.52_0.22_155)]"
                }`}
              >
                {link.label}
                {isActive && (
                  <span className="absolute bottom-0 left-0 w-full h-0.5 bg-[oklch(0.52_0.22_155)] rounded-full" />
                )}
              </Link>
            );
          })}
        </div>

        {/* Action */}
        <div className="flex items-center gap-4">
          {user ? (
            <>
              <span className="hidden sm:inline-flex items-center gap-1.5 text-sm font-medium text-[oklch(0.45_0.05_280)]">
                <UserRound className="w-4 h-4 text-[oklch(0.52_0.22_155)]" />
                {user.name || user.email}
              </span>
              <Button
                id="nav-signout"
                variant="ghost"
                onClick={() => void signOut()}
                className="rounded-full font-semibold text-[oklch(0.44_0.22_155)]"
              >
                <LogOut className="w-4 h-4" />
                Sign Out
              </Button>
            </>
          ) : (
            <>
              <Link href="/signin">
                <Button id="nav-signin" variant="ghost" className="rounded-full font-semibold text-[oklch(0.44_0.22_155)]">
                  Sign In
                </Button>
              </Link>
              <Link href="/denoise" className="hidden sm:block">
                <Button id="nav-cta" className="btn-purple rounded-full px-6 font-semibold">
                  Get Started
                </Button>
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
