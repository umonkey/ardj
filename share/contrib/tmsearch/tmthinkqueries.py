#!/usr/bin/python
# -*- coding: utf-8 -*-

QHitList = """
SELECT DISTINCT id, count, artist, title, weight FROM tracks 
ORDER BY weight DESC LIMIT 20
"""

QMostBookmarked = """
SELECT id, count, artist, title, weight, count(label) AS bmcount FROM tracks 
JOIN labels ON tracks.id = labels.track_id
WHERE label LIKE "bm:%" AND weight>1
GROUP BY tracks.id ORDER BY bmcount DESC, weight DESC
"""

QPopularArtists = """
SELECT artist, SUM(weight) AS weight, COUNT(*) as tcount, SUM(weight)/COUNT(*) AS avWeight FROM tracks
WHERE weight>=2 
GROUP BY artist
HAVING tcount>1
ORDER BY tcount DESC, avWeight DESC
"""

QNewTracksPlayed = """
SELECT DISTINCT id, count, artist, title, weight FROM playlog 
LEFT JOIN tracks ON tracks.id = track_id 
WHERE ts>=((SELECT MAX(ts) FROM playlog)-86400) 
	AND count<=2 AND weight>0
ORDER BY count ASC
"""

QBestNewTracks = """
SELECT DISTINCT id, count, artist, title, weight FROM tracks 
WHERE count<=5
ORDER BY weight DESC LIMIT 10
"""
QBestNewTracks2 = """
SELECT DISTINCT id, count, artist, title, weight, weight/count FROM tracks
WHERE count>2
ORDER BY weight/count DESC LIMIT 10
"""

QOldTracksPlayed = """
SELECT DISTINCT id, count, artist, title, weight FROM playlog 
LEFT JOIN tracks ON tracks.id = playlog.track_id 
LEFT JOIN labels ON labels.track_id = playlog.track_id
WHERE ts>=((SELECT MAX(ts) FROM playlog)-86400) AND labels.label="music"
ORDER BY count DESC LIMIT 10
"""

QBestCalmTracks = """
SELECT DISTINCT id, count, artist, title, weight FROM tracks 
LEFT JOIN labels ON labels.track_id = tracks.id
WHERE (labels.label="calm")
ORDER BY weight DESC LIMIT 10
"""
QBestLoungeTracks = """
SELECT DISTINCT id, count, artist, title, weight FROM tracks 
LEFT JOIN labels ON labels.track_id = tracks.id
WHERE (labels.label="lounge")
ORDER BY weight DESC LIMIT 10
"""
QBestCovers = """
SELECT id, count, artist, title, weight FROM tracks 
LEFT JOIN labels ON labels.track_id = tracks.id
WHERE labels.label="cover"
ORDER BY weight DESC
LIMIT 15
"""

QForgottenTracks = """
SELECT DISTINCT id, count, artist, title, weight FROM tracks 
WHERE last_played<=((SELECT MAX(ts) FROM playlog)-86400*60) AND last_played>0 AND filename
ORDER BY weight DESC
"""

QNeverPlayedTracks = """
SELECT DISTINCT id, count, artist, title, length, weight FROM tracks 
WHERE last_played=0 AND filename AND weight>0
ORDER BY artist
"""

QNeverPlayedArtists = """
SELECT DISTINCT artist FROM tracks WHERE artist NOT IN (SELECT artist FROM tracks WHERE count>0) AND weight>0
"""

QPreshowMusic = """
SELECT DISTINCT id, count, artist, title, weight FROM tracks 
LEFT JOIN labels ON labels.track_id = tracks.id
WHERE (labels.label="preshow-music")
ORDER BY weight DESC
"""
