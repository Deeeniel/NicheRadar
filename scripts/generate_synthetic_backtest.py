import json
import sqlite3
import random
from datetime import datetime, timedelta
import uuid
import os

DB_PATH = "logs/synthetic_backtest.sqlite"
SETTLEMENTS_PATH = "data/synthetic_settlements.json"

PROFILES = ["music_release", "product_release", "ipo_event", "default_content"]

def reset_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE watchlist_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT,
                slug TEXT,
                market_id TEXT,
                raw_json TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE shadow_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT,
                side TEXT,
                slug TEXT,
                fill_price REAL,
                raw_json TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE shadow_marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fill_id INTEGER,
                timestamp_utc TEXT,
                mark_price REAL,
                raw_json TEXT NOT NULL
            );
        """)

def generate_data():
    reset_db()
    
    settlements = []
    
    now = datetime.utcnow()
    
    with sqlite3.connect(DB_PATH) as conn:
        for i in range(1, 101):
            profile = random.choice(PROFILES)
            slug = f"synthetic-{profile}-{i}"
            market_id = f"mkt-{uuid.uuid4().hex[:8]}"
            timestamp = (now - timedelta(days=random.randint(10, 100))).isoformat() + "Z"
            
            # Simulate Brier correlations: true positives usually have high evidence AND high edge.
            yes_mid = random.uniform(0.1, 0.9)
            no_mid = 1.0 - yes_mid
            
            # Good models: if it resolved YES, the p_model was usually high.
            resolving_yes = random.random() > 0.5
            if resolving_yes:
                p_model = min(0.99, yes_mid + random.uniform(0.01, 0.15))
            else:
                p_model = max(0.01, yes_mid - random.uniform(0.01, 0.15))
                
            side = "BUY_YES" if p_model > yes_mid else "BUY_NO"
            edge = abs(p_model - yes_mid)
            net_edge = max(0.0, edge - 0.02)
            
            # Realistic profile logic: Product delays trigger BUY_NO strongly.
            event_type = "ipo_event" if profile == "ipo_event" else "content_release"
            
            snapshot = {
                "slug": slug,
                "timestamp_utc": timestamp,
                "market_id": market_id,
                "model_side": side,
                "preferred_side": None,
                "event_type": event_type,
                "platform": "generic",
                "title": f"Will {slug} happen?",
                "p_model": p_model,
                "p_mid": yes_mid if side == "BUY_YES" else no_mid,
                "net_edge": net_edge,
                "evidence_score": random.uniform(0.4, 0.9),
                "evidence_preheat_score": random.uniform(0.1, 0.9),
                "evidence_cadence_score": random.uniform(0.1, 0.9),
                "evidence_partner_score": random.uniform(0.1, 0.9),
                "yes_mid": yes_mid,
                "no_mid": no_mid,
                "signal_reasons_detail": [f"model_profile={profile}"]
            }
            
            # Insert Snapshot
            conn.execute(
                "INSERT INTO watchlist_snapshots (timestamp_utc, slug, market_id, raw_json) VALUES (?, ?, ?, ?)",
                (timestamp, slug, market_id, json.dumps(snapshot))
            )
            
            fill_eligible = net_edge > 0.03
            if fill_eligible:
                fill_price = (yes_mid if side == "BUY_YES" else no_mid) + 0.01
                fill_json = {"snapshot_timestamp_utc": timestamp}
                cursor = conn.execute(
                    "INSERT INTO shadow_fills (timestamp_utc, side, slug, fill_price, raw_json) VALUES (?, ?, ?, ?, ?)",
                    (timestamp, side, slug, fill_price, json.dumps(fill_json))
                )
                fill_id = cursor.lastrowid
                
                # Mock a recent shadow mark
                mark_price = fill_price + random.uniform(-0.1, 0.1)
                conn.execute(
                    "INSERT INTO shadow_marks (fill_id, timestamp_utc, mark_price, raw_json) VALUES (?, ?, ?, ?)",
                    (fill_id, timestamp, mark_price, "{}")
                )
            
            # Settlement outcome
            settlements.append({
                "slug": slug,
                "winning_side": "BUY_YES" if resolving_yes else "BUY_NO",
                "settled_at_utc": now.isoformat() + "Z"
            })
            
    with open(SETTLEMENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(settlements, f, indent=2)
        
    print(f"Generated 100 synthetic markets with settlements at {SETTLEMENTS_PATH}")
    print(f"Database created at {DB_PATH}")

if __name__ == "__main__":
    generate_data()
