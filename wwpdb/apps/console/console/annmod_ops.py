##
# File:  annmod_ops.py
# Date:  28-Oct-2026
##
"""Annotation Module actions for the annotator batch console (open + Finish)."""

import re
import sys

from wwpdb.apps.workmanager.db_access.StatusDbApi import StatusDbApi
from wwpdb.io.locator.PathInfo import PathInfo
from wwpdb.utils.config.ConfigInfo import ConfigInfo
from wwpdb.utils.session.WebRequest import InputRequest

_ANNMOD_CLASSES = ("AnnMod", "AnnModUI")


def _waiting_annmod(site_id, deposition_id, verbose, log):
    sdb = StatusDbApi(siteId=site_id, verbose=verbose, log=log)
    last = sdb.getLastInstance(depositionid=deposition_id)
    if not last:
        raise ValueError("No workflow instance for this deposition.")
    class_id = str(last.get("wf_class_id") or last.get("class_id") or "").strip()
    inst_id = str(last.get("wf_inst_id") or last.get("inst_id") or "").strip()
    status = str(last.get("inst_status") or "").strip().lower()
    method = str(last.get("dep_exp_method") or "").strip()
    if status != "waiting":
        raise ValueError("AnnMod is not waiting (status is %s)." % (last.get("inst_status") or "unknown"))
    if class_id not in _ANNMOD_CLASSES:
        raise ValueError("Current module is %s, not AnnMod." % (class_id or "unknown"))
    if not inst_id:
        raise ValueError("No waiting AnnMod instance id.")
    return class_id, inst_id, method


def _new_annmod_req(site_id, values, verbose, log):
    cI = ConfigInfo(site_id)
    req = InputRequest({}, verbose=verbose, log=log)
    req.setValue("TopSessionPath", cI.get("SITE_WEB_APPS_TOP_SESSIONS_PATH"))
    req.setValue("TopPath", cI.get("SITE_WEB_APPS_TOP_PATH"))
    req.setValue("WWPDB_SITE_ID", site_id)
    for key, val in values.items():
        if val is None:
            continue
        req.setValue(key, val)
    return req


def _error_text(rC, fallback):
    if rC is None:
        return fallback
    try:
        if rC.isError():
            payload = getattr(rC, "_cD", {})  # pylint: disable=protected-access
            text = str(payload.get("errortext") or payload.get("statustext") or "").strip()
            text = re.sub(r"<[^>]+>", " ", text)
            text = " ".join(text.split())
            if text:
                return text
    except Exception:  # noqa: BLE001
        pass
    return fallback


def _do_annmod(req, verbose, log):
    from wwpdb.apps.ann_tasks_v2.webapp.AnnTasksWebAppWorker import AnnTasksWebAppWorker  # pylint: disable=import-error,no-name-in-module

    worker = AnnTasksWebAppWorker(reqObj=req, verbose=verbose, log=log)
    return worker.doOp()


def run_open_and_finish(req_obj, deposition_id, annotator, extra=None, verbose=False, log=sys.stderr):
    """Open waiting AnnMod (live instance) and Finish. Optional all-monomer assign first."""
    assign = bool((extra or {}).get("assign_all_monomers"))
    site_id = str((req_obj.getValue("WWPDB_SITE_ID") if req_obj is not None else "") or "")
    class_id, inst_id, method = _waiting_annmod(site_id, deposition_id, verbose, log)
    req = _new_annmod_req(
        site_id,
        {
            "identifier": deposition_id,
            "idcode": deposition_id,
            "instance": inst_id,
            "classID": class_id,
            "filesource": "wf-instance",
            "method": method,
            "annotator": annotator,
            "expmethod": method,
        },
        verbose,
        log,
    )
    req.setValue("request_path", "/service/ann_tasks_v2/new_session/wf")
    rC = _do_annmod(req, verbose, log)
    if rC is None or rC.isError():
        raise ValueError(_error_text(rC, "Failed to open AnnMod."))
    session_id = str(req.getSessionId() or "").strip()
    if not session_id:
        raise ValueError("AnnMod session was not created.")
    session_path = req.getSessionObj().getPath()
    pI = PathInfo(siteId=site_id, sessionPath=session_path, verbose=verbose, log=log)
    entry_file = pI.getFileName(
        deposition_id, contentType="model", formatType="pdbx", versionId="none", partNumber="1"
    )
    if assign:
        req.setValue("entryid", deposition_id)
        req.setValue("entryfilename", entry_file)
        req.setValue("allmonomerflag", "yes")
        req.setValue("request_path", "/service/ann_tasks_v2/assemblysavedefaultinfo")
        rC = _do_annmod(req, verbose, log)
        if rC is None or rC.isError():
            raise ValueError(_error_text(rC, "Assign all monomers failed. AnnMod is open; Finish was not run."))
    req.setValue("request_path", "/service/ann_tasks_v2/finish")
    rC = _do_annmod(req, verbose, log)
    if rC is None or rC.isError():
        raise ValueError(_error_text(rC, "AnnMod opened but Finish failed."))
    if assign:
        return "assigned all monomers and finished %s %s" % (class_id, inst_id)
    return "finished %s %s" % (class_id, inst_id)
