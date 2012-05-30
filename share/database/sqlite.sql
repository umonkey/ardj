-- плейлисты
CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, name TEXT, last_played INTEGER);

-- композиции
CREATE TABLE IF NOT EXISTS tracks (id INTEGER PRIMARY KEY, owner TEXT, filename TEXT, artist TEXT, title TEXT, length INTEGER, weight REAL, real_weight REAL, count INTEGER, last_played INTEGER, image TEXT, download TEXT);
CREATE INDEX IF NOT EXISTS idx_tracks_owner ON tracks (owner);
CREATE INDEX IF NOT EXISTS idx_tracks_last ON tracks (last_played);
CREATE INDEX IF NOT EXISTS idx_tracks_count ON tracks (count);
CREATE INDEX IF NOT EXISTS idx_tracks_weight ON tracks (weight);
CREATE INDEX IF NOT EXISTS idx_tracks_real_weight ON tracks (real_weight);
CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY, track_id INTEGER, owner TEXT);

-- экстренный плейлист
CREATE TABLE IF NOT EXISTS urgent_playlists (labels TEXT, expires INTEGER);
CREATE INDEX IF NOT EXISTS urgent_playlists_expires ON urgent_playlists (expires);

-- метки
CREATE TABLE IF NOT EXISTS labels (track_id INTEGER NOT NULL, email TEXT NOT NULL, label TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_labels_track_id ON labels (track_id);
CREATE INDEX IF NOT EXISTS idx_labels_email ON labels (email);
CREATE INDEX IF NOT EXISTS idx_labels_label ON labels (label);

-- голоса пользователей
CREATE TABLE IF NOT EXISTS votes (track_id INTEGER NOT NULL, email TEXT NOT NULL, vote INTEGER, weight REAL, ts INTEGER);
CREATE INDEX IF NOT EXISTS idx_votes_track_id ON votes (track_id);
CREATE INDEX IF NOT EXISTS idx_votes_email ON votes (email);
CREATE INDEX IF NOT EXISTS idx_votes_ts ON votes (ts);

-- карма
CREATE TABLE IF NOT EXISTS karma (email TEXT, weight REAL);
CREATE INDEX IF NOT EXISTS idx_karma_email ON karma (email);

-- лог проигрываний
CREATE TABLE IF NOT EXISTS playlog (ts INTEGER NOT NULL, track_id INTEGER NOT NULL, listeners INTEGER NOT NULL, lastfm INTEGER NOT NULL DEFAULT 0, librefm INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_playlog_ts ON playlog (ts);
CREATE INDEX IF NOT EXISTS idx_playlog_track_id ON playlog (track_id);

-- исходящие сообщения
CREATE TABLE IF NOT EXISTS jabber_messages (id INTEGER PRIMARY KEY, re TEXT, message TEXT);

-- музыка для загрузки
CREATE TABLE IF NOT EXISTS download_queue (artist TEXT PRIMARY KEY, owner TEXT);

-- токены аутентификации
CREATE TABLE IF NOT EXISTS tokens (token TEXT PRIMARY KEY NOT NULL, login TEXT NOT NULL, login_type TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0);
