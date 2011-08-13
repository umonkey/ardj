import os
import re
import sys
import time


def pick_jingle(cur, label):
    """Returns a jingle with the specified label."""
    row = cur.execute('SELECT track_id FROM labels WHERE label = ? ORDER BY RANDOM() LIMIT 1', (label, )).fetchone()
    if row:
        return row[0]


def queue_tracks(cur, track_ids):
    """Queues all specified tracks."""
    for track_id in track_ids:
        cur.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (track_id, 'robot', ))


USAGE = """Usage: ardj db commands...

Commands:
  console           -- open SQLite console
  fix-artist-names  -- correct artist names according to last.fm
  flush-queue       -- remove everything from queue
  import            -- add tracks from a public "drop box"
  mark-hitlist      -- mark best tracks with "hitlist"
  mark-orphans      -- mark tracks that don't belong to a playlist
  mark-preshow      -- marks preshow music
  mark-recent       -- mark last 100 tracks with "recent"
  purge             -- remove dead data
  stat              -- show database statistics
  """


def merge_votes(args):
    """Collapses votes according to jabber/aliases."""
    db = Open()
    db.merge_aliases()
    db.commit()


def run_cli(args):
    """Implements the "ardj db" command."""
    db = Open()
    ok = False
    if 'console' in args or not args:
        ardj.util.run([ 'sqlite3', '-header', db.filename ])
        ok = True
    if 'flush-queue' in args:
        db.cursor().execute('DELETE FROM queue')
        ok = True
    if 'mark-hitlist' in args:
        db.mark_hitlist()
        ok = True
    if 'mark-preshow' in args:
        db.mark_preshow_music()
        ok = True
    if 'mark-recent' in args:
        db.mark_recent_music()
        ok = True
    if 'mark-orphans' in args:
        db.mark_orphans()
        ok = True
    if 'mark-long' in args:
        db.mark_long()
        ok = True
    if 'purge' in args:
        db.purge()
        ok = True
    if 'stat' in args:
        stats = db.get_stats()
        print '%u tracks, %.1f hours.' % (stats['tracks'], stats['seconds'] / 60 / 60)
        ok = True
    if 'fix-artist-names' in args:
        db.fix_artist_names()
        ok = True
    if not ok:
        print USAGE
    else:
        db.commit()
