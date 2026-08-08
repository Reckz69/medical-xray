"use client";

import {
  CheckCircle2,
  Circle,
  Loader2,
  Activity,
  XCircle,
} from "lucide-react";
import type { Job, Scan } from "@/lib/api";

interface Step {
  key: string;
  label: string;
  time: string | null;
  state: "done" | "active" | "error" | "pending";
  detail?: string | null;
}

function StepRow({ step, last }: { step: Step; last: boolean }) {
  const icon =
    step.state === "done" ? (
      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
    ) : step.state === "active" ? (
      <Loader2 className="w-4 h-4 text-[oklch(0.52_0.22_155)] animate-spin" />
    ) : step.state === "error" ? (
      <XCircle className="w-4 h-4 text-red-600" />
    ) : (
      <Circle className="w-4 h-4 text-[oklch(0.78_0.04_285)]" />
    );

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className="w-6 h-6 rounded-full flex items-center justify-center bg-[oklch(0.97_0.01_285)]">
          {icon}
        </div>
        {!last && <div className="w-px flex-1 min-h-[20px] bg-[oklch(0.88_0.04_285)]" />}
      </div>
      <div className="pb-4 flex-1 min-w-0">
        <div className="flex items-center justify-between gap-3">
          <p
            className={`text-sm font-semibold ${
              step.state === "error"
                ? "text-red-700"
                : step.state === "active"
                  ? "text-[oklch(0.44_0.22_155)]"
                  : "text-[oklch(0.14_0.02_275)]"
            }`}
          >
            {step.label}
          </p>
          {step.time && (
            <span className="text-xs text-[oklch(0.55_0.04_280)] tabular-nums">{step.time}</span>
          )}
        </div>
        {step.detail && (
          <p className="text-xs text-[oklch(0.55_0.04_280)] mt-0.5 break-words">{step.detail}</p>
        )}
      </div>
    </div>
  );
}

/**
 * Renders only real lifecycle transitions for a scan, derived from the job
 * (created/started/finished, attempt counts) and the scan status. No invented
 * sub-stages.
 */
export function JobTimeline({ job, scan }: { job: Job | null; scan?: Scan | null }) {
  const created = job?.created_at ?? scan?.created_at ?? null;
  const started = job?.started_at ?? null;
  const finished = job?.finished_at ?? scan?.completed_at ?? null;
  const status = job?.status ?? (scan ? scan.status : null);

  const steps: Step[] = [];

  steps.push({ key: "uploaded", label: "Uploaded", time: created, state: "done" });

  if (status) {
    steps.push({ key: "queued", label: "Queued", time: created, state: "done" });
  }

  const workerActive = status === "RUNNING" || status === "RETRYING" || status === "COMPLETED";
  if (started && workerActive) {
    steps.push({
      key: "worker",
      label: "Worker picked up",
      time: started,
      state: "done",
      detail: job?.worker_id ? `Worker: ${job.worker_id}` : null,
    });
  }

  if (status === "QUEUED") {
    steps.push({ key: "waiting", label: "Waiting for the inference worker…", time: null, state: "active" });
  } else if (status === "RUNNING") {
    steps.push({
      key: "running",
      label: "N2N U-Net analyzing & enhancing…",
      time: started,
      state: "active",
    });
  } else if (status === "RETRYING") {
    steps.push({
      key: "retrying",
      label: `Retrying (attempt ${job?.attempt ?? "?"}/${job?.max_attempts ?? "?"})`,
      time: job?.next_retry_at ?? started,
      state: "active",
      detail: job?.error ?? null,
    });
  } else if (status === "COMPLETED") {
    steps.push({
      key: "completed",
      label: "Completed",
      time: finished,
      state: "done",
      detail:
        job?.scan_status === "COMPLETED" && scan?.processing_time_ms != null
          ? `Processed in ${scan.processing_time_ms.toFixed(0)} ms`
          : null,
    });
  } else if (status === "FAILED") {
    steps.push({
      key: "failed",
      label: "Failed",
      time: finished,
      state: "error",
      detail: job?.error ?? scan?.routing_message ?? null,
    });
  } else if (status === "CANCELLED") {
    steps.push({
      key: "cancelled",
      label: "Cancelled",
      time: finished,
      state: "error",
      detail: job?.error ?? null,
    });
  }

  if (steps.length === 0) return null;

  return (
    <div className="rounded-2xl border border-[oklch(0.91_0.015_285)] bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <Activity className="w-4 h-4 text-[oklch(0.52_0.22_155)]" />
        <h3 className="text-sm font-bold text-[oklch(0.14_0.02_275)]">Processing Timeline</h3>
      </div>
      <div>
        {steps.map((step, i) => (
          <StepRow key={step.key} step={step} last={i === steps.length - 1} />
        ))}
      </div>
      {job?.trace_id && (
        <p className="text-[11px] text-[oklch(0.55_0.04_280)] mt-1 pt-3 border-t border-[oklch(0.94_0.02_285)] break-all">
          trace_id: <code className="font-mono">{job.trace_id}</code>
        </p>
      )}
      {!job?.trace_id && scan?.content_hash && (
        <p className="text-[11px] text-[oklch(0.55_0.04_280)] mt-1 pt-3 border-t border-[oklch(0.94_0.02_285)] break-all">
          sha256: <code className="font-mono">{scan.content_hash.slice(0, 20)}…</code>
        </p>
      )}
    </div>
  );
}
