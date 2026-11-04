##
# File:  auth.py
# Date:  28-Oct-2026
##
"""Session file for the annotator batch console (no password stored)."""

import json
import os

AUTH_FILENAME = "console_auth.json"
ALLOWED_GROUP_CODES = frozenset(("ANN", "LANN"))


def auth_path(session_path):
    return os.path.join(session_path, AUTH_FILENAME)


def write_auth(session_path, user_info):
    data = {
        "username": str(user_info.get("user_name") or ""),
        "annotator": str(user_info.get("initials") or "").strip().upper(),
        "first_name": str(user_info.get("first_name") or ""),
        "last_name": str(user_info.get("last_name") or ""),
        "group_code": str(user_info.get("code") or "").strip().upper(),
        "group_name": str(user_info.get("group_name") or ""),
        "site": str(user_info.get("site") or ""),
    }
    fp = open(auth_path(session_path), "w")
    try:
        json.dump(data, fp, indent=2)
    finally:
        fp.close()
    return data


def read_auth(session_path):
    path = auth_path(session_path)
    if not os.path.isfile(path):
        return None
    try:
        fp = open(path, "r")
        try:
            data = json.load(fp)
        finally:
            fp.close()
    except (IOError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not data.get("annotator"):
        return None
    return data


def clear_auth(session_path):
    path = auth_path(session_path)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def group_allowed(user_info):
    code = str((user_info or {}).get("code") or "").strip().upper()
    return code in ALLOWED_GROUP_CODES


def require_console_user(session_path, annotator):
    """Return auth dict or raise ValueError if the session is not a console login."""
    data = read_auth(session_path)
    if not data:
        raise ValueError("Not signed in. Open /console/ and sign in with your Work Manager username and password.")
    wanted = str(annotator or "").strip().upper()
    stored = str(data.get("annotator") or "").strip().upper()
    if wanted and stored and wanted != stored:
        raise ValueError("Session initials do not match. Sign in again.")
    return data
