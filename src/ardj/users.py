# encoding=utf-8

import time

from ardj import database
from ardj import settings


def get_voters():
    """Returns information on voters in tuples (email, count, weight)."""
    rows = database.fetch('SELECT v.email, COUNT(*) AS c, k.weight '
        'FROM votes v LEFT JOIN karma k ON k.email = v.email '
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


def get_aliases():
    """Returns user aliases."""
    return settings.get2("jabber_aliases", "jabber/aliases", {})


def resolve_alias(jid):
    """Resolves an addres according to configured aliases."""
    for main, other in get_aliases().items():
        if jid in other:
            return main
    return jid


def merge_aliased_votes():
    """Moves votes from aliases to real jids."""
    for k, v in get_aliases().items():
        for alias in v:
            database.execute("UPDATE votes SET email = ? WHERE email = ?", (k, alias, ))
    database.commit()
