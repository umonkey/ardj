import ardj
import ardj.settings

def get_used_labels():
    used_labels = []
    for playlist in ardj.Open().config.get_playlists():
        if 'labels' in playlist:
            labels = playlist['labels']
        else:
            labels = [playlist['name']]
        used_labels += [l for l in labels if not l.startswith('-')]
    return list(set(used_labels))

def process_labels(labels, set_label='orphan', quiet=False):
    if not labels:
        return []

    db = ardj.Open().database
    cur = db.cursor()

    cur.execute('DELETE FROM labels WHERE label = ?', (set_label, ))

    sql = 'SELECT id, artist, title FROM tracks WHERE id NOT IN (SELECT track_id FROM labels WHERE label IN (%s)) ORDER BY artist, title' % ', '.join(['?'] * len(labels))
    cur.execute(sql, labels)
    rows = cur.fetchall()

    if rows:
        print '%u orphan tracks found:' % len(rows)
        for row in rows:
            print '%8u; %s -- %s' % (row[0], row[1].encode('utf-8'), row[2].encode('utf-8'))
            cur.execute('INSERT INTO labels (track_id, email, label) VALUES (?, ?, ?)', (int(row[0]), 'ardj@googlecode.com', set_label))

    db.commit()

def mark(args=None, quiet=False):
    """Marks tracks that don't belong to a playlist."""
    labels = get_used_labels()
    process_labels(labels, quiet=quiet)
