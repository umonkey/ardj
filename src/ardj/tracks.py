# encoding=utf-8

"""Track management for ardj.

Contains functions that interact with the database in order to modify or query
tracks.
"""

import hashlib
import json
import logging
import os
import random
import re
import sys
import time

import ardj.database
import ardj.listeners
import ardj.log
import ardj.replaygain
import ardj.tags

KARMA_TTL = 30.0

def get_real_track_path(filename):
    return os.path.join(ardj.settings.get_music_dir(), filename)

def get_track_by_id(track_id, cur=None):
    """Returns track description as a dictionary.

    If the track does not exist, returns None.  Extended properties,
    such as labels, are also returned.

    Arguments:
    track_id -- identified the track to return.
    cur -- database cursor, None to open a new one.
    """
    cur = cur or ardj.database.cursor()
    row = cur.execute('SELECT id, filename, artist, title, length, NULL, weight, count, last_played, real_weight FROM tracks WHERE id = ?', (track_id, )).fetchone()
    if row is not None:
        result = { 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'length': row[4], 'weight': row[6], 'count': row[7], 'last_played': row[8], 'real_weight': row[9] }
        result['labels'] = [row[0] for row in cur.execute('SELECT DISTINCT label FROM labels WHERE track_id = ? ORDER BY label', (track_id, )).fetchall()]
        if result.get('filename'):
            result['filepath'] = get_real_track_path(result['filename'])
        return result


def get_last_track_id(cur=None):
    """Returns id of the last played track.

    If the database is empty, returns None, otherwise an integer.

    Keyword arguments:
    cur -- database cursor, created if None.
    """
    cur = cur or ardj.database.cursor()
    row = cur.execute('SELECT id FROM tracks ORDER BY last_played DESC LIMIT 1').fetchone()
    return row and row[0] or None


def get_last_track(cur=None):
    """Returns the full description of the last played track.

    Calls get_track_by_id(get_last_track_id()).
    """
    return get_track_by_id(get_last_track_id(cur), cur)


def identify(track_id, cur=None, unknown='an unknown track'):
    track = get_track_by_id(track_id, cur=cur)
    if not track:
        return unknown
    return u'«%s» by %s' % (track.get('title', 'untitled'), track.get('artist', 'unknown artist'))

def queue(track_id, owner=None, cur=None):
    """Adds the track to queue."""
    cur = cur or ardj.database.cursor()
    return cur.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (track_id, (owner or 'ardj').lower(), )).lastrowid


def get_queue(cur=None):
    cur = cur or ardj.database.cursor()
    return [get_track_by_id(row[0], cur) for row in cur.execute('SELECT track_id FROM queue ORDER BY id').fetchall()]


def find_ids(pattern, cur=None):
    cur = cur or ardj.database.cursor()

    search_order = 'weight DESC'
    search_args = []
    search_labels = []
    search_ids = []

    args = [a for a in pattern.split(' ') if a.strip()]
    for arg in args:
        if arg == '-r':
            search_order = 'RANDOM()'
        elif arg == '-l':
            search_order = 'id DESC'
        elif arg == '-f':
            search_order = 'id'
        elif arg.isdigit():
            if search_ids is not None:
                search_ids.append(arg)
        elif arg.startswith('@'):
            search_labels.append(arg[1:])
            search_ids = None
        else:
            search_args.append(arg)
            search_ids = None

    if search_ids:
        return [ int(x) for x in search_ids ]

    pattern = u' '.join(search_args)

    params = []
    where = []

    for label in search_labels:
        where.append('id IN (SELECT track_id FROM labels WHERE label = ?)')
        params.append(label)

    if search_args:
        like = u' '.join(search_args)
        where.append('(ULIKE(artist, ?) OR ULIKE(title, ?))')
        params.append(like)
        params.append(like)

    if not params:
        return []

    sql = 'SELECT id FROM tracks WHERE weight > 0 AND %s ORDER BY %s LIMIT 10' % (' AND '.join(where), search_order)
    rows = cur.execute(sql, params).fetchall()
    return [row[0] for row in rows]


def add_labels(track_id, labels, owner=None, cur=None):
    cur = cur or ardj.database.cursor()
    if labels:
        for label in labels:
            if label.startswith('-'):
                cur.execute('DELETE FROM labels WHERE track_id = ? AND label = ?', (track_id, label.lstrip('-'), ))
            elif cur.execute('SELECT 1 FROM labels WHERE track_id = ? AND label = ?', (track_id, label.lstrip('+'), )).fetchall():
                pass
            else:
                cur.execute('INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)', (track_id, label.lstrip('+'), owner or 'ardj', ))
    return sorted(list(set([row[0] for row in cur.execute('SELECT label FROM labels WHERE track_id = ?', (track_id, )).fetchall()])))


def update_track(properties, cur=None):
    """Updates valid track attributes.

    Loads the track specified in properties['id'], then updates its known
    fields with the rest of the properties dictionary, then saves the
    track.  If there's the "labels" key in properties (must be a list),
    labels are added (old are preserved) to the `labels` table.

    If there's not fields to update, a message is written to the debug log.
    """
    if type(properties) != dict:
        raise Exception('Track properties must be passed as a dictionary.')
    if 'id' not in properties:
        raise Exception('Track properties have no id.')
    cur = cur or ardj.database.cursor()

    sql = []
    params = []
    for k in properties:
        if k in ('filename', 'artist', 'title', 'length', 'weight', 'count', 'last_played', 'owner', 'real_weight'):
            sql.append(k + ' = ?')
            params.append(properties[k])

    if not sql:
        ardj.log.debug('No fields to update.')
    else:
        params.append(properties['id'])
        sql = 'UPDATE tracks SET ' + ', '.join(sql) + ' WHERE id = ?'
        ardj.database.Open().debug(sql, params)
        cur.execute(sql, tuple(params))

    if properties.get('labels'):
        add_labels(properties['id'], properties['labels'], owner=properties.get('owner'), cur=cur)


def purge(cur=None):
    """Deletes tracks with zero weight.

    Removes files, track entries are left in the database to prevent reloading
    by podcaster etc.
    """
    cur = cur or ardj.database.cursor()
    music_dir = ardj.settings.get_music_dir()

    # mark tracks that no longer have files
    for track_id, filename in cur.execute('SELECT id, filename FROM tracks WHERE weight > 0').fetchall():
        abs_filename = os.path.join(music_dir, filename)
        if not os.path.exists(abs_filename):
            ardj.log.warning('Track %u vanished (%s), deleting.' % (track_id, filename))
            cur.execute('UPDATE tracks SET weight = 0 WHERE id = ?', (track_id, ))

    for track_id, filename in cur.execute('SELECT id, filename FROM tracks WHERE weight = 0 AND filename IS NOT NULL').fetchall():
        abs_filename = os.path.join(music_dir, filename)
        if os.path.exists(abs_filename):
            os.unlink(abs_filename)
            ardj.log.info('Deleted track %u (%s) from file system.' % (track_id, filename))

    cur.execute('UPDATE tracks SET filename = NULL WHERE weight = 0')
    ardj.database.Open().purge(cur)


def get_urgent(cur=None):
    """Returns current playlist preferences."""
    cur = cur or ardj.database.cursor()
    data = cur.execute('SELECT labels FROM urgent_playlists WHERE expires > ? ORDER BY expires', (int(time.time()), )).fetchall()
    if data:
        return re.split('[,\s]+', data[0][0])
    return None


def set_urgent(args, cur=None):
    """Sets the music filter.

    Sets music filter to be used for picking random tracks.  If set, only
    matching tracks will be played, regardless of playlists.yaml.  Labels
    must be specified as a string, using spaces or commas as separators.
    Use "all" to reset.
    """
    cur = cur or ardj.database.cursor()
    cur.execute('DELETE FROM urgent_playlists')
    if args != 'all':
        expires = time.time() + 3600
        cur.execute('INSERT INTO urgent_playlists (labels, expires) VALUES (?, ?)', (args, int(expires), ))


def add_vote(track_id, email, vote, cur=None, update_karma=False):
    """Adds a vote for/against a track.

    The process is: 1) add a record to the votes table, 2) update email's
    record in the karma table, 3) update weight for all tracks email voted
    for/against.

    Votes other than +1 and -1 are skipped.

    Returns track's current weight.
    """
    cur = cur or ardj.database.cursor()

    email = email.lower()

    # Normalize the vote.
    if vote > 0: vote = 1
    elif vote < 0: vote = -1

    # Resolve aliases.
    for k, v in ardj.settings.get('jabber/aliases', {}).items():
        if email in v:
            email = k
            break

    last_played, current_weight = cur.execute("SELECT last_played, weight FROM tracks WHERE id = ?", (track_id, )).fetchone()
    if not last_played:
        raise Exception('This track was never played.')
    elif current_weight <= 0:
        raise Exception("Can't vote for deleted tracks.")

    vote_count = cur.execute("SELECT COUNT(*) FROM votes WHERE track_id = ? "
        "AND email = ? AND vote = ? AND ts >= ?", (track_id, email, vote,
        last_played, )).fetchone()[0]

    cur.execute('INSERT INTO votes (track_id, email, vote, ts) '
        'VALUES (?, ?, ?, ?)', (track_id, email, vote, int(time.time()), ))

    # Update current track weight.
    current_weight = max(current_weight + vote * 0.25, 0.1)
    cur.execute('UPDATE tracks SET weight = ? WHERE id = ?', (current_weight, track_id, ))

    real_weight = update_real_track_weight(track_id, cur=cur)
    real_weight = cur.execute('SELECT weight FROM tracks WHERE id = ?',
        (track_id, )).fetchone()[0]

    return real_weight


def get_vote(track_id, email, cur=None):
    return get_track_votes(track_id, cur=cur).get(email.lower(), 0)


def get_track_votes(track_id, cur=None):
    results = {}
    cur = cur or ardj.database.cursor()
    for email, vote in cur.execute("SELECT email, vote FROM votes WHERE track_id = ? ORDER BY id", (track_id, )).fetchall():
        results[email.lower()] = vote
    return results


def gen_filename(suffix):
    """Generates a local file name.

    Returns a tuple (abs_filename, rel_filename).
    """
    musicdir = ardj.settings.get_music_dir()

    while True:
        m = hashlib.md5()
        m.update(str(random.random()))
        name = m.hexdigest() + suffix
        rel_filename = os.path.join(name[0], name[1], name)
        abs_filename = os.path.join(musicdir, rel_filename)
        if not os.path.exists(abs_filename):
            return abs_filename, rel_filename


def add_file(filename, add_labels=None, owner=None):
    """Adds the file to the database.

    Returns track id.
    """
    if not os.path.exists(filename):
        raise Exception('File not found: %s' % filename)

    ardj.log.info('Adding from %s' % filename)
    ardj.replaygain.update(filename)

    tags = ardj.tags.get(str(filename)) or {}
    artist = tags.get('artist', 'Unknown Artist')
    title = tags.get('title', 'Untitled')
    duration = tags.get('length', 0)
    labels = tags.get('labels', [])

    if add_labels and not labels:
        labels = add_labels

    abs_filename, rel_filename = gen_filename(os.path.splitext(filename)[1])
    if not ardj.util.copy_file(filename, abs_filename):
        raise Exception('Could not copy %s to %s' % (filename, abs_filename))

    cur = ardj.database.cursor()
    track_id = cur.execute('INSERT INTO tracks (artist, title, filename, length, last_played, owner, weight, real_weight, count) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 0)', (artist, title, rel_filename, duration, 0, owner or 'ardj', )).lastrowid
    for label in labels:
        cur.execute('INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)', (track_id, label, (owner or 'ardj').lower(), ))
    ardj.database.commit()
    return track_id


def get_track_id_from_queue(cur=None):
    """Returns a track from the top of the queue.
    
    If the queue is empty or there's no valid track in it, returns None.
    """
    cur = cur or ardj.database.cursor()
    row = cur.execute('SELECT id, track_id FROM queue ORDER BY id LIMIT 1').fetchone()
    if row:
        cur.execute('DELETE FROM queue WHERE id = ?', (row[0], ))
        return row[1]


def get_random_track_id_from_playlist(playlist, skip_artists, cur=None):
    if type(playlist) != dict:
        raise TypeError('playlist must be a dictionary.')

    cur = cur or ardj.database.cursor()

    sql = 'SELECT id, weight, artist FROM tracks WHERE weight > 0 AND artist IS NOT NULL'
    params = []

    sql, params = add_labels_filter(sql, params, playlist.get('labels', [ playlist.get('name', 'music') ]))

    repeat_count = playlist.get('repeat')
    if repeat_count:
        sql += ' AND count < ?'
        params.append(int(repeat_count))

    if skip_artists:
        skip_artists = skip_artists[:int(playlist.get('history', '10'))]
        if skip_artists:
            sql += ' AND artist NOT IN (%s)' % ', '.join(['?'] * len(skip_artists))
            params += skip_artists

    weight = playlist.get('weight', '')
    if '-' in weight:
        parts = weight.split('-', 1)
        sql += ' AND weight >= ? AND weight <= ?'
        params.append(float(parts[0]))
        params.append(float(parts[1]))

    delay = playlist.get('track_delay')
    if delay:
        sql += ' AND (last_played IS NULL OR last_played <= ?)'
        params.append(int(time.time()) - int(delay) * 60)

    ardj.database.Open().debug(sql, params)
    track_id = get_random_row(cur.execute(sql, tuple(params)).fetchall())

    if playlist.get('preroll'):
        track_id = add_preroll(track_id, playlist.get('preroll'), cur=cur)

    return track_id


def add_labels_filter(sql, params, labels):
    either = [l for l in labels if not l.startswith('-') and not l.startswith('+')]
    neither = [l[1:] for l in labels if l.startswith('-')]
    every = [l[1:] for l in labels if l.startswith('+')]

    if either:
        sql += ' AND id IN (SELECT track_id FROM labels WHERE label IN (%s))' % ', '.join(['?'] * len(either))
        params += either

    if neither:
        sql += ' AND id NOT IN (SELECT track_id FROM labels WHERE label IN (%s))' % ', '.join(['?'] * len(neither))
        params += neither

    if every:
        for label in every:
            sql += ' AND id IN (SELECT track_id FROM labels WHERE label = ?)'
            params.append(label)

    return sql, params


def get_random_row(rows):
    """Picks a random row.

    First divides track weights by the number of tracks that the artist has,
    then picks a random track based on the updated weight.
    """
    ID_COL, WEIGHT_COL, NAME_COL = 0, 1, 2

    artist_counts = {}
    for row in rows:
        name = row[NAME_COL].lower()
        if name not in artist_counts:
            artist_counts[name] = 0
        artist_counts[name] += 1

    probability_sum = 0
    for row in rows:
        name = row[NAME_COL].lower()
        probability_sum += row[WEIGHT_COL] / artist_counts[name]

    rnd = random.random() * probability_sum
    for row in rows:
        name = row[NAME_COL].lower()
        weight = row[WEIGHT_COL] / artist_counts[name]
        if rnd < weight:
            return row[ID_COL]
        rnd -= weight

    if len(rows):
        ardj.log.warning('Bad RND logic, returning first track.')
        return rows[0][ID_COL]

    return None


def get_all_playlists(cur=None):
    """Returns information about all known playlists.  Information from
    playlists.yaml is complemented by the last_played column of the `playlists'
    table."""
    cur = cur or ardj.database.cursor()
    stats = dict(cur.execute('SELECT name, last_played FROM playlists WHERE name IS NOT NULL AND last_played IS NOT NULL').fetchall())
    def expand(lst):
        result = []
        for item in lst:
            if '-' in str(item):
                bounds = item.split('-')
                result += range(int(bounds[0]), int(bounds[1]))
            else:
                result.append(item)
        return result
    def add_ts(p):
        p['last_played'] = 0
        if p['name'] in stats:
            p['last_played'] = stats[p['name']]
        if 'days' in p:
            p['days'] = expand(p['days'])
        if 'hours' in p:
            p['hours'] = expand(p['hours'])
        return p
    return [add_ts(p) for p in ardj.settings.load().get_playlists()]


def get_active_playlists(timestamp=None, debug=False, cur=None):
    now = time.localtime(timestamp)

    now_ts = time.mktime(now)
    now_day = int(time.strftime('%w', now))
    now_hour = int(time.strftime('%H', now))

    def is_active(p):
        if 'delay' in p and p['delay'] * 60 + p['last_played'] >= now_ts:
            if debug:
                ardj.log.debug('playlist %s: delayed' % p['name'])
            return False
        if 'hours' in p and now_hour not in p['hours']:
            if debug:
                ardj.log.debug('playlist %s: wrong hour (%s not in %s)' % (p['name'], now_hour, p['hours']))
            return False
        if 'days' in p and now_day not in p['days']:
            if debug:
                ardj.log.debug('playlist %s: wrong day (%s not in %s)' % (p['name'], now_day, p['days']))
            return False
        return True

    return [p for p in get_all_playlists(cur) if is_active(p)]


def get_prerolls_for_labels(labels, cur):
    """Returns ids of valid prerolls that have one of the specified labels."""
    sql = "SELECT tracks.id FROM tracks INNER JOIN labels ON labels.track_id = tracks.id WHERE tracks.weight > 0 AND tracks.filename IS NOT NULL AND labels.label IN (%s)" % ', '.join(['?'] * len(labels))
    return [row[0] for row in cur.execute(sql, labels).fetchall()]

def get_prerolls_for_track(track_id, cur):
    """Returns prerolls applicable to the specified track."""
    by_artist = cur.execute("SELECT t1.id FROM tracks t1 INNER JOIN tracks t2 ON t2.artist = t1.artist INNER JOIN labels l ON l.track_id = t1.id WHERE l.label = 'preroll' AND t2.id = ? AND t1.weight > 0", (track_id, )).fetchall()
    by_label = cur.execute("SELECT t.id, t.title FROM tracks t WHERE t.id IN (SELECT track_id FROM labels WHERE label IN (SELECT l.label || '-preroll' FROM tracks t1 INNER JOIN labels l ON l.track_id = t1.id WHERE t1.id = ?))", (track_id, )).fetchall()
    return list(set([row[0] for row in by_artist + by_label]))

def add_preroll(track_id, labels=None, cur=None):
    """Adds a preroll for the specified track.

    Finds prerolls by labels and artist title, picks one and returns its id,
    queueing the input track_id.  If `labels' is explicitly specified, only
    tracks with those labels will be used as prerolls.
    
    Tracks that have a preroll-* never have a preroll.
    """
    cur = cur or ardj.database.cursor()

    # Skip if the track is a preroll.
    if cur.execute("SELECT COUNT(*) FROM labels WHERE track_id = ? AND label LIKE 'preroll-%'", (track_id, )).fetchone()[0]:
        return track_id

    if labels:
        prerolls = get_prerolls_for_labels(labels, cur)
    else:
        prerolls = get_prerolls_for_track(track_id, cur)

    if track_id in prerolls:
        prerolls.remove(track_id)

    if prerolls:
        queue(track_id, cur=cur)
        track_id = prerolls[random.randrange(len(prerolls))]

    return track_id


def get_next_track_id(cur=None, debug=False, update_stats=True):
    """Picks a track to play.

    The track is chosen from the active playlists. If nothing could be chosen,
    a random track is picked regardless of the playlist (e.g., the track can be
    in no playlist or in an unexisting one).  If that fails too, None is
    returned.

    Normally returns a dictionary with keys that corresponds to the "tracks"
    table fields, e.g.: filename, artist, title, length, weight, count,
    last_played, playlist.  An additional key is filepath, which contains the
    full path name to the picked track, encoded in UTF-8.

    Before the track is returned, its and the playlist's statistics are
    updated.

    Arguments:
    update_stats -- set to False to not update last_played.
    """
    want_preroll = True
    cur = cur or ardj.database.cursor()

    skip_artists = list(set([row[0] for row in cur.execute('SELECT artist FROM tracks WHERE artist IS NOT NULL AND last_played IS NOT NULL ORDER BY last_played DESC LIMIT ' + str(ardj.settings.get('dupes', 5))).fetchall()]))
    if debug:
        ardj.log.debug(u'Artists to skip: %s' % u', '.join(skip_artists or ['none']) + u'.')

    track_id = get_track_id_from_queue(cur)
    if track_id:
        want_preroll = False
        if debug:
            ardj.log.debug('Picked track %u from the queue.' % track_id)

    if not track_id:
        labels = get_urgent()
        if labels:
            track_id = get_random_track_id_from_playlist({'labels': labels}, skip_artists, cur)
            if debug and track_id:
                ardj.log.debug('Picked track %u from the urgent playlist.' % track_id)

    if not track_id:
        for playlist in get_active_playlists():
            if debug:
                ardj.log.debug('Looking for tracks in playlist "%s"' % playlist.get('name', 'unnamed'))
            labels = playlist.get('labels', [ playlist.get('name', 'music') ])
            track_id = get_random_track_id_from_playlist(playlist, skip_artists, cur)
            if track_id is not None:
                if debug:
                    ardj.log.debug('Picked track %u from playlist %s' % (track_id, playlist.get('name', 'unnamed')))
                break

    if track_id:
        if want_preroll:
            track_id = add_preroll(track_id, cur=cur)

        if update_stats:
            count = cur.execute('SELECT count FROM tracks WHERE id = ?', (track_id, )).fetchone()[0] or 0
            cur.execute('UPDATE tracks SET count = ?, last_played = ? WHERE id = ?', (count + 1, int(time.time()), track_id, ))

            block_playlists(track_id, cur=cur)

            log(track_id, cur=cur)

        shift_track_weight(track_id, cur)
        ardj.database.Open().commit()

    return track_id


def shift_track_weight(track_id, cur):
    weight, real_weight = cur.execute("SELECT weight, real_weight FROM tracks WHERE id = ?", (track_id, )).fetchone()
    if weight < real_weight:
        weight = min(weight + 0.1, real_weight)
    elif weight > real_weight:
        weight = max(weight - 0.1, real_weight)
    cur.execute("UPDATE tracks SET weight = ? WHERE id = ?", (weight, track_id, ))


def log(track_id, listener_count=None, ts=None, cur=None):
    """Logs that the track was played.

    Only logs tracks with more than zero listeners."""
    if listener_count is None:
        listener_count = ardj.listeners.get_count()
    if listener_count > 0:
        cur = cur or ardj.database.cursor()
        cur.execute('INSERT INTO playlog (ts, track_id, listeners) VALUES (?, ?, ?)', (int(ts or time.time()), int(track_id), listener_count, ))


def get_average_length(cur=None):
    """Returns the weighed average track length in seconds."""
    s_prc = s_qty = 0.0
    cur = cur or ardj.database.cursor()

    for prc, qty in cur.execute('SELECT ROUND(length / 60) AS r, COUNT(*) FROM tracks GROUP BY r').fetchall():
        s_prc += prc * qty
        s_qty += qty

    return int(s_prc / s_qty * 60 * 1.5)


def get_track_to_play():
    """Returns information about the track to play.
    
    The information is requested from an external ardj process, because
    otherwise you would have to restart ices every time the track selection
    algorythm is changed."""
    data = ardj.util.run([ 'ardj', 'track', 'next-json' ], quiet=True, grab_output=True)
    return json.loads(data)


def update_real_track_weight(track_id, cur=None):
    """Returns the real track weight, using the last vote for each user."""
    cur = cur or ardj.database.cursor()
    rows = cur.execute('SELECT v.email, v.vote * k.weight FROM votes v '
        'INNER JOIN karma k ON k.email = v.email '
        'WHERE v.track_id = ? ORDER BY v.ts', (track_id, )).fetchall()

    results = {}
    for email, vote in rows:
        results[email] = vote

    real_weight = sum(results.values()) * 0.25 + 1
    cur.execute('UPDATE tracks SET real_weight = ? WHERE id = ?', (real_weight, track_id, ))
    return real_weight

def update_real_track_weights(cur=None):
    """Updates the real_weight column for all tracks.  To be used when the
    votes table was heavily modified or when corruption is possible."""
    cur = cur or ardj.database.cursor()
    update_karma(cur=cur)
    for row in cur.execute('SELECT id FROM tracks').fetchall():
        update_real_track_weight(row[0], cur=cur)


def block_playlists(track_id, cur=None):
    """Finds playlists that contain this track and updates their last_played
    property, so that they could be delayed properly."""
    cur = cur or ardj.database.cursor()

    track = get_track_by_id(track_id, cur=cur)
    ts = int(time.time())

    for playlist in get_all_playlists(cur=cur):
        name = playlist.get('name')
        if name and track_matches_playlist(track, playlist):
            logging.debug('Track %u touches playlist %s' % (track_id, name))
            cur.execute('UPDATE playlists SET last_played = ? '
                'WHERE name = ?', (ts, name, ))
            if cur.rowcount == 0:
                cur.execute('INSERT INTO playlists (name, last_played) '
                    'VALUES (?, ?)', (name, ts, ))


def track_matches_playlist(track, playlist):
    """Checks if the track matches the playlist labels."""
    tlabels = track.get('labels')
    if not tlabels:
        return False

    plabels = playlist.get('labels', [ playlist.get('name') ])
    success = False

    for plabel in plabels:
        if plabel.startswith('-'):
            if plabel[1:] in tlabels:
                return False
        if plabel.startswith('+'):
            if plabel[1:] not in tlabels:
                return False
        elif plabel in tlabels:
            success = True

    return success


def update_karma(cur=None):
    """Updates users karma based on their last voting time."""
    cur = cur or ardj.database.cursor()

    cur.execute('DELETE FROM karma')

    now = int(time.time()) / 86400
    for email, ts in cur.execute('SELECT email, MAX(ts) FROM votes GROUP BY email').fetchall():
        diff = now - ts / 86400
        if diff == 0:
            karma = 1
        elif diff > KARMA_TTL:
            karma = 0
        else:
            karma = (KARMA_TTL - float(diff)) / KARMA_TTL
        if karma:
            cur.execute('INSERT INTO karma (email, weight) VALUES (?, ?)', (email, karma, ))
            if '-q' not in sys.argv:
                print '%.04f\t%s (%u)' % (karma, email, diff)


def merge(id1, id2, cur):
    """Merges two tracks."""
    t1 = get_track_by_id(id1, cur=cur)
    t2 = get_track_by_id(id2, cur=cur)

    for k in ('real_weight', 'last_played', 'weight'):
        t1[k] = max(t1[k], t2[k])
    t1['count'] = t1['count'] + t2['count']

    t1['labels'] = list(set(t1['labels'] + t2['labels']))

    cur.execute('UPDATE labels SET track_id = ? WHERE track_id = ?', (id1, id2, ))
    cur.execute('UPDATE votes SET track_id = ? WHERE track_id = ?', (id1, id2, ))
    cur.execute('UPDATE playlog SET track_id = ? WHERE track_id = ?', (id1, id2, ))

    update_track(t1, cur=cur)

    t2['weight'] = 0
    update_track(t2, cur=cur)

    update_real_track_weight(id1, cur=cur)


def update_track_lengths():
    cur = ardj.database.cursor()
    rows = cur.execute('SELECT id, filename, length '
        'FROM tracks WHERE weight > 0 AND filename').fetchall()

    updates = []
    for id, filename, length in rows:
        tags = ardj.tags.get(get_real_track_path(filename))
        if tags['length'] != length:
            print '%u, %s: %s => %s' % (id, filename, length, tags['length'])
            updates.append((tags['length'], id))

    for length, id in updates:
        cur.execute('UPDATE tracks SET length = ? WHERE id = ?', (length, id, ))
    ardj.database.commit()


def find_incoming_files():
    """Returns a list of incoming file names.  Only files modified more than 60
    seconds ago are reported.  If the database/incoming/path parameter is not
    set, an empty list is returned."""
    result = []
    incoming = ardj.settings.getpath('database/incoming/path')
    ts_limit = int(time.time()) - 120
    if incoming:
        for dir, dirs, files in os.walk(incoming):
            for filename in files:
                realname = os.path.join(dir, filename)
                if os.stat(realname).st_mtime > ts_limit:
                    return [] # still uploading
                if os.path.splitext(filename.lower())[1] in ('.mp3', '.ogg'):
                    result.append(realname)
    return result


__CLI_USAGE__ = """Usage: ardj track command

Commands:
  next-json       -- print what to play next (-n to debug).
  update-weights  -- update the real_weight property of all tracks.
"""

def run_cli(args):
    command = ''.join(args[:1])

    if command == 'next-json':
        cur = ardj.database.cursor()
        debug = '-n' in args
        track_id = get_next_track_id(cur=cur, update_stats=not debug)
        if track_id:
            track = get_track_by_id(track_id, cur=cur)
            output = json.dumps(track)
            ardj.log.debug('next-json returns: %s' % output)
            print output
    elif command == 'update-weights':
        update_real_track_weights()
        ardj.database.Open().commit()
    elif command == 'update-lengths':
        update_track_lengths()
    else:
        print __CLI_USAGE__
