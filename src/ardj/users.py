# encoding=utf-8

import time

from ardj import settings
from ardj.database import fetch


def get_voters():
    """Returns information on voters in tuples (email, count, weight)."""
    rows = ardj.database.fetch('SELECT v.email, COUNT(*) AS c, k.weight '
        'FROM votes v INNER JOIN karma k ON k.email = v.email '
        'GROUP BY v.email ORDER BY c DESC, k.weight DESC, v.email')
    return rows


def get_top_recent_voters(count=10, days=14):
    """Returns top 10 voters for last 2 weeks."""
    if not count:
        return []
    delta = int(time.time()) - days * 86400
    emails = ardj.database.fetchcol("SELECT `email`, COUNT(*) AS `c` FROM `votes` "
        "WHERE `ts` >= ? GROUP BY `email` ORDER BY `c` DESC "
        "LIMIT %u" % count, (delta, ))
    return emails


def get_admins(safe=False):
    """Returns jids/emails of admins."""
    admins = ardj.settings.get("jabber_admins", ardj.settings.get("jabber/access", []))
    if not safe:
        count = ardj.settings.get("promote_voters", 0)
        days = ardj.settings.get("promote_voters_days", 14)
        admins += get_top_recent_voters(count, days)
    return admins
