"""Re-render multiple videos, each in an isolated subprocess to prevent memory buildup."""

import subprocess
import sys
import time

CONTENT_IDS = [7, 14, 15, 17, 18, 24]

def main():
    results = {}
    for cid in CONTENT_IDS:
        print(f"\n{'='*60}")
        print(f"  Re-rendering content_{cid} (isolated subprocess)")
        print(f"{'='*60}\n")
        start = time.time()
        proc = subprocess.run(
            [sys.executable, "scripts/rerender_one.py", str(cid)],
            cwd=r"C:\Users\claws\OneDrive\Desktop\gold",
            timeout=2400,  # 40 min max per video
        )
        elapsed = time.time() - start
        ok = proc.returncode == 0
        results[cid] = ok
        status = "OK" if ok else "FAILED"
        print(f"\n  content_{cid}: {status} ({elapsed:.0f}s)")

        # Brief pause between renders to let GPU memory fully release
        if cid != CONTENT_IDS[-1]:
            print("  Waiting 10s before next render...")
            time.sleep(10)

    print(f"\n{'='*60}")
    print("  RESULTS")
    print(f"{'='*60}")
    for cid, ok in results.items():
        print(f"  content_{cid}: {'OK' if ok else 'FAILED'}")
    success = sum(1 for ok in results.values() if ok)
    print(f"\n  {success}/{len(CONTENT_IDS)} rendered successfully")


if __name__ == "__main__":
    main()
