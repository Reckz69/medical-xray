# CPU baseline — denoising pipeline

- Date: 2026-08-04 22:03 UTC
- Git commit: `2940a51`
- Weights: `n2n_unet_best_weights04.keras`
- Runs per image: 3 timed (+ 1 warmup)

## Environment

- Host: Narendra-ka-MacBook-Air.local (arm64)
- CPU: Apple M2
- Logical cores: 8
- Python: 3.11.15
- TensorFlow: 2.21.0

## Per-image results (ms)

| metric | dataset_x-ray1.png | foot_friend_x-ray.jpeg | low_nosie_dicom.dicom | high_noise_dicom.dicom |
|---|---|---|---|---|
| conversion_ms | 7.3 (p50 7.4) | 1.9 (p50 2.2) | 1,394.9 (p50 1,406.8) | 1,163.3 (p50 1,188.2) |
| preprocessing_ms | 2.8 (p50 2.8) | 2.6 (p50 3.0) | 16.3 (p50 17.7) | 15.5 (p50 17.3) |
| inference_ms | 0.2 (p50 0.2) | 0.2 (p50 0.2) | 0.4 (p50 0.4) | 26,435.3 (p50 26,741.1) |
| postprocessing_ms | 1.0 (p50 1.1) | 0.9 (p50 1.2) | 5.3 (p50 6.7) | 6.8 (p50 7.2) |
| encode_ms | 23.0 (p50 23.3) | 17.2 (p50 17.3) | 125.8 (p50 126.1) | 169.1 (p50 169.3) |
| total_ms | 34.6 (p50 34.8) | 22.9 (p50 24.2) | 1,542.6 (p50 1,560.8) | 27,823.2 (p50 28,123.2) |

## Routing per image

| image | width x height | routing | noise_variance |
|---|---|---|---|
| dataset_x-ray1.png | 1024x1024 | PATH B (bypassed) | 1.0 |
| foot_friend_x-ray.jpeg | 859x970 | PATH B (bypassed) | 1.1 |
| low_nosie_dicom.dicom | 2345x2584 | PATH B (bypassed) | 3.9 |
| high_noise_dicom.dicom | 2217x2463 | PATH A (AI engaged) | 8.1 |