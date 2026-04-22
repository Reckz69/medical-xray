# Denoise X: Medical X-Ray Image Enhancement

Denoise X is an AI-powered platform designed to enhance medical X-ray images. It uses a Noise-to-Noise (N2N) U-Net architecture to isolate and remove clinical noise, followed by CLAHE (Contrast Limited Adaptive Histogram Equalization) and soft unsharp masking to deliver high-fidelity, diagnostic-ready outputs.

## 🚀 Features

- **AI-Powered Denoising**: Leverages N2N U-Net for clinical-grade noise reduction.
- **Dynamic Animation**: Real-time "medical scanner" animation during inference.
- **3-Card Analysis**: Compare Original, Noise Map, and Enhanced images side-by-side.
- **Smart Routing**: Analyzes noise variance to determine the best enhancement path.
- **DICOM Support**: Handles medical imaging formats alongside PNG and JPEG.

---

## 🛠️ Project Structure

- `/frontend`: Next.js (React) application with Framer Motion animations.
- `/backend`: FastAPI inference engine for model execution.
- `inference.py`: Core model logic and image processing pipeline.

---

## 💻 Getting Started

### 1. Backend Setup

The backend handles the AI inference.

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --reload
```

### 2. Frontend Setup

The frontend provides the interactive user interface.

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Run the development server
npm run dev
```

The application will be available at `http://localhost:3000`.

---

## ⚕️ Clinical Disclaimer

Denoise X is a supplementary visual aid intended to assist healthcare professionals. It is **not** a primary diagnostic tool. Always consult a qualified radiologist for final clinical decisions.

---

## 📄 License

This project is licensed under the MIT License.
