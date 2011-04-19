import ardj.database
import ardj.tracks


USAGE = """Usage: ardj shitlist command

Commands:
    queue      -- pick and queue tracks
"""

JINGLES = [ 'shitlist-begin', 'shitlist-mid', 'shitlist-mid', 'shitlist-end' ]


def get_highest_weight(cur):
    """Returns the lowest weight in the worst 10 tracks."""
    row = cur.execute('SELECT weight FROM tracks WHERE weight > 0 AND id IN (SELECT track_id FROM labels WHERE label = ?) ORDER BY weight limit 9, 1', ('music', )).fetchone()
    if row is None:
        return 0
    return row[0]


def pick_jingle(cur, label):
    """Returns a jingle with the specified label."""
    row = cur.execute('SELECT track_id FROM labels WHERE label = ? ORDER BY RANDOM() LIMIT 1', (label, )).fetchone()
    if row:
        return row[0]


def pick_tracks(cur=None):
    """Picks 10 tracks with less weight.
    
    Find out what's the lowest weight in the shitty 10, then returns random
    tracks with up to that weight."""
    cur = cur or ardj.database.cursor()
    weight = get_highest_weight(cur)
    rows = cur.execute('SELECT id FROM tracks WHERE weight <= ? AND id IN (SELECT track_id FROM labels WHERE label = ?) ORDER BY RANDOM() LIMIT 10', (weight, 'music', ))
    return [row[0] for row in rows]


def queue_tracks(cur=None):
    cur = cur or ardj.database.cursor()

    tracks = pick_tracks(cur=cur)
    if not tracks:
        ardj.log.warning('Shitlist failed: no tracks.')
        return False

    jlabels = JINGLES
    queue_ids = []

    for track_id in tracks:
        if len(queue_ids) % 4 == 0:
            queue_ids.append(pick_jingle(cur, JINGLES[0]))
            del JINGLES[0]
        queue_ids.append(track_id)

    for x in queue_ids:
        ardj.tracks.queue(x, 'ardj', cur)


def run_cli(args):
    db = ardj.database.Open()

    if args[0:1] == ['queue']:
        queue_tracks(cur=db.cursor())
        db.commit()
        return True

    elif args[0:1] == ['print']:
        for track_id in pick_tracks(cur=db.cursor()):
            print track_id
        return True

    print USAGE
