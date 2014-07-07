import tempfile

from database import Token, Message, commit
from users import resolve_alias
from util import run
from settings import get as get_setting
from mail import TokenMailer


def create_token(login, login_type):
    if login_type == "jid":
        login = resolve_alias(login)

    tmp = tempfile.mktemp(suffix="", prefix="", dir="")
    token = Token(token=tmp, login=login, login_type=login_type, active=1)
    token.put(force_insert=True)

    TokenMailer(login, token["token"]).deliver()

    commit()


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


def get_active_tokens():
    """Returns active tokens"""
    return [t for t in Token.find_all()
        if t["active"]]
