# Video Fingerprint Robustness Research

> **Research Notice:** This project is **strictly for research, benchmarking, and algorithm evaluation only**. It must not be used to evade, bypass, defeat, or interfere with copyright enforcement, Rights Manager, Content ID, platform moderation, or content-identification systems in production.

---

## Research Question

**How robust is a perceptual-hash video fingerprinting algorithm against controlled transformations?**

Specifically:
- Which classes of controlled transformations cause the largest degradation in fingerprint similarity?
- Are transformation effects on detection additive, multiplicative, or independent?
- At what transformation magnitude does detection reliability fall below a practical threshold?

---

## Hypothesis

1. **Small transformations** (e.g., ≤5% crop, ±3% brightness) should have limited effect on perceptual similarity scores.
2. **Temporal transformations** (trimming, speed changes) will reduce similarity proportionally to the amount of temporal displacement.
3. **Spatial transformations** (cropping, scaling) will reduce similarity more aggressively than color adjustments.
4. **Color adjustments** alone will have the least impact on perceptual hashing, since aHash is grayscale-based.
5. **Audio modifications** will have no effect on visual fingerprint similarity (but would affect an audio-based fingerprint).
6. **Combined transformations** will show compounding effects, but not necessarily multiplicative.
7. **Metadata removal** will have zero effect on content-based fingerprinting.

---

## Variables

### Independent Variables

| Variable | Layer | Range |
|----------|-------|-------|
| Temporal trim (start) | Layer 1 | 0.5s, 1.0s, 1.5s, 2.0s |
| Temporal trim (end) | Layer 1 | 0.5s, 1.0s, 1.5s, 2.0s |
| Playback speed | Layer 1 | 0.97x, 0.98x, 1.02x, 1.03x |
| Crop percentage | Layer 2 | 5%, 10%, 15%, center |
| Aspect ratio | Layer 2 | 16:9 → 9:16 |
| Resolution scale | Layer 2 | 720p, 1080p |
| Contrast | Layer 3 | ±4% |
| Saturation | Layer 3 | ±5% |
| Brightness | Layer 3 | ±3% |
| Gamma | Layer 3 | 0.9, 1.1 |
| Sharpening | Layer 3 | mild |
| Blur | Layer 3 | mild |
| Audio presence | Layer 4 | original, removed, replaced |
| Overlay size | Layer 5 | 5%, 10%, 15% |
| Overlay type | Layer 5 | text, logo, banner |
| Metadata presence | Layer 6 | preserved, removed |
| Combined transforms | Layer 7 | A, B, C, D |

### Dependent Variables

| Variable | Description |
|----------|-------------|
| Similarity Score | Perceptual hash similarity (0.0–1.0) |
| Detection Result | DETECTED / NOT_DETECTED (threshold-based) |
| Confidence | Normalized confidence metric |
| Processing Time | Time to compute fingerprint (ms) |
| False Negative | Original not detected (should not happen) |
| False Positive | Not applicable in same-source tests |

---

## Methodology

### Fingerprinting Algorithm

The research pipeline uses **Average Hash (aHash)** as the baseline perceptual fingerprint:

1. **Frame Sampling:** Extract N evenly-spaced frames from the video
2. **Thumbnail Generation:** Scale each frame to 16×16 pixels
3. **Grayscale Conversion:** Convert to single-channel grayscale
4. **Average Computation:** Calculate mean pixel intensity
5. **Binary Hash:** Each pixel → 1 if above average, 0 otherwise
6. **Hex Encoding:** Convert 256-bit binary string to 64-character hex

### Similarity Computation

- **Hamming Distance:** Count differing bits between two hashes
- **Best-Match Alignment:** For each test frame hash, find the closest match in the original set (handles temporal shifts)
- **Normalized Score:** `similarity = 1 - (hamming_distance / total_bits)`
- **Threshold:** Detection if similarity ≥ 0.75

### Transformation Generation

All transformations use FFmpeg with deterministic parameters. Each transformation produces one output file with a descriptive filename.

---

## Experimental Architecture

```
raw_video.mp4
    │
    ├── Layer 1: Temporal ────────── 12 variants
    │     ├── trim_start_0.5s..2.0s
    │     ├── trim_end_0.5s..2.0s
    │     └── speed_0.97x..1.03x
    │
    ├── Layer 2: Spatial ─────────── 7 variants
    │     ├── crop_5%..15%
    │     ├── center_crop
    │     ├── aspect_9x16
    │     └── scale_720p, 1080p
    │
    ├── Layer 3: Color ───────────── 10 variants
    │     ├── contrast ±4%
    │     ├── saturation ±5%
    │     ├── brightness ±3%
    │     ├── gamma 0.9, 1.1
    │     ├── sharpen, blur
    │     └── combined
    │
    ├── Layer 4: Audio ───────────── 5 variants
    │     ├── original, removed
    │     ├── synthetic_speech
    │     ├── test_tone
    │     └── multitone
    │
    ├── Layer 5: Overlay ─────────── 6 variants
    │     ├── text 5%, 10%, 15%
    │     ├── small_logo
    │     ├── semi_transparent_rect
    │     └── top_banner
    │
    ├── Layer 6: Metadata ────────── 2 variants
    │     ├── original
    │     └── removed
    │
    └── Layer 7: Combined ────────── 4 variants
          ├── A: trim + crop + contrast
          ├── B: trim + speed + overlay
          ├── C: aspect + audio + metadata
          └── D: all combined
```

**Total: ~47 experimental variants** (exact count depends on source video duration)

---

## Output Structure

```
experiments/
├── original/
│   └── original.mp4
├── temporal/
│   ├── temporal_trim_start_0.5s.mp4
│   ├── temporal_trim_start_1.0s.mp4
│   ├── ...
│   └── temporal_speed_1.03x.mp4
├── spatial/
│   ├── spatial_crop_5pct.mp4
│   └── ...
├── color/
│   ├── color_contrast_1.04.mp4
│   └── ...
├── audio/
│   ├── audio_original.mp4
│   ├── audio_removed.mp4
│   └── ...
├── overlay/
│   ├── overlay_5pct.mp4
│   └── ...
├── metadata/
│   ├── metadata_original.mp4
│   └── metadata_removed.mp4
├── combined/
│   ├── combined_A_trim1s_crop5_contrast.mp4
│   └── ...
├── experiment_matrix.csv
├── evaluation_results.csv
├── research_summary.json
└── research_dashboard.html
```

---

## Reproducibility

Every experiment records:

| Field | Description |
|-------|-------------|
| `experiment_id` | Unique deterministic identifier |
| `source_file` | Path to input video |
| `ffmpeg_command` | Exact FFmpeg command used |
| `transformation_parameters` | JSON-encoded parameters |
| `source_hash` | SHA-256 of input file |
| `output_file` | Path to generated variant |
| `timestamp` | ISO 8601 generation timestamp |
| `ffmpeg_version` | FFmpeg version string |
| `python_version` | Python version string |

---

## Running the Experiment

### Prerequisites

- Python 3.10+
- FFmpeg 5.0+ (with libx264)

### Quick Start

```bash
# Place your test video as raw_video.mp4
python3 video_fingerprint_research.py

# Or specify a custom input file
python3 video_fingerprint_research.py my_test_video.mp4
```

### Output

1. **`experiments/`** — All generated variants organized by category
2. **`experiment_matrix.csv`** — Complete metadata for every variant
3. **`evaluation_results.csv`** — Fingerprint comparison results
4. **`research_summary.json`** — Statistical summary in JSON
5. **`research_dashboard.html`** — Interactive visualization dashboard

---

## Ethical Considerations

### Permitted Uses

- ✅ Evaluating perceptual hashing algorithm robustness
- ✅ Benchmarking custom fingerprinting implementations
- ✅ Academic research on content identification
- ✅ Testing with user-owned or public-domain content
- ✅ Algorithm development and parameter tuning

### Prohibited Uses

- ❌ Targeting a specific platform's production detection system
- ❌ Attempting to bypass copyright enforcement
- ❌ Attempting to defeat Rights Manager or Content ID
- ❌ Uploading transformed copyrighted material to test evasion
- ❌ Recommending transformation parameters as an evasion recipe
- ❌ Optimizing transformations against a real platform's detector

---

## Expected Research Outcomes

The final analysis should answer:

> "Which classes of controlled transformations make the experimental fingerprinting algorithm less robust, and by how much?"

Rather than:

> "How can we make a video invisible to a platform's copyright detector?"

### Expected Findings

1. **Metadata removal** → zero effect on perceptual fingerprint
2. **Audio modification** → zero effect on visual fingerprint
3. **Mild color changes** → minimal effect (aHash is grayscale-insensitive to saturation)
4. **Small crops** → moderate effect (spatial displacement changes pixel positions)
5. **Temporal trimming** → proportional effect (offset frames reduce best-match overlap)
6. **Combined transformations** → compounding but sub-multiplicative effects
7. **Aspect ratio change** → significant effect (fundamentally alters frame geometry)

---

## References

1. Zauner, C. (2010). "Implementation and Benchmarking of Perceptual Image Hash Functions"
2. Hamming, R.W. (1950). "Error Detecting and Error Correcting Codes"
3. Coskun, B., Sankur, B., Memon, N. (2006). "Spatio-temporal transform based video hashing"
4. FFmpeg Documentation — https://ffmpeg.org/documentation.html

---

*Generated by Video Fingerprint Research Pipeline v1.0*
