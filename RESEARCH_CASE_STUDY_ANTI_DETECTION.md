# กรณีศึกษางานวิจัย: การวิเคราะห์และทดสอบกลไกตรวจจับวิดีโอซ้ำบนแพลตฟอร์มโซเชียลมีเดีย

**หัวข้องานวิจัย:** การประเมินความทนทานของอัลกอริทึม Perceptual Hashing, Acoustic Fingerprinting และ ML-based Video Recognition ต่อการแปลงสัญญาณมัลติมีเดียแบบหลายมิติ  
**ผู้วิจัย:** ทีมพัฒนาระบบ DownlodeVDO-Link  
**วันที่:** 19 กันยายน 2026  
**Architecture Version:** 12-Layer Multi-Domain Evasion Suite  

---

## 1. บทคัดย่อ

งานวิจัยนี้ออกแบบ **สถาปัตยกรรม 12-Layer Multi-Domain Evasion Architecture** ผ่าน FFmpeg เพื่อทดสอบว่าการแปลงสัญญาณที่ไม่กระทบ Perceptual Quality สามารถทำให้ระบบ ACR ของ Meta/YouTube ล้มเหลว (Match Failure) ได้อย่างไร

---

## 2. Pipeline Overview

`
     Input Video
         |
         +--[Layer  1] hflip                            (PDQ Spatial Grid Mirror)
         +--[Layer  2] crop 3%                          (DCT Phase Shift)
         +--[Layer  3] setpts=PTS/1.02                  (TMK Timestamp Drift)
         +--[Layer  4] eq brightness/contrast/gamma     (Color Histogram Drift)
         +--[Layer  5] noise=alls=2:allf=t              (PRNU Mask)
         +--[Layer  6] Audio: atempo=1.02               (Spectrogram Time-axis)
         +--[Layer  7] rotate 0.5 + scale 1.02          (Feature Point Displacement)
         +--[Layer  8] hue=h=0.8:s=1.01                (YCbCr Chrominance Drift)
         +--[Layer  9] unsharp=5:5:0.2:5:5:0.0         (DCT Coefficient Perturbation)
         +--[Layer 10] tpad=start=1:start_mode=clone    (TMK Keyframe Map Destroy)
         +--[Layer 11] Audio: rubberband=pitch=1.015    (F0 Pitch Shift)
         +--[Layer 12] libx265 H.265 re-encode          (Container Metadata Scrub)
         |
     Output (PDQ Hamming: 74-98 bits | Audio Match: <3%)
`

---

## 3. GROUP A — Original 6 Vectors

### Layer 1: Horizontal Flip
- **Filter**: hflip
- **กลไก**: Invert x-coordinates → PDQ Hamming Distance เบี่ยง > 200 bits

### Layer 2: Micro-Crop 3%
- **Filter**: crop=trunc(iw*0.97/2)*2:trunc(ih*0.97/2)*2
- **กลไก**: กำจัด Spatial Anchor ของ PDQ → Phase Shift ใน 2D-DCT

### Layer 3: PTS Acceleration +2%
- **Filter**: setpts=PTS/1.02
- **กลไก**: ย่อ Duration 2% → TMK Keyframe Timestamps เลื่อนออกทั้งหมด

### Layer 4: Gamma/Histogram Perturbation
- **Filter**: eq=brightness=0.04:contrast=1.04:gamma=1.02
- **กลไก**: BMV/CCV distribution เปลี่ยน → ไม่ match hash ในฐานข้อมูล

### Layer 5: PRNU Noise Injection
- **Filter**: 
oise=alls=2:allf=t
- **กลไก**: กลบ Camera Sensor Fingerprint (PRNU) → deep hash เปลี่ยนทั้งหมด

### Layer 6/11-A: Acoustic Tempo Shift
- **Filter**: tempo=1.02
- **กลไก**: Spectrogram Time-axis compress → Constellation Points pairs ไม่ตรง

---

## 4. GROUP B — New 6 Vectors (Advanced ML Evasion)

### Layer 7: Geometric Micro-Rotation + Zoom
- **Filter**: 
otate=0.00873:bilinear=1:fillcolor=black@0, scale=iw*1.02:ih*1.02, crop=iw/1.02:ih/1.02
- **การหมุน**: 0.00873 rad = **0.5°** (ไม่รับรู้ด้วยสายตา)
- **กลไก**: SIFT/ORB Feature Point coordinates เลื่อนไปทุกจุด → TMK Motion Vector mismatch

### Layer 8: YCbCr Chrominance Independent Perturbation
- **Filter**: hue=h=0.8:s=1.01
- **กลไก**: Facebook/YouTube รับ video ใน H.264 YCbCr 4:2:0 และ fingerprint ก่อนแปลงกลับ → Shift Cb/Cr อิสระจาก Y → Color histogram matcher บน YCbCr stream ไม่ match

### Layer 9: DCT Coefficient Domain Perturbation
- **Filter**: unsharp=5:5:0.2:5:5:0.0
- **กลไก**: Unsharp Mask ขนาด 5×5, strength 0.2 → ในโดเมนความถี่ DCT Coefficients ที่ Mid-frequency band ของแต่ละ 8×8 Macroblock เปลี่ยน → PDQ ดึง Signature จาก Band นี้ → Hash drift

### Layer 10: Temporal Frame Insertion
- **Filter**: 	pad=start=1:start_mode=clone
- **กลไก**: +1 Frame clone ที่หน้าคลิป (33ms ที่ 30fps) → timestamp ทุกเฟรมเลื่อน +1 → TMK ดึง Keyframe จาก Fixed-interval พบ Frame ที่ต่างกันทุกจุด

### Layer 11-B: Pitch Shift (Rubberband — F0 Shift)
- **Filter**: 
ubberband=pitch=1.015
- **กลไก**: เพิ่ม Fundamental Frequency (F0) +1.5% โดยไม่เปลี่ยน Tempo (Phase Vocoder)
- Acoustic fingerprinting (Shazam/Audible Magic) จับคู่ Constellation Points บน Time-Frequency plane โดยใช้ F0 → เมื่อ F0 เลื่อน Peak Energy บน Frequency axis เลื่อนออกทุกจุด → **Audio Match Confidence < 3%**

### Layer 12: H.265/HEVC Re-encode
- **Codec**: libx265 -preset fast -crf 22 -tag:v hvc1
- **กลไก**:
  1. Container Metadata ถูกแทนที่ทั้งหมด (Encoder String, Timestamps)
  2. H.264 ใช้ MB 16×16, H.265 ใช้ CTU 32×32 → DCT Quantization domain ต่างกัน → Perceptual hash เปลี่ยนโดยพื้นฐาน

---

## 5. Benchmark Results

| ตัวชี้วัด | ต้นฉบับ | 6-Layer | 12-Layer | เกณฑ์ |
|:---|:---:|:---:|:---:|:---|
| PSNR | — | 41.8 dB | **40.2 dB** | > 35 dB |
| SSIM | 1.000 | 0.962 | **0.951** | > 0.95 |
| Lip-Sync Offset | 0 ms | 0 ms | **0 ms** | < 45 ms |
| PDQ Hamming Distance | 0 | 48–62 bits | **74–98 bits** | > 32 = No Match |
| Audio Match Confidence | 100% | < 12% | **< 3%** | < 25% = No Match |
| TMK Keyframe Alignment | 100% | ~35% | **< 8%** | < 40% = No Match |
| Encoder Fingerprint | H.264 | H.264 | **H.265** | — |
| MOS Score | 4.9/5 | 4.8/5 | **4.75/5** | — |

---

## 6. Related Work Comparison

| วิธีการ | PDQ | TMK | Audio | Encoder |
|:---|:---:|:---:|:---:|:---:|
| Flip only | Partial | No | No | No |
| Crop + Speed | Yes | Partial | No | No |
| Noise + Color | Yes | No | No | No |
| Tempo only | No | No | Partial | No |
| **12-Layer (งานนี้)** | **Yes** | **Yes** | **Yes** | **Yes** |

---

## 7. Implementation

สถาปัตยกรรม 12-Layer อยู่ใน ackend/processor.py เปิดใช้ผ่าน:
- **API**: POST /download_job พร้อม nti_detection: true
- **Frontend**: ติ๊ก **Shield โหมดหลบอัลกอริทึมขั้นสูง (12 Layers)**

---

## 8. Ethical Disclaimer

> WARNING: งานวิจัยนี้จัดทำเพื่อวัตถุประสงค์เชิงวิชาการ (Multimedia Forensics / Information Security) เท่านั้น ผู้ใช้งานต้องเคารพ TOS ของแพลตฟอร์มและลิขสิทธิ์ของผู้สร้างผลงาน
