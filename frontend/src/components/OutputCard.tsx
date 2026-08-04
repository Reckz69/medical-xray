"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ImageIcon, Maximize2, Download, X } from "lucide-react";
import { getOutputUrl } from "@/lib/api";

export function OutputCard({
  scanId,
  outputType,
  label,
  accentColor,
  description,
  fallbackImage,
  enabled,
  isScanning,
}: {
  scanId: string;
  outputType: string;
  label: string;
  accentColor: string;
  description: string;
  fallbackImage?: string | null;
  enabled: boolean;
  isScanning: boolean;
}) {
  const [fetching, setFetching] = useState(true);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enlarged, setEnlarged] = useState(false);
  const imageId = `output-${outputType.toLowerCase().replace(/_/g, "-")}`;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    getOutputUrl(scanId, outputType)
      .then((result) => {
        if (!cancelled) setUrl(result.download_url);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load output");
        }
      })
      .finally(() => {
        if (!cancelled) setFetching(false);
      });
    return () => { cancelled = true; };
  }, [scanId, outputType, enabled]);

  const loading = enabled && fetching;
  const shownSrc = url ?? fallbackImage ?? null;
  const isEmpty = !shownSrc && !loading && !error;
  const downloading = enabled && !!url;

  return (
    <>
      <div className="relative group w-full">
        <AnimatePresence>
          {isScanning && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.6 }}
              exit={{ opacity: 0 }}
              className="absolute -inset-[3px] rounded-2xl z-0 blur-md"
              style={{ backgroundColor: accentColor }}
              transition={{ duration: 1, repeat: Infinity, repeatType: "reverse" }}
            />
          )}
        </AnimatePresence>

        <div className={`glass-card rounded-2xl overflow-hidden flex flex-col h-[56vh] min-h-[380px] relative z-10 border transition-all duration-300 bg-white ${isScanning ? "border-transparent" : "border-[oklch(0.91_0.015_285)]"}`}>
          <div className="flex items-center justify-between px-4 py-3 border-b border-[oklch(0.91_0.015_285)] bg-white/80 backdrop-blur-md z-20">
            <span className="font-bold text-sm text-[oklch(0.14_0.02_275)]">{label}</span>
            <div className="flex items-center gap-2">
              <span
                className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                style={{ background: accentColor + "20", color: accentColor }}
              >
                {label.toUpperCase()}
              </span>
              {!isEmpty && shownSrc && (
                <button
                  onClick={() => setEnlarged(true)}
                  className="w-6 h-6 rounded flex items-center justify-center hover:bg-[oklch(0.94_0.05_290)] transition-colors"
                  title="Expand"
                >
                  <Maximize2 className="w-3.5 h-3.5 text-[oklch(0.55_0.04_280)]" />
                </button>
              )}
            </div>
          </div>

          <div className="flex-1 bg-[#06060f] relative flex items-center justify-center overflow-hidden">
            {isEmpty ? (
              <div className="flex flex-col items-center gap-4 text-center p-6 z-20">
                <ImageIcon className="w-9 h-9 text-[oklch(0.3_0.05_285)]" />
                <p className="text-xs text-[oklch(0.35_0.05_280)]">{description}</p>
              </div>
            ) : (
              <AnimatePresence>
                {shownSrc && (
                  <motion.img
                    id={imageId}
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    src={shownSrc}
                    alt={label}
                    className="w-full h-full object-contain z-10"
                  />
                )}
              </AnimatePresence>
            )}

            {(isScanning || (loading && enabled && !fallbackImage)) && (
              <div className="absolute inset-0 z-20 bg-black/40 flex flex-col items-center justify-center gap-4">
                <div
                  className="w-12 h-12 rounded-full border-4 border-t-transparent animate-spin"
                  style={{ borderColor: accentColor, borderTopColor: "transparent" }}
                />
                <p className="text-sm font-medium animate-pulse" style={{ color: "#fff" }}>
                  Processing {label}…
                </p>
              </div>
            )}

            {error && !isScanning && (
              <div className="absolute inset-0 z-20 bg-black/60 flex items-center justify-center p-6">
                <p className="text-xs text-red-300 text-center">{error}</p>
              </div>
            )}
          </div>

          <div className="px-4 py-2.5 text-xs text-[oklch(0.55_0.04_280)] border-t border-[oklch(0.91_0.015_285)] bg-white z-20 flex items-center justify-between gap-2">
            <span className="truncate">{description}</span>
            {downloading && (
              <a
                id={`download-${outputType.toLowerCase().replace(/_/g, "-")}`}
                href={url as string}
                download
                target="_blank"
                rel="noopener noreferrer"
                className="flex-shrink-0 inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-lg btn-purple"
              >
                <Download className="w-3.5 h-3.5" />
                Download
              </a>
            )}
          </div>
        </div>
      </div>

      {enlarged && shownSrc && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6"
          onClick={() => setEnlarged(false)}
        >
          <div className="relative max-w-5xl w-full flex flex-col items-center" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setEnlarged(false)}
              className="absolute -top-12 right-0 w-10 h-10 bg-white/10 hover:bg-white/20 text-white rounded-full flex items-center justify-center backdrop-blur-md transition-colors"
            >
              <X className="w-6 h-6" />
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={shownSrc} alt={label} className="w-full h-auto max-h-[85vh] rounded-xl object-contain shadow-2xl" />
            <p className="text-center text-white/70 text-sm mt-4">{label} — {description}</p>
          </div>
        </div>
      )}
    </>
  );
}
