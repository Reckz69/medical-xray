import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/Navbar";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Denoise X — Clinical-Grade AI X-Ray Enhancement",
  description:
    "Denoise X uses Noise-to-Noise AI with U-Net architecture to rescue low-dose chest X-rays, delivering crystal-clear enhanced medical images without hallucination.",
  keywords: ["medical AI", "X-ray denoising", "DICOM", "chest X-ray", "clinical imaging", "N2N", "U-Net"],
  openGraph: {
    title: "Denoise X — Clinical-Grade AI X-Ray Enhancement",
    description: "Empowering medical professionals with clinical-grade X-ray enhancement using self-supervised AI.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen bg-background antialiased">
        <Navbar />
        <main className="pt-16">
          {children}
        </main>
      </body>
    </html>
  );
}
