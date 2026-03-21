import sqlite3

conn = sqlite3.connect("library.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    password TEXT,
    role TEXT
)
""")

cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin', 'admin')")
cursor.execute("INSERT INTO users (username, password, role) VALUES ('user', 'user', 'user')")

conn.commit()
conn.close()

print("Users added")
