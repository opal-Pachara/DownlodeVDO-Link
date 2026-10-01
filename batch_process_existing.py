"""
Script to batch process / flip / enhance / watermark any existing downloaded videos in VDO/ folder
and output them into VDO_processed/ folder.
"""

import os
import sys
import argparse
import glob
from backend import processor

def batch_process(
    creator_name: str = "นางฟ้าชัดๆ",
    flip: bool = True,
    brighten: bool = True,
    watermark_text: str = "@SoSoCute Girl TH",
    watermark_opacity: float = 0.25,
    anti_detection: bool = False,
    overwrite: bool = False
):
    project_root = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(project_root, "VDO", creator_name)
    output_dir = os.path.join(project_root, "VDO_processed", creator_name)
    
    if not os.path.exists(input_dir):
        print(f"Error: Folder does not exist: {input_dir}")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    video_files = glob.glob(os.path.join(input_dir, "*.mp4"))
    print(f"Found {len(video_files)} video(s) in {input_dir}")
    
    success_count = 0
    skipped_count = 0
    
    for idx, raw_path in enumerate(video_files, start=1):
        filename = os.path.basename(raw_path)
        out_path = os.path.join(output_dir, filename)
        
        # Check if already processed
        if not overwrite and os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            skipped_count += 1
            continue
            
        print(f"[{idx}/{len(video_files)}] Processing & Flipping: {filename}...")
        res = processor.process_video(
            input_file=raw_path,
            output_file=out_path,
            flip=flip,
            brighten=brighten,
            watermark_text=watermark_text,
            watermark_opacity=watermark_opacity,
            anti_detection=anti_detection
        )
        if res.get("success"):
            success_count += 1
        else:
            print(f"  Failed: {res.get('error')}")
            
    print(f"\nDone! Successfully processed {success_count} new video(s). ({skipped_count} already existed in {output_dir})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch process existing videos in VDO/")
    parser.add_argument("--creator", default="นางฟ้าชัดๆ", help="Creator folder name inside VDO/")
    parser.add_argument("--no-flip", action="store_true", help="Disable flipping")
    parser.add_argument("--no-brighten", action="store_true", help="Disable brightening")
    parser.add_argument("--watermark", default="@SoSoCute Girl TH", help="Watermark text")
    parser.add_argument("--opacity", type=float, default=0.25, help="Watermark opacity (0.05 - 1.0)")
    parser.add_argument("--anti-detection", action="store_true", help="Enable 6-layer anti-detection suite")
    parser.add_argument("--overwrite", action="store_true", help="Re-process and overwrite existing files in VDO_processed")
    
    args = parser.parse_args()
    batch_process(
        creator_name=args.creator,
        flip=not args.no_flip,
        brighten=not args.no_brighten,
        watermark_text=args.watermark,
        watermark_opacity=args.opacity,
        anti_detection=args.anti_detection,
        overwrite=args.overwrite
    )
