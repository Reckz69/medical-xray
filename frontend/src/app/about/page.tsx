"use client";

import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Brain,
  GitBranch,
  ShieldCheck,
  MonitorSmartphone,
  Clock,
  Scan,
  Zap,
  ArrowRight,
  BookOpen,
  FlaskConical,
  Users,
  AlertTriangle,
  ArrowLeftRight,
} from "lucide-react";

/* ============================================
   DATA
   ============================================ */
const mission = {
  title: "Our Mission",
  body: `Denoise X is designed to help medical professionals rescue low-dose and portable chest X-rays using the power of self-supervised artificial intelligence. By utilizing a strict Noise-to-Noise (N2N) mathematical framework combined with U-Net architecture, our engine cleanly strips away quantum mottle, scatter radiation, and hardware grid lines. We provide crystal-clear, enhanced medical images to build diagnostic confidence and support your clinical decision-making process—without ever hallucinating or altering the underlying human anatomy.`,
};

const features = [
  {
    icon: Brain,
    title: "Zero-Hallucination AI",
    desc: "Preserves 100% of biological structures. Our strict N2N framework mathematically guarantees no anatomy is invented, removed, or altered during the denoising process.",
    color: "#16a34a",
  },
  {
    icon: GitBranch,
    title: "Smart Gateway Routing",
    desc: "Mathematically calculates noise variance in flat tissue regions (ignoring bone edges via Canny edge detection) to safely bypass already-clean digital scans and preserve fine bone detail.",
    color: "#15803d",
  },
  {
    icon: ShieldCheck,
    title: "Secure & Private Architecture",
    desc: "Patient data and DICOM files stay protected. Zero cloud dependency ensures PHI never leaves the clinical environment, meeting strict medical data privacy requirements.",
    color: "#166534",
  },
  {
    icon: MonitorSmartphone,
    title: "ICU & Rural-Optimized UI",
    desc: "The interface is built specifically for high-stress ICU environments and low-resource rural clinics. Minimal cognitive load, large touch targets, and offline-capable architecture.",
    color: "#14532d",
  },
  {
    icon: Clock,
    title: "Lightning-Fast Batch Processing",
    desc: "Patch-based 256×256 U-Net tiling enables GPU-accelerated processing of full-resolution X-rays and entire DICOM studies in seconds, not minutes.",
    color: "#16a34a",
  },
  {
    icon: Scan,
    title: "Native DICOM Support",
    desc: "Handles raw 16-bit DICOM pixel arrays, reads PhotometricInterpretation metadata for inversion correction (MONOCHROME1), and normalizes data for model inference automatically.",
    color: "#15803d",
  },
];

const technicalSpecs = [
  { label: "AI Architecture", value: "U-Net (Encoder-Decoder)" },
  { label: "Training Framework", value: "Noise-to-Noise (N2N)" },
  { label: "Patch Size", value: "256 × 256 px" },
  { label: "Model Format", value: ".keras (TensorFlow)" },
  { label: "Noise Threshold", value: "Variance > 8.0" },
  { label: "Enhancement", value: "CLAHE + Unsharp Masking" },
  { label: "DICOM", value: "16-bit MONOCHROME1/2" },
  { label: "Target Pathology", value: "Quantum Mottle, Scatter, Grids" },
];

const pipelineStages = [
  {
    step: "01",
    icon: Scan,
    title: "Image Ingestion",
    desc: "Accepts DICOM (.dcm, .dicom), PNG, and JPEG formats. For DICOM files, pydicom reads the 16-bit pixel array, normalizes it to 8-bit (0–255), and corrects PhotometricInterpretation inversions automatically.",
  },
  {
    step: "02",
    icon: GitBranch,
    title: "Smart Gateway Variance Analysis",
    desc: "Canny edge detection isolates bone boundaries. A 5×5 dilation mask removes those regions. Median blur residual analysis on the remaining flat tissue measures true quantum noise variance—bypassing clean scans (variance < 8.0) to preserve anatomy.",
  },
  {
    step: "03",
    icon: Brain,
    title: "N2N U-Net Denoising",
    desc: "High-noise scans are split into 256×256 patches with reflect padding. Each patch passes through the trained U-Net model (compiled=False for inference). Predictions are tiled back together to reconstruct the full-resolution denoised image.",
  },
  {
    step: "04",
    icon: Zap,
    title: "Clinical Enhancement",
    desc: "CLAHE (clipLimit=1.0, tileGridSize=8×8) applies localized contrast enhancement. A Gaussian unsharp mask (σ=1.0) with a soft blend (0.5 original / -0.2 smooth) delivers the final clinical output—crisp, artifact-free, and ready for diagnostic review.",
  },
];

/* ============================================
   ABOUT PAGE
   ============================================ */
export default function AboutPage() {
  return (
    <div className="min-h-screen">

      {/* ── Hero ── */}
      <section className="relative py-20 px-6 md:px-12 orb-bg hero-grid overflow-hidden">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <div className="pill-badge">
              <BookOpen className="w-3 h-3" />
              About Denoise X
            </div>
            <h1 className="text-5xl font-extrabold text-[oklch(0.14_0.02_275)] leading-tight">
              Empowering Medical
              <br />
              <span className="text-gradient">Professionals</span>
              <br />
              with Clinical AI
            </h1>
            <p className="text-lg text-[oklch(0.45_0.05_280)] leading-relaxed max-w-lg">
              {mission.body.slice(0, 220)}…
            </p>
            <Link href="/denoise">
              <Button id="about-try-btn" className="btn-purple h-12 px-8 rounded-full font-bold gap-2">
                Try Denoise X <ArrowRight className="w-4 h-4" />
              </Button>
            </Link>
          </div>

          {/* Before / After X-ray panel */}
          <div className="relative flex items-center justify-center">
            <div
              className="absolute inset-0 rounded-3xl pointer-events-none"
              style={{
                background:
                  "radial-gradient(ellipse at center, oklch(0.52 0.22 155 / 0.10) 0%, transparent 70%)",
              }}
            />
            <div
              className="relative w-full max-w-[460px] rounded-2xl p-4"
              style={{
                background: "rgba(255,255,255,0.82)",
                backdropFilter: "blur(20px)",
                WebkitBackdropFilter: "blur(20px)",
                border: "1px solid rgba(22,163,74,0.15)",
                boxShadow: "0 24px 64px oklch(0.52 0.22 155 / 0.12), 0 4px 16px rgba(0,0,0,0.05)",
              }}
            >
              <div className="grid grid-cols-2 gap-3">
                {/* Before */}
                <div className="relative rounded-xl overflow-hidden bg-black">
                  <span
                    className="absolute top-2 left-2 z-10 text-[10px] font-bold tracking-widest uppercase px-2.5 py-0.5 rounded-full"
                    style={{ background: "rgba(0,0,0,0.55)", color: "#86efac", border: "1px solid rgba(134,239,172,0.25)" }}
                  >
                    Before
                  </span>
                  <Image
                    src="/xray-before.png"
                    alt="Noisy X-ray before denoising"
                    width={220}
                    height={240}
                    className="w-full object-cover opacity-80"
                    style={{ filter: "brightness(0.9) contrast(1.05)" }}
                  />
                </div>
                {/* After */}
                <div className="relative rounded-xl overflow-hidden bg-black">
                  <span
                    className="absolute top-2 left-2 z-10 text-[10px] font-bold tracking-widest uppercase px-2.5 py-0.5 rounded-full"
                    style={{ background: "oklch(0.52 0.22 155 / 0.80)", color: "#fff", border: "1px solid oklch(0.68 0.18 155 / 0.4)" }}
                  >
                    After
                  </span>
                  <Image
                    src="/xray-after.png"
                    alt="Enhanced X-ray after AI denoising"
                    width={220}
                    height={240}
                    className="w-full object-cover"
                    style={{ filter: "brightness(1.05) contrast(1.12) saturate(0.9)" }}
                  />
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between px-2">
                <span className="text-xs text-[oklch(0.55_0.04_280)] font-medium">AI-Enhanced Comparison</span>
                <div
                  className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold"
                  style={{ background: "oklch(0.94 0.05 155)", color: "oklch(0.44 0.22 155)" }}
                >
                  <ArrowLeftRight className="w-3 h-3" />
                  Denoise X Output
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Mission ── */}
      <section className="py-20 px-6 md:px-12 bg-white">
        <div className="max-w-4xl mx-auto text-center">
          <div className="pill-badge mb-5 mx-auto w-fit">
            <FlaskConical className="w-3 h-3" />
            Our Mission
          </div>
          <h2 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)] mb-8">
            Built for Clinical Reality
          </h2>
          <div className="gradient-border p-[1px] rounded-2xl">
            <div className="bg-white rounded-2xl p-10">
              <p className="text-[oklch(0.35_0.05_280)] text-lg leading-loose">{mission.body}</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section className="py-20 px-6 md:px-12 bg-[oklch(0.98_0.005_285)]">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <div className="pill-badge mb-4 mx-auto w-fit">
              <Zap className="w-3 h-3" />
              Key Features
            </div>
            <h2 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)]">
              Engineering Breakthroughs
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((f) => (
              <Card key={f.title} className="glass-card glass-card-hover border-0 p-0 h-full">
                <CardContent className="p-7 h-full flex flex-col">
                  <div className="feature-icon mb-5" style={{ background: `${f.color}15`, color: f.color }}>
                    <f.icon className="w-6 h-6" strokeWidth={1.8} />
                  </div>
                  <h3 className="font-bold text-[oklch(0.14_0.02_275)] text-lg mb-2">{f.title}</h3>
                  <p className="text-[oklch(0.52_0.05_280)] text-sm leading-relaxed flex-1">{f.desc}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* ── Technical Pipeline ── */}
      <section className="py-20 px-6 md:px-12 bg-white">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <div className="pill-badge mb-4 mx-auto w-fit">
              <Brain className="w-3 h-3" />
              Technical Deep-Dive
            </div>
            <h2 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)]">
              The 4-Stage Pipeline
            </h2>
            <p className="text-[oklch(0.45_0.05_280)] mt-3 text-lg max-w-xl mx-auto">
              Every step is deterministic, auditable, and designed with clinical safety as the primary constraint.
            </p>
          </div>

          <div className="space-y-6">
            {pipelineStages.map((stage, i) => (
              <div
                key={stage.step}
                className="glass-card glass-card-hover rounded-2xl p-8 grid grid-cols-[auto_1fr] gap-6 items-start"
              >
                <div className="flex flex-col items-center gap-3">
                  <div className="text-4xl font-black text-gradient opacity-25 leading-none">{stage.step}</div>
                  <div className="feature-icon">
                    <stage.icon className="w-5 h-5" strokeWidth={1.8} />
                  </div>
                  {i < pipelineStages.length - 1 && (
                    <div className="w-px flex-1 min-h-[24px] bg-gradient-to-b from-[oklch(0.78_0.14_155)] to-transparent" />
                  )}
                </div>
                <div>
                  <h3 className="font-bold text-[oklch(0.14_0.02_275)] text-xl mb-2">{stage.title}</h3>
                  <p className="text-[oklch(0.45_0.05_280)] leading-relaxed">{stage.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Tech Specs ── */}
      <section className="py-20 px-6 md:px-12 bg-[oklch(0.97_0.01_285)]">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <div className="pill-badge mb-4 mx-auto w-fit">
              <Users className="w-3 h-3" />
              Technical Specifications
            </div>
            <h2 className="text-3xl font-extrabold text-[oklch(0.14_0.02_275)]">Model & System Specs</h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            {technicalSpecs.map((spec) => (
              <div key={spec.label} className="stat-card">
                <div className="text-base font-bold text-gradient mb-1 leading-tight">{spec.value}</div>
                <div className="text-xs text-[oklch(0.55_0.04_280)]">{spec.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Important Note ── */}
      <section className="py-20 px-6 md:px-12 bg-white">
        <div className="max-w-3xl mx-auto">
          <div className="rounded-2xl border-2 border-amber-200 bg-amber-50 p-10">
            <div className="flex items-start gap-5">
              <div className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center flex-shrink-0">
                <AlertTriangle className="w-6 h-6 text-amber-600" />
              </div>
              <div>
                <h3 className="font-bold text-amber-900 text-xl mb-3">Important Clinical Notice</h3>
                <p className="text-amber-800 leading-relaxed">
                  Denoise X is designed to <strong>assist medical professionals, not replace them</strong>.
                  Always consult with a qualified healthcare provider for proper diagnosis and treatment.
                  This tool should be used strictly as a supplementary visual aid in the clinical decision-making process.
                  Results are intended for review by trained radiologists and clinicians only.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

    </div>
  );
}


