# encoding=utf-8

import time

from ardj import settings
from ardj.database import fetch, fetchcol


def get_voters():
    """Returns information on voters in tuples (email, count, weight)."""
    rows = database.fetch('SELECT v.email, COUNT(*) AS c, k.weight '
        'FROM votes v INNER JOIN karma k ON k.email = v.email '
        'GROUP BY v.email ORDER BY c DESC, k.weight DESC, v.email')
    return rows


def get_top_recent_voters(count=10, days=14):
    """Returns top 10 voters for last 2 weeks."""
    if not count:
        return []
    delta = int(time.time()) - days * 86400
    emails = database.fetchcol("SELECT `email`, COUNT(*) AS `c` FROM `votes` "
        "WHERE `ts` >= ? GROUP BY `email` ORDER BY `c` DESC "
        "LIMIT %u" % count, (delta, ))
    return emails


def get_admins(safe=False):
    """Returns jids/emails of admins."""
    admins = settings.get2("jabber_admins", "jabber/access", [])
    if not safe:
        count = settings.get("promote_voters", 0)
        days = settings.get("promote_voters_days", 14)
        admins += get_top_recent_voters(count, days)
    return admins
