"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowLeftRight,
  Download,
  Maximize2,
  Minimize2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { getOutputUrl, OUTPUT_TYPES, type OutputUrl } from "@/lib/api";

/**
 * Before/after comparison slider for a completed scan.
 *
 * Shows the ENHANCED output with the ORIGINAL clipped on top; dragging the
 * divider reveals one side or the other. Includes zoom (fills the viewer,
 * scrollable) and fullscreen. Requires scanId; URLs may be supplied to skip
 * the presigned-URL fetches.
 */
export function ScanViewer({
  scanId,
  originalUrl,
  enhancedUrl,
  label = "AI-Enhanced Comparison",
}: {
  scanId: string;
  originalUrl?: string | null;
  enhancedUrl?: string | null;
  label?: string;
}) {
  const [original, setOriginal] = useState<string | null>(originalUrl ?? null);
  const [enhanced, setEnhanced] = useState<string | null>(enhancedUrl ?? null);
  const [error, setError] = useState<string | null>(null);
  const [percent, setPercent] = useState(50);
  const [zoomed, setZoomed] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetches: Promise<OutputUrl>[] = [];
    if (!original && !originalUrl) fetches.push(getOutputUrl(scanId, OUTPUT_TYPES.ORIGINAL));
    if (!enhanced && !enhancedUrl) fetches.push(getOutputUrl(scanId, OUTPUT_TYPES.ENHANCED));

    if (fetches.length === 0) return;
    Promise.all(fetches)
      .then((results) => {
        if (cancelled) return;
        setOriginal(results[0]?.download_url ?? null);
        setEnhanced(results[1]?.download_url ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load comparison");
      });
    return () => {
      cancelled = true;
    };
  }, [scanId, original, enhanced, originalUrl, enhancedUrl]);

  useEffect(() => {
    const onFsChange = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void rootRef.current?.requestFullscreen().catch(() => undefined);
    }
  };

  const showOriginal = !!original;
  const showEnhanced = !!enhanced;

  if (!showOriginal && !showEnhanced) {
    return (
      <div className="rounded-2xl border border-[oklch(0.91_0.015_285)] bg-white p-8 text-center">
        <p className="text-sm text-[oklch(0.55_0.04_280)]">
          {error ?? "Loading comparison…"}
        </p>
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      className="rounded-2xl overflow-hidden border border-[oklch(0.91_0.015_285)] bg-[#06060f] shadow-sm"
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-white/95 border-b border-[oklch(0.91_0.015_285)]">
        <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[oklch(0.44_0.22_155)]">
          <ArrowLeftRight className="w-3.5 h-3.5" />
          {label}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setZoomed((v) => !v)}
            title={zoomed ? "Zoom out" : "Zoom in"}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-[oklch(0.55_0.04_280)] hover:bg-[oklch(0.94_0.05_290)] transition-colors"
          >
            {zoomed ? <ZoomOut className="w-4 h-4" /> : <ZoomIn className="w-4 h-4" />}
          </button>
          <button
            onClick={toggleFullscreen}
            title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-[oklch(0.55_0.04_280)] hover:bg-[oklch(0.94_0.05_290)] transition-colors"
          >
            {fullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Stage */}
      <div
        className={`relative w-full ${zoomed ? "overflow-auto cursor-zoom-out" : "overflow-hidden"}`}
        onClick={() => zoomed && setZoomed(false)}
      >
        <div className={`relative ${zoomed ? "w-[200%] min-h-[56vh]" : "h-[56vh]"}`}>
          {/* Enhanced (base) */}
          {showEnhanced && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              id="viewer-enhanced"
              src={enhanced as string}
              alt="Enhanced output"
              className="absolute inset-0 w-full h-full object-contain"
              draggable={false}
            />
          )}
          {/* Original (clipped on top) */}
          {showOriginal && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              id="viewer-original"
              src={original as string}
              alt="Original input"
              className="absolute inset-0 w-full h-full object-contain"
              style={{ clipPath: `inset(0 ${100 - percent}% 0 0)` }}
              draggable={false}
            />
          )}
          {/* Divider */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-white/90 z-10 pointer-events-none"
            style={{ left: `${percent}%` }}
          />
          {/* Labels */}
          <span className="absolute top-3 left-3 z-20 text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded-full bg-black/60 text-emerald-200 border border-emerald-200/25">
            Original
          </span>
          <span className="absolute top-3 right-3 z-20 text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded-full bg-[oklch(0.52_0.22_155)] text-white">
            Enhanced
          </span>
        </div>
      </div>

      {/* Slider + download */}
      <div className="flex items-center gap-4 px-4 py-3 bg-white/95 border-t border-[oklch(0.91_0.015_285)]">
        <input
          id="viewer-slider"
          type="range"
          min={0}
          max={100}
          value={percent}
          onChange={(e) => setPercent(Number(e.target.value))}
          disabled={!showOriginal || !showEnhanced}
          aria-label="Comparison slider"
          className="flex-1 accent-[oklch(0.52_0.22_155)]"
        />
        <div className="flex items-center gap-2">
          {showEnhanced && (
            <a
              id="viewer-download"
              href={enhanced as string}
              download
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-lg btn-purple"
            >
              <Download className="w-3.5 h-3.5" />
              Download
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
