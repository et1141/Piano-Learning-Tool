import sqlite3

def init_db():
    conn = sqlite3.connect('songs.db')
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS songs (
        song_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        audio_path TEXT NOT NULL,
        source TEXT,  
        picture_path TEXT,
        original_key_root TEXT,
        original_key_mode TEXT,
        uploaded_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS song_versions (
        version_id INTEGER PRIMARY KEY AUTOINCREMENT,
        song_id INTEGER NOT NULL,
        model_name TEXT NOT NULL,
        key_root TEXT,
        key_mode TEXT,
        instrument TEXT, 
        filename TEXT,  
        duration REAL,
        midi_path TEXT,
        pdf_path TEXT,
        musicxml_path TEXT,
        video_path TEXT,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_public INTEGER DEFAULT 0,
        FOREIGN KEY (song_id) REFERENCES songs(song_id),
        UNIQUE(song_id, model_name, key_root,key_mode,instrument)
    )
    ''')

    conn.commit()
    conn.close()
    print("Database initialized.")


def migrate_db():
    conn = sqlite3.connect('songs.db')
    c = conn.cursor()

   # try:
   #     c.execute('ALTER TABLE songs ADD COLUMN source TEXT')
   # except sqlite3.OperationalError:
   #     pass

   # try:
   #     c.execute('ALTER TABLE song_versions ADD COLUMN filename TEXT')
   # except sqlite3.OperationalError:
   #     pass

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    init_db()
 #   migrate_db()
