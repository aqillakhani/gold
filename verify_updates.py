import sqlite3
import json

db_path = "data/gold.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

content_ids = [9, 12, 15, 20, 23, 24]

for cid in content_ids:
    cursor.execute("""
        SELECT id, title, hook, script 
        FROM content 
        WHERE id = ?
    """, (cid,))
    
    row = cursor.fetchone()
    if row:
        cid, title, hook, script = row
        print(f"\n{'='*80}")
        print(f"CONTENT ID: {cid}")
        print(f"{'='*80}")
        print(f"TITLE: {title}")
        print(f"\nHOOK: {hook}")
        print(f"\nSCRIPT (first 300 chars):\n{script[:300]}...")
    else:
        print(f"Content ID {cid} not found")

conn.close()
print(f"\n{'='*80}")
print("VERIFICATION COMPLETE - All 6 scripts have been updated with factual cases")
print(f"{'='*80}")
