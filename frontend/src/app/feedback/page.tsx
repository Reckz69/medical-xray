"use client";

import Link from "next/link";
import {
  Bug,
  Mail,
  MessageSquareText,
  ExternalLink,
  ArrowUpRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";

const GITHUB_ISSUES_URL = "https://github.com/Reckz69/medical-xray/issues/new";
const FEEDBACK_MAILTO = "mailto:feedback@denoisex.app";

export default function FeedbackPage() {
  return (
    <div className="min-h-screen bg-[oklch(0.98_0.005_285)] orb-bg pb-20">
      <div className="max-w-4xl mx-auto px-6 md:px-12 py-12 flex flex-col gap-10">
        <div className="text-center">
          <div className="pill-badge mb-4 mx-auto w-fit">
            <MessageSquareText className="w-3 h-3" />
            Feedback
          </div>
          <h1 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)] mb-3">
            Help us improve <span className="text-gradient">Denoise X</span>
          </h1>
          <p className="text-[oklch(0.45_0.05_280)] text-lg max-w-xl mx-auto">
            Spotted a bug, or have an idea for a clinical workflow? We read
            every report.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Report an issue */}
          <div className="glass-card glass-card-hover rounded-2xl p-8 flex flex-col gap-4 border border-[oklch(0.91_0.015_285)] shadow-sm">
            <div className="feature-icon">
              <Bug className="w-6 h-6" strokeWidth={1.8} />
            </div>
            <h2 className="font-bold text-[oklch(0.14_0.02_275)] text-lg">Report an issue</h2>
            <p className="text-sm text-[oklch(0.52_0.05_280)] leading-relaxed flex-1">
              File a GitHub issue with repro steps, expected vs actual behavior,
              and any error messages or trace IDs you saw. Attach a screenshot
              if it helps.
            </p>
            <a href={GITHUB_ISSUES_URL} target="_blank" rel="noopener noreferrer">
              <Button id="feedback-github" className="btn-purple w-full rounded-xl font-semibold gap-2">
                <ExternalLink className="w-4 h-4" />
                Open GitHub Issue
                <ArrowUpRight className="w-4 h-4" />
              </Button>
            </a>
          </div>

          {/* Contact */}
          <div className="glass-card glass-card-hover rounded-2xl p-8 flex flex-col gap-4 border border-[oklch(0.91_0.015_285)] shadow-sm">
            <div className="feature-icon">
              <Mail className="w-6 h-6" strokeWidth={1.8} />
            </div>
            <h2 className="font-bold text-[oklch(0.14_0.02_275)] text-lg">Contact the team</h2>
            <p className="text-sm text-[oklch(0.52_0.05_280)] leading-relaxed flex-1">
              For feature requests, partnership inquiries, or sensitive clinical
              deployments, email us directly. We respond to every message.
            </p>
            <a href={FEEDBACK_MAILTO}>
              <Button id="feedback-mail" variant="outline" className="w-full rounded-xl font-semibold gap-2">
                <Mail className="w-4 h-4" />
                feedback@denoisex.app
                <ArrowUpRight className="w-4 h-4" />
              </Button>
            </a>
          </div>
        </div>

        <div className="rounded-xl border border-[oklch(0.88_0.09_290)] bg-[oklch(0.96_0.02_290)] p-5 flex items-start gap-3">
          <MessageSquareText className="w-5 h-5 text-[oklch(0.52_0.22_290)] flex-shrink-0 mt-0.5" />
          <p className="text-sm text-[oklch(0.45_0.05_280)] leading-relaxed">
            You can also leave feedback on the{" "}
            <Link href="/about" className="font-semibold text-[oklch(0.44_0.22_155)] hover:text-[oklch(0.36_0.20_155)] transition-colors">
              About
            </Link>{" "}
            page, or report a system issue from the{" "}
            <Link href="/status" className="font-semibold text-[oklch(0.44_0.22_155)] hover:text-[oklch(0.36_0.20_155)] transition-colors">
              Status
            </Link>{" "}
            page.
          </p>
        </div>
      </div>
    </div>
  );
}
