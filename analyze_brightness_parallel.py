#!/usr/bin/env python3

import os
import json
import subprocess
import re
import sys
from pathlib import Path
from collections import defaultdict
from multiprocessing import Pool, cpu_count
from functools import partial

FFmpeg_PATH = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
CLIPS_DIR = r"C:\Users\claws\OneDrive\Desktop\gold\data\media\clips"

ffprobe_exe = os.path.join(FFmpeg_PATH, "ffprobe.exe")
ffmpeg_exe = os.path.join(FFmpeg_PATH, "ffmpeg.exe")

def analyze_clip(clip_path):
    """Analyze a single clip and return result or None on error."""
    file_name = clip_path.name
    
    try:
        # Get duration using ffprobe
        duration_cmd = [ffprobe_exe, "-v", "error", "-select_streams", "v:0", 
                       "-show_entries", "format=duration", "-of", "csv=p=0", str(clip_path)]
        result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
        duration_output = result.stdout.strip()
        
        if not duration_output:
            return None
        
        try:
            duration = float(duration_output)
        except ValueError:
            return None
        
        midpoint = int(duration / 2)
        
        # Get YAVG from signalstats - with stdin=subprocess.DEVNULL to prevent blocking
        ffmpeg_cmd = [ffmpeg_exe, "-y", "-ss", str(midpoint), "-i", str(clip_path),
                     "-t", "0.5", "-vf", "signalstats,metadata=print:file=-",
                     "-f", "null", "-"]
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, 
                              stdin=subprocess.DEVNULL, timeout=60)
        ffmpeg_output = result.stderr + result.stdout
        
        # Parse YAVG value
        yavg_matches = re.findall(r"lavfi\.signalstats\.YAVG=([\d\.]+)", ffmpeg_output)
        
        if yavg_matches:
            yavg_value = float(yavg_matches[-1])
            
            # Extract content_ID
            content_id = ""
            if match := re.match(r"^content_(\d+)_stock", file_name):
                content_id = f"content_{match.group(1)}"
            elif match := re.match(r"^test_([a-z_]+)_", file_name):
                content_id = f"test_{match.group(1)}"
            else:
                content_id = file_name.split("_")[0]
            
            return {
                "filename": file_name,
                "content_id": content_id,
                "yavg": yavg_value,
                "too_bright": yavg_value > 200
            }
    
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        return None
    
    return None

def main():
    # Get all MP4 files
    clip_files = sorted(Path(CLIPS_DIR).glob("*.mp4"))
    total_files = len(clip_files)
    
    print(f"Found {total_files} MP4 files to analyze...", file=sys.stderr, flush=True)
    print(f"Using {cpu_count()} processes...", file=sys.stderr, flush=True)
    
    # Process clips in parallel
    results = []
    error_count = 0
    
    with Pool(processes=cpu_count()) as pool:
        for i, result in enumerate(pool.imap_unordered(analyze_clip, clip_files, chunksize=10)):
            if (i + 1) % 50 == 0:
                print(f"Processed {i+1}/{total_files}...", file=sys.stderr, flush=True)
            
            if result is not None:
                results.append(result)
            else:
                error_count += 1
    
    # Sort by YAVG descending
    results_sorted = sorted(results, key=lambda x: x["yavg"], reverse=True)
    
    # Print all clips
    print("\n" + "="*80)
    print("=== ALL CLIPS (Sorted by YAVG descending) ===")
    print("="*80)
    print(f"{'Filename':<50} {'ContentID':<20} {'YAVG':<10} {'TooBright':<10}")
    print("-"*90)
    for r in results_sorted:
        too_bright = "YES" if r["too_bright"] else "NO"
        print(f"{r['filename']:<50} {r['content_id']:<20} {r['yavg']:<10.2f} {too_bright:<10}")
    
    # Highlight clips > 160
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
    
    # Group by content_ID
    print("\n" + "="*80)
    print("=== GROUPED BY CONTENT_ID ===")
    print("="*80)
    grouped = defaultdict(list)
    for r in results_sorted:
        grouped[r["content_id"]].append(r)
    
    # Sort groups by average YAVG
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
    
    # Summary
    print("\n" + "="*80)
    print("=== SUMMARY ===")
    print("="*80)
    print(f"Total clips analyzed: {len(results)}")
    print(f"Clips with YAVG > 200 (TOO BRIGHT): {sum(1 for r in results if r['too_bright'])}")
    print(f"Clips with YAVG > 160 (WARNING): {sum(1 for r in results if r['yavg'] > 160)}")
    print(f"Processing errors: {error_count}")

if __name__ == "__main__":
    main()
