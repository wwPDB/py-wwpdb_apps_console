##
# File:  jobs.py
# Date:  28-Oct-2026
##
"""Ephemeral console job progress, stored under the WFM session directory."""

import json
import os
import re
import uuid
from datetime import datetime

from wwpdb.apps.console.console import catalog

_DEP_ID = re.compile(r"^D_\d+$", re.I)


_DEP = re.compile(r"^D_?\d+$", re.I)
_PDB = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
_EMD = re.compile(r"^EMD(?:B)?-?\d+$", re.I)
_BMRB = re.compile(r"^\d+$")
_SAS = re.compile(r"^SAS[A-Za-z0-9]+$", re.I)


def parse_entry_tokens(raw):
    """Identifiers for a set-level archive edit.

    Accepts deposition ids and PDB, EMDB, BMRB, and SAS codes. Raises ValueError
    when a token is not one of those, so a typo is not silently dropped.
    """
    tokens = []
    seen = set()
    rejected = []
    for part in re.split(r"[\s,;]+", str(raw or "")):
        text = part.strip()
        if not text or text.startswith("#"):
            continue
        if _DEP.match(text):
            norm = "D_" + re.sub(r"\D", "", text)
        elif _EMD.match(text):
            norm = "EMD-" + re.sub(r"\D", "", text)
        elif _SAS.match(text):
            norm = text.upper()
        elif _PDB.match(text):
            norm = text.upper()
        elif _BMRB.match(text):
            norm = text
        else:
            rejected.append(text)
            continue
        key = norm.upper()
        if key not in seen:
            seen.add(key)
            tokens.append(norm)
    if rejected:
        raise ValueError(
            "Unrecognized identifier(s): %s. Use a deposition ID (D_…) or a PDB, EMDB, or BMRB code."
            % ", ".join(rejected)
        )
    return tokens


def parse_deposition_ids(raw):
    ids = []
    seen = set()
    text = str(raw or "")
    for part in re.split(r"[\s,;]+", text):
        s = part.strip().upper()
        if not s:
            continue
        if s.startswith("D") and not s.startswith("D_"):
            s = "D_" + s[1:].lstrip("_")
        if not _DEP_ID.match(s):
            continue
        if s not in seen:
            seen.add(s)
            ids.append(s)
    return ids


def jobs_root(session_path):
    return os.path.join(session_path, "console_jobs")


def job_dir(session_path, job_id):
    return os.path.join(jobs_root(session_path), job_id)


def _progress_path(session_path, job_id):
    return os.path.join(job_dir(session_path, job_id), "progress.json")


def _log_path(session_path, job_id):
    return os.path.join(job_dir(session_path, job_id), "run.log")


def _cancel_path(session_path, job_id):
    return os.path.join(job_dir(session_path, job_id), "cancel.flag")


def _now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    fp = open(tmp, "w")
    try:
        json.dump(data, fp, indent=2)
        fp.flush()
        os.fsync(fp.fileno())
    finally:
        fp.close()
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)


def new_job(session_path, action_id, annotator, deposition_ids, extra=None):
    job_id = str(uuid.uuid4())
    dest = job_dir(session_path, job_id)
    os.makedirs(dest)
    rows = []
    for dep_id in deposition_ids:
        rows.append({"deposition_id": dep_id, "status": "waiting", "error": "", "detail": "", "outcome": ""})
    progress = {
        "job_id": job_id,
        "action_id": action_id,
        "action_title": catalog.action_label(action_id),
        "annotator": annotator,
        "status": "running",
        "created_at": _now(),
        "updated_at": _now(),
        "error": "",
        "deposition_ids": list(deposition_ids),
        "rows": rows,
        "ok": 0,
        "failed": 0,
        "running": 0,
        "waiting": len(deposition_ids),
        "log": [],
        "extra": extra or {},
    }
    _atomic_write_json(_progress_path(session_path, job_id), progress)
    fp = open(_log_path(session_path, job_id), "w")
    fp.close()
    return progress


def load_progress(session_path, job_id):
    path = _progress_path(session_path, job_id)
    if not os.path.isfile(path):
        return None
    fp = open(path, "r")
    try:
        return json.load(fp)
    except (IOError, ValueError, TypeError):
        return None
    finally:
        fp.close()


def append_log(session_path, job_id, line):
    text = str(line or "").rstrip() + "\n"
    fp = open(_log_path(session_path, job_id), "a")
    try:
        fp.write(text)
    finally:
        fp.close()
    progress = load_progress(session_path, job_id)
    if not progress:
        return
    log_lines = list(progress.get("log") or [])
    log_lines.append(text.rstrip("\n"))
    if len(log_lines) > 400:
        log_lines = log_lines[-400:]
    progress["log"] = log_lines
    progress["updated_at"] = _now()
    _atomic_write_json(_progress_path(session_path, job_id), progress)


def set_row(session_path, job_id, deposition_id, status, error="", detail=None, outcome=None):
    progress = load_progress(session_path, job_id)
    if not progress:
        return
    for row in progress.get("rows") or []:
        if row.get("deposition_id") == deposition_id:
            row["status"] = status
            row["error"] = error or ""
            if detail is not None:
                row["detail"] = detail
            if outcome is not None:
                row["outcome"] = outcome
            break
    counts = {"ok": 0, "failed": 0, "running": 0, "waiting": 0}
    for row in progress.get("rows") or []:
        st = str(row.get("status") or "waiting")
        if st in counts:
            counts[st] += 1
    progress.update(counts)
    progress["updated_at"] = _now()
    _atomic_write_json(_progress_path(session_path, job_id), progress)


def finish_job(session_path, job_id, status="done", error=""):
    progress = load_progress(session_path, job_id)
    if not progress:
        return
    progress["status"] = status
    progress["error"] = error or ""
    progress["updated_at"] = _now()
    _atomic_write_json(_progress_path(session_path, job_id), progress)


def request_cancel(session_path, job_id):
    dest = job_dir(session_path, job_id)
    if not os.path.isdir(dest):
        return False
    fp = open(_cancel_path(session_path, job_id), "w")
    fp.write("1\n")
    fp.close()
    return True


def cancel_requested(session_path, job_id):
    return os.path.isfile(_cancel_path(session_path, job_id))
