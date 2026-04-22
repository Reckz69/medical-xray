"use client";

import Image from "next/image";
import Link from "next/link";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Zap,
  ShieldCheck,
  Brain,
  GitBranch,
  Clock,
  Scan,
  ChevronRight,
  Activity,
  Star,
  ArrowRight,
  CheckCircle2,
  ArrowLeftRight,
} from "lucide-react";

const DotGrid = dynamic(() => import("@/components/DotGrid"), { ssr: false });

/* ============================================
   DATA
   ============================================ */
const features = [
  {
    icon: Brain,
    title: "Zero-Hallucination AI",
    desc: "Preserves 100% of biological structures. Our N2N framework mathematically guarantees no anatomy is invented or erased.",
  },
  {
    icon: GitBranch,
    title: "Smart Gateway Routing",
    desc: "Calculates noise variance in real-time to safely bypass already-clean digital scans and preserve bone detail.",
  },
  {
    icon: ShieldCheck,
    title: "Secure & Private",
    desc: "Patient data and DICOM files never leave your environment. Zero cloud dependency, zero PHI exposure.",
  },
  {
    icon: Scan,
    title: "Optimized for ICU & Rural",
    desc: "Minimal UI designed for high-stress environments. Works on portable tablets and low-bandwidth connections.",
  },
  {
    icon: Clock,
    title: "Lightning-Fast Processing",
    desc: "Batch-process entire studies in seconds. Enhanced clinical outputs delivered faster than a radiographer refresh.",
  },
  {
    icon: Scan,
    title: "DICOM Native",
    desc: "Reads DICOM metadata natively, handles PhotometricInterpretation inversion and 16-bit pixel arrays seamlessly.",
  },
];

const stats = [
  { value: "100%", label: "Anatomy Preserved" },
  { value: "N2N", label: "AI Framework" },
  { value: "DICOM", label: "Native Format" },
  { value: "<3s", label: "Avg. Processing" },
];

const techSteps = [
  {
    step: "01",
    title: "Smart Gateway",
    desc: "The system calculates noise variance using edge-masked flat tissue regions. Only truly noisy scans proceed to the AI — clean scans bypass the model entirely.",
  },
  {
    step: "02",
    title: "N2N U-Net Denoising",
    desc: "The 256×256 patch-based U-Net model—trained with Noise-to-Noise mathematics—strips quantum mottle, scatter, and grid lines without inventing new data.",
  },
  {
    step: "03",
    title: "Clinical Enhancement",
    desc: "CLAHE contrast enhancement and soft unsharp masking are applied to both paths, delivering a final clinical output ready for diagnostic review.",
  },
];

/* ============================================
   HERO — Before / After X-ray panel
   ============================================ */
function HeroSection() {
  return (
    <section className="relative min-h-[calc(100vh-64px)] flex items-center orb-bg overflow-hidden">
      {/* ── Interactive DotGrid background ── */}
      <div className="absolute inset-0 z-0 pointer-events-auto">
        <DotGrid
          dotSize={8}
          gap={27}
          baseColor="#bbf7d0"
          activeColor="#16a34a"
          proximity={230}
          shockRadius={240}
          shockStrength={5}
          resistance={750}
          returnDuration={2}
        />
      </div>
      {/* Soft white fade so content stays readable */}
      <div className="absolute inset-0 z-[1] bg-gradient-to-r from-white/90 via-white/70 to-white/30 pointer-events-none" />

      <div className="relative z-10 w-full max-w-7xl mx-auto px-6 md:px-12 py-16
                      grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">

        {/* ── Left: Copy ── */}
        <div className="space-y-7">
          <div className="pill-badge fade-in-up">
            <Activity className="w-3 h-3" />
            AI-Powered Radiology
          </div>

          <div className="fade-in-up fade-in-up-delay-1">
            <h1 className="text-5xl md:text-6xl font-extrabold leading-[1.08] tracking-tight text-[oklch(0.14_0.02_275)]">
              Clear X-Rays.
              <br />
              Better Learning.
              <br />
              <span className="text-gradient">Stronger Future.</span>
            </h1>
          </div>

          <p className="text-lg text-[oklch(0.45_0.05_280)] leading-relaxed max-w-lg fade-in-up fade-in-up-delay-2">
            Our AI removes noise while preserving anatomy, helping the next generation of doctors learn
            with clarity and confidence — without ever hallucinating or altering the underlying human anatomy.
          </p>

          <div className="flex flex-wrap items-center gap-4 fade-in-up fade-in-up-delay-3">
            {["DICOM Support", "Zero-Cloud Privacy", "ICU-Ready"].map((tag) => (
              <span key={tag} className="flex items-center gap-1.5 text-sm text-[oklch(0.44_0.22_155)] font-medium">
                <CheckCircle2 className="w-4 h-4" />
                {tag}
              </span>
            ))}
          </div>

          <div className="flex flex-wrap gap-4 fade-in-up fade-in-up-delay-4">
            <Link href="/denoise">
              <Button id="hero-try-btn" className="btn-purple h-12 px-8 text-base rounded-full font-semibold gap-2">
                Upload X-Ray
                <Zap className="w-4 h-4" />
              </Button>
            </Link>
            <Link href="/about">
              <Button
                id="hero-learn-btn"
                variant="outline"
                className="h-12 px-8 text-base rounded-full font-semibold gap-2
                           border-[oklch(0.78_0.14_155)] text-[oklch(0.44_0.22_155)]
                           hover:bg-[oklch(0.94_0.05_155)]"
              >
                See How It Works
                <ChevronRight className="w-4 h-4" />
              </Button>
            </Link>
          </div>
        </div>

        {/* ── Right: Before / After X-ray panel ── */}
        <div className="relative flex items-center justify-center">
          {/* Soft glow behind panels */}
          <div
            className="absolute inset-0 rounded-3xl pointer-events-none"
            style={{
              background:
                "radial-gradient(ellipse at center, oklch(0.52 0.22 155 / 0.12) 0%, transparent 70%)",
            }}
          />

          {/* Floating card */}
          <div
            className="relative w-full max-w-[520px] rounded-2xl p-4 fade-in-up fade-in-up-delay-2"
            style={{
              background: "rgba(255,255,255,0.80)",
              backdropFilter: "blur(24px)",
              WebkitBackdropFilter: "blur(24px)",
              border: "1px solid rgba(22,163,74,0.15)",
              boxShadow:
                "0 24px 64px oklch(0.52 0.22 155 / 0.14), 0 4px 16px rgba(0,0,0,0.06)",
            }}
          >
            {/* Panel row */}
            <div className="grid grid-cols-2 gap-3">

              {/* Before */}
              <div className="relative rounded-xl overflow-hidden bg-black group">
                {/* Label */}
                <span
                  className="absolute top-2 left-2 z-10 text-[10px] font-bold tracking-widest
                             uppercase px-2.5 py-0.5 rounded-full"
                  style={{
                    background: "rgba(0,0,0,0.55)",
                    color: "#86efac",
                    border: "1px solid rgba(134,239,172,0.25)",
                  }}
                >
                  Before
                </span>

                <Image
                  src="/xray-before.png"
                  alt="Noisy X-ray before denoising"
                  width={240}
                  height={260}
                  className="w-full object-cover opacity-80 group-hover:opacity-90 transition-opacity duration-300"
                  style={{ filter: "brightness(0.9) contrast(1.05)" }}
                  priority
                />

                {/* Subtle noise grain overlay */}
                <div
                  className="absolute inset-0 pointer-events-none opacity-30"
                  style={{
                    backgroundImage:
                      "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.15'/%3E%3C/svg%3E\")",
                  }}
                />
              </div>

              {/* After */}
              <div className="relative rounded-xl overflow-hidden bg-black group">
                {/* Label */}
                <span
                  className="absolute top-2 left-2 z-10 text-[10px] font-bold tracking-widest
                             uppercase px-2.5 py-0.5 rounded-full"
                  style={{
                    background: "oklch(0.52 0.22 155 / 0.75)",
                    color: "#fff",
                    border: "1px solid oklch(0.68 0.18 155 / 0.4)",
                  }}
                >
                  After
                </span>

                <Image
                  src="/xray-after.png"
                  alt="Enhanced X-ray after AI denoising"
                  width={240}
                  height={260}
                  className="w-full object-cover group-hover:opacity-95 transition-opacity duration-300"
                  style={{ filter: "brightness(1.05) contrast(1.12) saturate(0.9)" }}
                  priority
                />
              </div>
            </div>

            {/* Bottom swap bar */}
            <div className="mt-3 flex items-center justify-between px-2">
              <span className="text-xs text-[oklch(0.55_0.04_280)] font-medium">
                AI-Enhanced Comparison
              </span>
              <div
                className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold"
                style={{
                  background: "oklch(0.94 0.05 155)",
                  color: "oklch(0.44 0.22 155)",
                }}
              >
                <ArrowLeftRight className="w-3 h-3" />
                Denoise X Output
              </div>
            </div>
          </div>

          {/* Floating badge — top right */}
          <div
            className="absolute -top-3 -right-3 md:right-4 px-3 py-1.5 rounded-full text-xs font-bold
                       shadow-lg flex items-center gap-1.5 fade-in-up fade-in-up-delay-3"
            style={{
              background: "linear-gradient(135deg, oklch(0.52 0.22 155), oklch(0.44 0.22 155))",
              color: "white",
            }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-white/80 pulse-dot" />
            N2N U-Net Active
          </div>
        </div>
      </div>
    </section>
  );
}

/* ============================================
   STATS BAR
   ============================================ */
function StatsBar() {
  return (
    <section className="py-8 border-y border-[oklch(0.91_0.015_285)] bg-white">
      <div className="max-w-4xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-6">
        {stats.map((s) => (
          <div key={s.label} className="stat-card">
            <div className="text-3xl font-extrabold text-gradient mb-1">{s.value}</div>
            <div className="text-sm text-[oklch(0.52_0.05_280)] font-medium">{s.label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ============================================
   FEATURES
   ============================================ */
function FeaturesSection() {
  return (
    <section id="features" className="py-24 max-w-7xl mx-auto px-6 md:px-12">
      <div className="text-center mb-16">
        <div className="pill-badge mb-4 mx-auto w-fit">
          <Star className="w-3 h-3" />
          Key Features
        </div>
        <h2 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)] mb-4">
          Engineering Breakthroughs
        </h2>
        <p className="text-[oklch(0.45_0.05_280)] max-w-xl mx-auto text-lg">
          Every feature is purpose-built for clinical reliability in demanding medical environments.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {features.map((f, i) => (
          <Card
            key={f.title}
            className="glass-card glass-card-hover cursor-default border-0 p-0"
            style={{ animationDelay: `${i * 0.08}s` }}
          >
            <CardContent className="p-7">
              <div className="feature-icon mb-5">
                <f.icon className="w-6 h-6" strokeWidth={1.8} />
              </div>
              <h3 className="font-bold text-[oklch(0.14_0.02_275)] text-lg mb-2">{f.title}</h3>
              <p className="text-[oklch(0.52_0.05_280)] text-sm leading-relaxed">{f.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}

/* ============================================
   HOW IT WORKS
   ============================================ */
function HowItWorksSection() {
  return (
    <section className="py-24 bg-[oklch(0.97_0.01_285)] orb-bg">
      <div className="max-w-7xl mx-auto px-6 md:px-12">
        <div className="text-center mb-16">
          <div className="pill-badge mb-4 mx-auto w-fit">
            <Zap className="w-3 h-3" />
            The Pipeline
          </div>
          <h2 className="text-4xl font-extrabold text-[oklch(0.14_0.02_275)] mb-4">
            How Denoise X Works
          </h2>
          <p className="text-[oklch(0.45_0.05_280)] max-w-xl mx-auto text-lg">
            A three-stage clinical pipeline that guarantees safety, precision, and speed.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {techSteps.map((step, i) => (
            <div key={step.step} className="relative">
              {i < techSteps.length - 1 && (
                <div
                  className="hidden md:block absolute top-8 left-[calc(100%-0px)] w-full h-px"
                  style={{
                    background:
                      "linear-gradient(90deg, oklch(0.78 0.14 155 / 0.5), transparent)",
                    zIndex: 0,
                  }}
                />
              )}
              <div className="glass-card glass-card-hover rounded-2xl p-8 relative z-10">
                <div className="text-5xl font-black text-gradient opacity-30 mb-4 leading-none">
                  {step.step}
                </div>
                <h3 className="font-bold text-[oklch(0.14_0.02_275)] text-xl mb-3">{step.title}</h3>
                <p className="text-[oklch(0.52_0.05_280)] text-sm leading-relaxed">{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ============================================
   CTA
   ============================================ */
function CTASection() {
  return (
    <section className="py-24 px-6 md:px-12">
      <div className="max-w-4xl mx-auto text-center">
        <div className="gradient-border p-[1px] rounded-3xl">
          <div className="bg-white rounded-3xl p-14 relative overflow-hidden">
            <div
              className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 rounded-full pointer-events-none"
              style={{
                background:
                  "radial-gradient(circle, oklch(0.88 0.09 155 / 0.4) 0%, transparent 70%)",
              }}
            />
            <div className="relative z-10">
              <Badge className="mb-6 bg-[oklch(0.94_0.05_155)] text-[oklch(0.44_0.22_155)] border-[oklch(0.88_0.09_155)] text-sm px-4 py-1">
                Ready to Enhance?
              </Badge>
              <h2 className="text-4xl md:text-5xl font-extrabold text-[oklch(0.14_0.02_275)] mb-6 leading-tight">
                Start enhancing your
                <br />
                <span className="text-gradient">X-rays today</span>
              </h2>
              <p className="text-[oklch(0.45_0.05_280)] text-lg mb-10 max-w-md mx-auto">
                Upload your first DICOM or PNG file and see the difference Denoise X delivers in seconds.
              </p>
              <Link href="/denoise">
                <Button id="cta-main-btn" className="btn-purple h-14 px-10 text-lg rounded-full font-bold gap-2">
                  Try Denoise X Now
                  <ArrowRight className="w-5 h-5" />
                </Button>
              </Link>
              <p className="text-xs text-[oklch(0.65_0.04_280)] mt-6">
                ⚠️ For supplementary clinical decision support only. Always consult a qualified healthcare provider.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ============================================
   FOOTER
   ============================================ */
function Footer() {
  return (
    <footer className="border-t border-[oklch(0.91_0.015_285)] py-10 px-6 md:px-12">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg btn-purple flex items-center justify-center">
            <Zap className="w-3.5 h-3.5 text-white" strokeWidth={2.5} />
          </div>
          <span className="font-bold text-[oklch(0.14_0.02_275)]">
            Denoise<span className="text-gradient"> X</span>
          </span>
        </div>
        <p className="text-sm text-[oklch(0.55_0.04_280)]">
          © 2026 Denoise X. Built with N2N + U-Net AI. For clinical decision support only.
        </p>
        <div className="flex gap-6 text-sm text-[oklch(0.55_0.04_280)]">
          <Link href="/about" className="hover:text-[oklch(0.52_0.22_155)] transition-colors">About</Link>
          <Link href="/feedback" className="hover:text-[oklch(0.52_0.22_155)] transition-colors">Feedback</Link>
        </div>
      </div>
    </footer>
  );
}

/* ============================================
   PAGE
   ============================================ */
export default function HomePage() {
  return (
    <>
      <HeroSection />
      <StatsBar />
      <FeaturesSection />
      <div className="section-divider mx-auto max-w-4xl" />
      <HowItWorksSection />
      <CTASection />
      <Footer />
    </>
  );
}


