"use client";

import { CheckCircle2, Clock, AlertCircle, Loader2 } from "lucide-react";

const STYLES: Record<string, string> = {
  COMPLETED: "bg-emerald-50 border-emerald-200 text-emerald-700",
  RUNNING: "bg-blue-50 border-blue-200 text-blue-700",
  QUEUED: "bg-amber-50 border-amber-200 text-amber-700",
  RETRYING: "bg-orange-50 border-orange-200 text-orange-700",
  FAILED: "bg-red-50 border-red-200 text-red-700",
  CANCELLED: "bg-red-50 border-red-200 text-red-700",
};

export function StatusChip({ status }: { status: string }) {
  const Icon =
    status === "COMPLETED"
      ? CheckCircle2
      : status === "RUNNING"
        ? Loader2
        : status === "QUEUED" || status === "RETRYING"
          ? Clock
          : AlertCircle;
  const spinning = status === "RUNNING" ? " animate-spin" : "";
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full border ${
        STYLES[status] ?? "bg-gray-50 border-gray-200 text-gray-600"
      }`}
    >
      <Icon className={`w-3 h-3${spinning}`} />
      {status === "RETRYING" ? "RETRYING" : status}
    </span>
  );
}
