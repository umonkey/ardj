#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, re, sys, time
from datetime import datetime
from sqlite3 import dbapi2 as sqlite, OperationalError

OUTPUT = "/home/ekis/tornado/text/think.txt"

def fetchQuery(query):
	return sqlite.connect('ardj.sqlite').cursor().execute(query).fetchall()

def getTrackString(id, count, artist, title, weight):
	s = "id: %5s  %s count: %3i weight: %1.2f \n"%(id, (artist+" - "+title).ljust(65), count, weight)
	return s.encode('utf-8')

popularArtists = fetchQuery("""
SELECT artist, SUM(weight) AS weight, COUNT(*) as tcount, SUM(weight)/COUNT(*) AS avWeight FROM tracks
WHERE weight>=2 
GROUP BY artist
HAVING tcount>1
ORDER BY avWeight DESC
LIMIT 16
""")

newTracksPlayed = fetchQuery("""
SELECT id, count, artist, title, weight FROM playlog 
LEFT JOIN tracks ON tracks.id = track_id 
WHERE ts>=((SELECT MAX(ts) FROM playlog)-86400) 
	AND count<=2
ORDER BY count ASC
""")

'''
oldTracksPlayed = fetchQuery("""
SELECT DISTINCT id, count, artist, title, weight FROM playlog 
LEFT JOIN tracks ON tracks.id = playlog.track_id 
LEFT JOIN labels ON labels.track_id = playlog.track_id
WHERE ts>=((SELECT MAX(ts) FROM playlog)-86400) AND labels.label="music"
ORDER BY count DESC LIMIT 10
""")
'''
bestCalmTracks = fetchQuery("""
SELECT DISTINCT id, count, artist, title, weight FROM tracks 
LEFT JOIN labels ON labels.track_id = tracks.id
WHERE (labels.label="calm" OR labels.label="lounge")
ORDER BY weight DESC LIMIT 10
""")

bestCovers = fetchQuery("""
SELECT id, count, artist, title, weight FROM tracks 
LEFT JOIN labels ON labels.track_id = tracks.id
WHERE labels.label="cover"
ORDER BY weight DESC LIMIT 8
""")

forgottenTracks = fetchQuery("""
SELECT DISTINCT id, count, artist, title, weight FROM tracks 
WHERE last_played<=((SELECT MAX(ts) FROM playlog)-86400*60) AND last_played>0 AND filename
ORDER BY weight DESC
LIMIT 10
""")

neverPlayedTracks = fetchQuery("""
SELECT DISTINCT id, count, artist, title, length, weight FROM tracks 
WHERE last_played=0 AND filename AND weight>0
ORDER BY artist
""")

neverPlayedArtists = fetchQuery("""
SELECT DISTINCT artist FROM tracks WHERE artist NOT IN (SELECT artist FROM tracks WHERE count>0) AND weight>0
""")



out = open(OUTPUT, "w")
out.write( (u"Дата последнего изменения базы %s \n"%datetime.fromtimestamp(os.stat('ardj.sqlite')[8])).encode('utf-8'))
out.write( (u"Статистика составлена %s. Обновляется раз в 6 часов.\n"%datetime.now() ).encode('utf-8'))

'''out.write(u"\nСамые старые песни, проигранные за 24 часа:\n".encode('utf-8'))
for id, count, artist, title, weight in oldTracksPlayed:
	out.write(getTrackString(id, count, artist, title, weight))'''

out.write(u"\nЛучшие исполнители:\n".encode('utf-8'))
for artist, weight, tracks, avWeight in popularArtists:
	s = u"artist: %s average weight: %2.2f tracks: %2i \n"%(artist.ljust(40), avWeight, tracks)
	out.write(s.encode('utf-8'))
out.write(u" * Только для исполнителей, у которых больше одной песни и рейтинг песен >= 2\n".encode('utf-8'))

out.write(u"\nНовинки, проигранные за 24 часа:\n".encode('utf-8'))
for id, count, artist, title, weight in newTracksPlayed:
	out.write(getTrackString(id, count, artist, title, weight))

out.write(u"\nПозабытые песни (не игрались больше двух месяцев):\n".encode('utf-8'))
for id, count, artist, title, weight in forgottenTracks:
	out.write(getTrackString(id, count, artist, title, weight))

out.write(u"\nЛучшие вечерние песни:\n".encode('utf-8'))
for id, count, artist, title, weight in bestCalmTracks:
	out.write(getTrackString(id, count, artist, title, weight))

out.write(u"\nЛучшие каверы:\n".encode('utf-8'))
for id, count, artist, title, weight in bestCovers:
	out.write(getTrackString(id, count, artist, title, weight))

out.write(u"\nНи разу не звучавшие исполнители:\n".encode('utf-8'))
if not len(neverPlayedArtists): out.write(u"Нет\n".encode('utf-8'))
for (artist, ) in neverPlayedArtists:
	out.write( (artist+"\n").encode('utf-8'))

out.write(u"\nНе прослушанные песни:\n".encode('utf-8'))
l = 0
for id, count, artist, title, length, weight in neverPlayedTracks:
	l+=length
	out.write(getTrackString(id, count, artist, title, weight))
s = u"Всего не прослушано %i минут (%1.1f часов) музыки.\n"%(l/60, l/60./60.)
out.write(s.encode('utf-8'))
out.close()

