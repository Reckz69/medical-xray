import numpy as np
import tensorflow as tf
import cv2
import matplotlib.pyplot as plt
import pydicom # NEW: The standard library for medical DICOM files

# ==========================================
# --- 1. CONFIGURATION ---
# ==========================================
MODEL_PATH = 'n2n_unet_best_weights04.keras' 
# Change this to your actual downloaded DICOM file name
TEST_IMAGE_PATH = 'low_nosie_dicom.dicom' 

print("Loading Original Golden Model...")
model = tf.keras.models.load_model(MODEL_PATH, compile=False)
print("Model loaded successfully!")

# ==========================================
# --- 2. THE SMART GATEWAY ALGORITHM ---
# ==========================================
def detect_noise_level(image_array):
    """Calculates noise variance ONLY in the flat tissue, ignoring bone edges."""
    edges = cv2.Canny(image_array, 50, 150)
    kernel = np.ones((5, 5), np.uint8)
    edge_mask = cv2.dilate(edges, kernel, iterations=1)
    flat_areas_mask = cv2.bitwise_not(edge_mask)
    
    blurred = cv2.medianBlur(image_array, 5)
    static_residual = cv2.absdiff(image_array, blurred)
    flat_noise = static_residual[flat_areas_mask == 255]
    
    if len(flat_noise) == 0:
        return 0.0
        
    return np.var(flat_noise)

# ==========================================
# --- 3. THE MASTER ROUTING PIPELINE ---
# ==========================================
def master_inference_pipeline(image_path, ai_model, noise_threshold=8.0):
    print(f"\nProcessing Image: {image_path}")
    
    # ---------------------------------------------------------
    # NEW: SMART FILE READER (Handles DICOM and Normal Images)
    # ---------------------------------------------------------
    if image_path.lower().endswith('.dcm') or image_path.lower().endswith('.dicom'):
        # 1. Read the DICOM file
        dicom_data = pydicom.dcmread(image_path)
        
        # 2. Extract the raw 16-bit pixel array
        pixel_array = dicom_data.pixel_array.astype(float)
        
        # 3. Normalize to 0-255 (8-bit) for our AI model
        pixel_array = (np.maximum(pixel_array, 0) / pixel_array.max()) * 255.0
        raw_img = np.uint8(pixel_array)
        
        # 4. DICOM Inversion Fix (Some X-rays are stored with black bones. We fix that here).
        if hasattr(dicom_data, 'PhotometricInterpretation') and dicom_data.PhotometricInterpretation == "MONOCHROME1":
            raw_img = cv2.bitwise_not(raw_img)
    else:
        # Fallback to standard OpenCV for PNG/JPG
        raw_img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        
    if raw_img is None:
        raise ValueError("Image could not be loaded. Check the file path.")
    # ---------------------------------------------------------
        
    h, w = raw_img.shape
    
    # 1. Analyze the Physics of the Image
    noise_variance = detect_noise_level(raw_img)
    print(f"Calculated Noise Variance: {noise_variance:.2f}")
    
    # 2. THE ROUTER
    if noise_variance > noise_threshold:
        routing_message = f"PATH A: Heavy scatter detected (Var: {noise_variance:.1f}). AI Denoising Engaged."
        print(routing_message)
        
        pad_h = (256 - h % 256) % 256
        pad_w = (256 - w % 256) % 256
        padded_img = np.pad(raw_img, ((0, pad_h), (0, pad_w)), mode='reflect')
        new_h, new_w = padded_img.shape

        denoised_padded = np.zeros_like(padded_img, dtype=np.float32)
        
        for i in range(0, new_h, 256):
            for j in range(0, new_w, 256):
                patch = padded_img[i:i+256, j:j+256] / 255.0
                patch_input = np.expand_dims(patch, axis=(0, -1)) 
                prediction = ai_model.predict(patch_input, verbose=0)[0, :, :, 0]
                denoised_padded[i:i+256, j:j+256] = prediction

        denoised_float = denoised_padded[:h, :w]
        unet_output = np.clip(denoised_float * 255.0, 0, 255).astype(np.uint8)

        residual_map = cv2.absdiff(raw_img, unet_output)
        _, pure_noise = cv2.threshold(residual_map, 4, 255, cv2.THRESH_TOZERO)
        residual_visual = np.clip(pure_noise * 4, 0, 255).astype(np.uint8)
        
    else:
        routing_message = f"PATH B: Clean digital scan detected (Var: {noise_variance:.1f}). AI Bypassed to preserve bones."
        print(routing_message)
        
        unet_output = raw_img.copy()
        residual_visual = np.zeros_like(raw_img)

    # 3. Deterministic OpenCV Enhancement (Happens for BOTH paths)
    print("Applying Global Clinical Enhancement...")
    # Using your softened contrast settings!
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(8, 8))
    contrast_enhanced = clahe.apply(unet_output)
    
    smoothed = cv2.GaussianBlur(contrast_enhanced, (5, 5), 1.0)
    final_output = cv2.addWeighted(contrast_enhanced, 1.1 , smoothed, -0.2, 0)
    
    return raw_img, unet_output, residual_visual, final_output, routing_message

# ==========================================
# --- 4. RUN AND VISUALIZE ---
# ==========================================
raw_image, unet_image, residual_map, final_image, status_msg = master_inference_pipeline(TEST_IMAGE_PATH, model, noise_threshold=8.0)

plt.figure(figsize=(24, 7))
plt.suptitle(status_msg, fontsize=18, fontweight='bold', color='blue')

plt.subplot(1, 4, 1)
plt.title("1. Original Raw Input", fontsize=14)
plt.imshow(raw_image, cmap='gray')
plt.axis('off')

plt.subplot(1, 4, 2)
plt.title("2. What the AI Removed (Noise Map)", fontsize=14, color='red')
plt.imshow(residual_map, cmap='gray') 
plt.axis('off')

plt.subplot(1, 4, 3)
plt.title("3. AI Denoised (U-Net Only)", fontsize=14)
plt.imshow(unet_image, cmap='gray')
plt.axis('off')

plt.subplot(1, 4, 4)
plt.title("4. Final Clinical Output", fontsize=14, color='green')
plt.imshow(final_image, cmap='gray')
plt.axis('off')

plt.tight_layout()
plt.show()