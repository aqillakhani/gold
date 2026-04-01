#!/usr/bin/env python3

import os
import subprocess
import re
from pathlib import Path
from collections import defaultdict
import sys

FFmpeg_PATH = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
CLIPS_DIR = r"C:\Users\claws\OneDrive\Desktop\gold\data\media\clips"

ffprobe_exe = os.path.join(FFmpeg_PATH, "ffprobe.exe")
ffmpeg_exe = os.path.join(FFmpeg_PATH, "ffmpeg.exe")

results = []
error_count = 0
processed_count = 0

clip_files = sorted(Path(CLIPS_DIR).glob("*.mp4"))
total_files = len(clip_files)

print(f"Found {total_files} MP4 files to analyze...", file=sys.stderr)
sys.stderr.flush()

for clip_path in clip_files:
    processed_count += 1
    file_name = clip_path.name
    
    if processed_count % 50 == 0:
        print(f"Processing {processed_count}/{total_files}...", file=sys.stderr, flush=True)
    
    try:
        # Get duration
        result = subprocess.run(
            [ffprobe_exe, "-v", "error", "-select_streams", "v:0", 
             "-show_entries", "format=duration", "-of", "csv=p=0", str(clip_path)],
            capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL
        )
        
        duration_output = result.stdout.strip()
        if not duration_output:
            error_count += 1
            continue
        
        duration = float(duration_output)
        midpoint = int(duration / 2)
        
        # Run ffmpeg with -y flag to auto-answer prompts
        result = subprocess.run(
            [ffmpeg_exe, "-y", "-ss", str(midpoint), "-i", str(clip_path),
             "-frames:v", "1", "-vf", "signalstats,metadata=print:file=-",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL
        )
        
        ffmpeg_output = result.stderr + result.stdout
        
        yavg_matches = re.findall(r"lavfi\.signalstats\.YAVG=([\d\.]+)", ffmpeg_output)
        
        if yavg_matches:
            yavg_value = float(yavg_matches[-1])
            
            content_id = ""
            if match := re.match(r"^content_(\d+)_stock", file_name):
                content_id = f"content_{match.group(1)}"
            elif match := re.match(r"^test_([a-z_]+)_", file_name):
                content_id = f"test_{match.group(1)}"
            else:
                content_id = file_name.split("_")[0]
            
            results.append({
                "filename": file_name,
                "content_id": content_id,
                "yavg": yavg_value,
                "too_bright": yavg_value > 200
            })
    
    except Exception as e:
        error_count += 1
        continue

results_sorted = sorted(results, key=lambda x: x["yavg"], reverse=True)

print("\n" + "="*80)
print("=== ALL CLIPS (Sorted by YAVG descending) ===")
print("="*80)
print(f"{'Filename':<50} {'ContentID':<20} {'YAVG':<10} {'TooBright':<10}")
print("-"*90)
for r in results_sorted:
    too_bright = "YES" if r["too_bright"] else "NO"
    print(f"{r['filename']:<50} {r['content_id']:<20} {r['yavg']:<10.2f} {too_bright:<10}")

print("\n" + "="*80)
print("=== CLIPS WITH YAVG > 160 (HIGHLIGHT) ===")
print("="*80)
highlight = [r for r in results_sorted if r["yavg"] > 160]
if highlight:
    print(f"{'Filename':<50} {'ContentID':<20} {'YAVG':<10}")
    print("-"*80)
    for r in highlight:
        print(f"{r['filename']:<50} {r['content_id']:<20} {r['yavg']:<10.2f}")
else:
    print("No clips with YAVG > 160")

print("\n" + "="*80)
print("=== GROUPED BY CONTENT_ID ===")
print("="*80)
grouped = defaultdict(list)
for r in results_sorted:
    grouped[r["content_id"]].append(r)

grouped_sorted = sorted(grouped.items(), 
                       key=lambda x: sum(r["yavg"] for r in x[1]) / len(x[1]), 
                       reverse=True)

for content_id, clips in grouped_sorted:
    avg_yavg = sum(r["yavg"] for r in clips) / len(clips)
    print(f"\nContent: {content_id} | Count: {len(clips)} | Avg YAVG: {avg_yavg:.2f}")
    print(f"{'  Filename':<50} {'YAVG':<10} {'TooBright':<10}")
    print("-"*70)
    for r in clips:
        too_bright = "YES" if r["too_bright"] else "NO"
        print(f"  {r['filename']:<48} {r['yavg']:<10.2f} {too_bright:<10}")

print("\n" + "="*80)
print("=== SUMMARY ===")
print("="*80)
print(f"Total clips analyzed: {len(results)}")
print(f"Clips with YAVG > 200 (TOO BRIGHT): {sum(1 for r in results if r['too_bright'])}")
print(f"Clips with YAVG > 160 (WARNING): {sum(1 for r in results if r['yavg'] > 160)}")
print(f"Processing errors: {error_count}")
