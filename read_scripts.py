import sqlite3
import json

db_path = "data/gold.db"
content_ids = [9, 12, 15, 20, 23, 24]

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

for cid in content_ids:
    cursor.execute("""
        SELECT id, title, hook, script, scene_descriptions 
        FROM content 
        WHERE id = ?
    """, (cid,))
    
    row = cursor.fetchone()
    if row:
        cid, title, hook, script, scene_descriptions = row
        print(f"\n{'='*80}")
        print(f"CONTENT ID: {cid}")
        print(f"{'='*80}")
        print(f"TITLE: {title}")
        print(f"\nHOOK:\n{hook}")
        print(f"\nSCRIPT:\n{script}")
        print(f"\nSCENE DESCRIPTIONS:\n{scene_descriptions}")
    else:
        print(f"Content ID {cid} not found")

conn.close()
