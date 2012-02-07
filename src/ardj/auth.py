import tempfile

from database import Token, Message, commit
from users import resolve_alias
from util import run


def create_token(login, login_type):
    if login_type == "jid":
        login = resolve_alias(login)

    tmp = tempfile.mktemp(suffix="", prefix="", dir="")
    token = Token(token=tmp, login=login, login_type=login_type, active=0)
    token.put(force_insert=True)

    url = "http://music.tmradio.net/api/auth?token=%s" % tmp
    message = "A third-party application is requesting access to your account. If that was you, follow this link:\n%s" % url

    if login_type == "jid":
        msg = Message(re=login, message=message)
        msg.put()
    else:
        run(["mail", "-s", "Your token", login], stdin_data=message)

    commit()

    return url


def confirm_token(token):
    saved = Token.get_by_id(token)
    if saved is None:
        return False

    if saved["active"]:
        return False

    saved["active"] = 1
    saved.put()

    return True


def get_id_by_token(token):
    saved = Token.get_by_id(token)
    if saved is None or not saved["active"]:
        return None
    return saved["login"]
