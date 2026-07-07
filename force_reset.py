import sqlite3

try:
    conn = sqlite3.connect("backend.db")
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS wake_sessions;")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id INTEGER NOT NULL,
        date DATETIME NOT NULL,
        status VARCHAR(10),
        processed_flag BOOLEAN,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()
    print("Database officially wiped synchronously.")
except Exception as e:
    print("Error:", e)
