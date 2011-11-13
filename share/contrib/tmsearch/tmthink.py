#!/usr/bin/python
# -*- coding: utf-8 -*-

import time, os, sys, web
from datetime import datetime
from sqlite3 import dbapi2 as sqlite, OperationalError
from tmthinkqueries import *
#sys.path.append('/home/hakimovis/freelance2/ekis/main')
#import tornado.web
import simplejson as json
#from grab import Grab
from render import render_to_response

APP_PATH = "/home/hakimovis/tmsearch"

def fetchQuery(query):
    #print "query:", query
    try:
        return sqlite.connect(APP_PATH+'/tm/ardj.sqlite').cursor().execute(query).fetchall()
    except Exception as e:
        print "fetchQuery error:",e
        print "wrong query:", query

SORT_LIST={
    'id':           {'title': u'id',            'selected': False},
    'artist':       {'title': u'Исполнитель',   'selected': False},
    'title':        {'title': u'Название',      'selected': False},
    'weight':       {'title': u'Рейтинг',       'selected': False},
    'count':        {'title': u'Проигрываний',  'selected': False},
}
SORT_LIST['weight']['selected'] = True

"""
ardj base structure:
    table           fields
    --------- -----------------------------------------------
    tracks    id, count, artist, title, weight, last_played
    labels    id, track_id, label
    playlog   ts, track_id, listeners
    votes     id, track_id, email, vote, ts
"""

QUERY_TEMPLATE = """
    SELECT DISTINCT fieldsString FROM tracks 
    WHERE nameWhereString
        AND labelString
        AND weight>0
    orderString orderDir
    limitString
"""

def makeQuery(query, **kwargs):
    if kwargs.get('name', '')!='':
        n = kwargs['name']
        nameWhereString = '(LOWER(artist) LIKE "%%'+n+'%%" OR LOWER(title) LIKE "%%'+n+'%%")'
        #nameWhereString = '(CHARINDEX("%s", LOWER(artist)) IS NOT NULL) OR (CHARINDEX("%s", LOWER(title)) IS NOT NULL)'%(n, n)
    else: nameWhereString = '1'
    query = query.replace('nameWhereString', nameWhereString)
    
    if kwargs.has_key('fields'):
        fieldsString = kwargs['fields']
    else:
        fieldsString = """id, count, artist, title, weight, tagslist"""
    query = query.replace('fieldsString', fieldsString)
    query = query.replace('tagslist', """(SELECT group_concat(label) FROM labels 
            WHERE labels.track_id = tracks.id AND NOT label LIKE "%:%")
            """)
    if kwargs.has_key('order'):
        orderString = "ORDER BY "+kwargs['order']
    else:
        orderString = "ORDER BY artist"
    query = query.replace('orderString', orderString)

    if kwargs.has_key('orderDir'):
        orderDir = kwargs['orderDir']
    else: orderDir = 'ASC'
    query = query.replace('orderDir', orderDir)

    if kwargs.has_key('limit'):
        limitString = "LIMIT "+str(kwargs['limit'])
    else:
        limitString = "LIMIT 50"
    query = query.replace('limitString', limitString)
    labelString = '1'
    if kwargs.get('labels', False):
        labelString = []
        for label in kwargs['labels']:
            if label[0] != '-':
                labelString+=["id IN (SELECT track_id FROM labels WHERE label = '%s')"%label]
            else:
                labelString+=["id NOT IN (SELECT track_id FROM labels WHERE label = '%s')"%label.strip('-')]
        labelString = " AND ".join(labelString)
    query = query.replace('labelString', labelString)
    return query

def getSpecInfo(qType):
    fields, query = False, False
    if qType == 'welcome': return "welcome!"
    if qType == 'hitList': fields, query = "id, count, artist, title, weight", QHitList
    if qType == 'popularArtists': fields, query = "artist, weight, tracks, avWeight", QPopularArtists
    if qType == 'newTracksPlayed': fields, query = "id, count, artist, title, weight", QNewTracksPlayed
    if qType == 'bestNewTracks': fields, query = "id, count, artist, title, weight", QBestNewTracks
    if qType == 'bestNewTracks2': fields, query = "id, count, artist, title, weight, avWeight", QBestNewTracks2
    if qType == 'forgottenTracks': fields, query = "id, count, artist, title, weight", QForgottenTracks
    if qType == 'bestCalmTracks': fields, query = "id, count, artist, title, weight", QBestCalmTracks
    if qType == 'bestLoungeTracks': fields, query = "id, count, artist, title, weight", QBestLoungeTracks
    if qType == 'bestCovers': fields, query = "id, count, artist, title, weight", QBestCovers
    if qType == 'mostBookmarked': fields, query = "id, count, artist, title, weight, bmcount", QMostBookmarked  
    if qType == 'neverPlayedArtists': fields, query = "artist", QNeverPlayedArtists
    if qType == 'neverPlayedTracks': fields, query = "id, count, artist, title, length, weight", QNeverPlayedTracks
    if qType == 'preshowMusic': fields, query = "id, count, artist, title, weight", QPreshowMusic
    fields = fields.replace(" ", "").split(",")
    if fields and query:
        data = fetchDict(fields, fetchQuery(query))
        result = {'fields': fields, 'data': data}
        return result
    return """available requests: popularArtists, newTracksPlayed, forgottenTracks, 
                    bestCalmTracks, bestCovers, neverPlayedArtists, neverPlayedTracks<br>
                    for example: ?spec=bestCovers
                """

def fetchDict(fields, query_r):
    if not query_r: return []
    if type(fields).__name__ != "list": fieldsList = fields.replace(' ',"").split(',')
    else: fieldsList = fields
    print "fields", fieldsList
    result = []
    for dataList in query_r:
        row = {}
        for num, key in enumerate(fieldsList): 
            value = dataList[num]
            if type(value).__name__=='float': value = str(round(value,2))
            if type(value).__name__=='int': value = str(value)
            row[key] = value.replace("'", "`").replace('"',"&quot;")
        result.append(row)
    return result

def search(**kwargs):
    print "search {0}".format(kwargs)
    params = kwargs
    if not kwargs.has_key('fieldsString'): fieldsString = 'id, count, artist, title, weight, tagslist'
    else: fieldsString = kwargs['fieldsString']
    params['fieldsString'] = fieldsString
    query = makeQuery(QUERY_TEMPLATE, **params)
    print "search query: ", query.encode('utf-8')
    query_r = fetchQuery(query)
    if query_r and len(query_r): print "found", len(query_r), "results"
    data = fetchDict(fieldsString, query_r)
    result = {'fields': fieldsString.replace(' ','').split(','), 'data': data}
    return result


class TmThinker:
    def get_argument(self, key, default_value = False):
        return web.input().get(key, default_value)
    def request_arguments(self):
        return web.input()
        
    def getSearchData(self):
        if self.get_argument('spec', False): return getSpecInfo(self.get_argument('spec'))
        elif self.get_argument('name', False) or self.get_argument('labelFilter', False) or self.get_argument('vocals', False) or self.get_argument('bookmarkId', False):
            params = {}
            if self.get_argument('name', False): params['name'] = self.get_argument('name')
            if self.get_argument('order', False): params['order'] = self.get_argument('order')
            if self.get_argument('orderDir', False): params['orderDir'] = self.get_argument('orderDir')
            if self.get_argument('limit', False): params['limit'] = self.get_argument('limit')
            
            labels = []
            if self.get_argument('labelFilter', False):
                labels+=self.get_argument('labelFilter').strip().split(' ')
            if self.get_argument('vocals', False):
                vocals = self.get_argument('vocals')
                if vocals == 'male': labels+=['male', '-female']
                elif vocals == 'female': labels+=['female', '-male']
                elif vocals == 'both': labels+=['male', 'female']
                elif vocals == 'instrumental': labels+=['instrumental']
            if self.get_argument('bookmarkId', False): 
                labels += ["bm:"+self.get_argument('bookmarkId')]
            if self.get_argument('lang', False):
                lang = self.get_argument('lang')
                if lang == 'ru': labels+=['lang:ru']
                elif lang == 'en': labels+=['lang:en']
                elif lang == 'other': labels+=['-lang:ru', '-lang:en', '-instrumental']
            if len(labels): params['labels'] = labels
            data = search(**params)
            data['arguments'] = self.request_arguments()
            return data

    def GET(self, *args, **kwargs):
        i = web.input()
        if not i or i.get('ajax',0)==0:
            c = {'title': u"Заголовок"}
            c['sortList'] = SORT_LIST
            c['DBDate'] = datetime.fromtimestamp(os.stat(APP_PATH+'/tm/ardj.sqlite')[8])
            query_r = fetchQuery("SELECT label, COUNT(track_id) AS tc FROM labels WHERE NOT label LIKE '%%:%%' GROUP BY label ORDER BY tc DESC LIMIT 20")
            c['labels'] = sorted([one[0] for one in query_r or []])
            query_r = fetchQuery("SELECT DISTINCT label FROM labels WHERE NOT label LIKE '%%:%%'")
            c['allLabels'] = sorted([one[0] for one in query_r or [] if one[0]])
            c['tracksCount'] = fetchQuery("SELECT COUNT(*) FROM tracks WHERE weight>0")[0][0]
            c['setSearchData'] = ''
            if self.get_argument('permalink','1') == '1':
                data = json.dumps(self.getSearchData())
                c['setSearchData'] = u"""
                    var searchDataSet = $.parseJSON('%s');
                    showInfo(searchDataSet);
                """%data
                print c['setSearchData']
            return render_to_response("tmbase.html", c)
        else:
            data = self.getSearchData()
            jsonData = json.dumps(data)
            return jsonData
