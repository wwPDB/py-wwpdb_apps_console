##
# File:  status_ops.py
# Date:  28-Oct-2026
##
"""Status Module actions for the annotator batch console (reload, hold, AUTH)."""

import os
import shutil
import sys
import traceback
from datetime import datetime, timedelta

from wwpdb.apps.console.console import catalog
from wwpdb.io.locator.PathInfo import PathInfo


def _truthy(raw):
    return str(raw or "").strip().lower() in ("1", "yes", "true", "on")


def compute_extended_hold_date(deposit_date, months):
    """Deposit date + 12 months + 3 or 6, matching Status JS Date.setMonth overflow."""
    text = str(deposit_date or "").strip()[:10]
    parts = text.split("-")
    if len(parts) != 3:
        raise ValueError("No deposition date; cannot extend hold.")
    try:
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        add = int(months)
    except (TypeError, ValueError):
        raise ValueError("No deposition date; cannot extend hold.")  # pylint: disable=raise-missing-from
    total = (month - 1) + add + 12
    ny = year + (total // 12)
    nm = total % 12
    return (datetime(ny, nm + 1, 1) + timedelta(days=day - 1)).strftime("%Y-%m-%d")


def _pdbx_entry_info_io(verbose, log):
    try:
        from mmcif_utils.pdbx.PdbxIo import PdbxEntryInfoIo
    except ImportError:
        from wwpdb.apps.ann_tasks_v2.report.styles.PdbxIo import PdbxEntryInfoIo  # pylint: disable=import-error,no-name-in-module
    return PdbxEntryInfoIo(verbose=verbose, log=log)


def fetch_model(req_obj, deposition_id, verbose, log):
    from wwpdb.apps.ann_tasks_v2.utils.SessionDownloadUtils import SessionDownloadUtils  # pylint: disable=import-error,no-name-in-module

    req_obj.setValue("identifier", deposition_id)
    req_obj.setValue("idcode", deposition_id)
    du = SessionDownloadUtils(req_obj, verbose=verbose, log=log)
    if not du.fetchId(deposition_id, contentType="model", formatType="pdbx"):
        raise ValueError("Status update failed, data file cannot be accessed.")
    path = du.getDownloadPath()
    if not path or not os.access(path, os.R_OK):
        raise ValueError("Status update failed, data file cannot be accessed.")
    return du, path


def read_entry_info(file_path, verbose, log):
    pdbx_i = _pdbx_entry_info_io(verbose, log)
    pdbx_i.setFilePath(file_path)
    pdbx_i.get()
    info = pdbx_i.getInfoD(contextType="info") or {}
    em = {}
    if info.get("emdb_id"):
        try:
            em.update(pdbx_i.getInfoD(contextType="em_admin") or {})
        except Exception:  # noqa: BLE001
            pass
    return info, em


def _acc_flags(info):
    req = str(info.get("reqacctypes") or "")
    has_pdb = len(req) < 2 or ("PDB" in req)
    has_em = "EMDB" in req
    return has_pdb, has_em


def _check_auth_policy(info, em, has_pdb, has_em):
    org_status = str(info.get("status_code") or "").upper()
    org_post = str(info.get("post_rel_status_code") or "")
    org_em = str(em.get("em_current_status") or "").upper()
    if has_pdb:
        if org_status == "REL" and len(org_post) == 0:
            raise ValueError("Processing status code change from REL prohibited")
        if org_status == "OBS":
            raise ValueError("Processing status code change from OBS prohibited")
    if has_em and org_em == "OBS":
        raise ValueError("Processing status code change from OBS prohibited")


def _archive_next_path(req_obj, deposition_id, verbose, log):
    site_id = str(req_obj.getValue("WWPDB_SITE_ID") or "")
    session_path = req_obj.getSessionPath()
    pI = PathInfo(siteId=site_id, sessionPath=session_path, verbose=verbose, log=log)
    return pI.getModelPdbxFilePath(
        dataSetId=deposition_id, wfInstanceId=None, fileSource="archive", versionId="next", mileStone=None
    )


def _status_update(req_obj, verbose, log):
    from wwpdb.apps.ann_tasks_v2.status.StatusUpdate import StatusUpdate  # pylint: disable=import-error,no-name-in-module

    return StatusUpdate(reqObj=req_obj, verbose=verbose, log=log)


def run_reload(req_obj, deposition_id, annotator, verbose=False, log=sys.stderr):
    from wwpdb.apps.wf_engine.engine.WFEapplications import killAllWF

    _du, file_path = fetch_model(req_obj, deposition_id, verbose, log)
    info, _em = read_entry_info(file_path, verbose, log)
    sU = _status_update(req_obj, verbose, log)
    ok1 = sU.wfLoad(
        deposition_id,
        info.get("status_code") or None,
        annotatorInitials=info.get("annotator_initials") or annotator,
        initialDepositionDate=info.get("deposit_date") or None,
        authRelCode=info.get("auth_release_code") or None,
        postRelStatusCode=info.get("post_rel_status_code") or None,
        postRelRecvdCoord=info.get("post_rel_recvd_coord") or None,
        postRelRecvdCoordDate=info.get("post_rel_recvd_coord_date") or None,
    )
    if not ok1:
        raise ValueError("WF status database update failed.")
    killAllWF(deposition_id, "statMod")
    ok2 = sU.dbLoad(file_path)
    if not ok2:
        raise ValueError("Data file status update failed.")
    return "reloaded from current model"


def run_extend_hold(req_obj, deposition_id, annotator, extra, verbose=False, log=sys.stderr):
    from wwpdb.apps.wf_engine.engine.WFEapplications import killAllWF

    months = catalog.validate_hold_months((extra or {}).get("hold_months"))
    notify = _truthy((extra or {}).get("hold_notify"))
    _du, file_path = fetch_model(req_obj, deposition_id, verbose, log)
    info, em = read_entry_info(file_path, verbose, log)
    has_pdb, has_em = _acc_flags(info)
    new_date = compute_extended_hold_date(info.get("deposit_date"), months)
    pdb_hold = new_date if has_pdb else str(info.get("hold_coord_date") or "")
    em_hold = new_date if has_em else str(em.get("em_map_hold_date") or "")
    status_d = {"em_map_hold_date": em_hold}
    em_auth = em.get("em_depui_depositor_hold_instructions") or None
    if em_auth:
        status_d["em_depui_depositor_hold_instructions"] = em_auth
    req_obj.setValue("identifier", deposition_id)
    req_obj.setValue("expmethod", info.get("experimental_methods") or "")
    req_obj.setValue("experimental_methods", info.get("experimental_methods") or "")
    req_obj.setValue("reqacctypes", info.get("reqacctypes") or "")
    req_obj.setValue("sender", annotator)
    sU = _status_update(req_obj, verbose, log)
    ok1 = True
    if has_pdb:
        ok1 = sU.wfLoad(
            deposition_id,
            annotatorInitials=info.get("annotator_initials") or annotator,
            authRelCode=info.get("auth_release_code") or None,
        )
    ok1a = True
    if has_em:
        ok1a = sU.wfEmLoad(
            deposition_id,
            annotatorInitials=info.get("annotator_initials") or annotator,
            authRelCode=em_auth,
        )
    if not (ok1 and ok1a):
        raise ValueError("WF status database update failed.")
    ok2 = sU.setBoth(
        file_path,
        file_path,
        info.get("reqacctypes") or "",
        statusCode=None,
        statusD=status_d,
        approvalType=None,
        annotatorInitials=info.get("annotator_initials") or annotator,
        authReleaseCode=info.get("auth_release_code") or None,
        holdCoordinatesDate=pdb_hold,
        processSite=info.get("process_site") or None,
        expMethods=info.get("experimental_methods") or None,
    )
    if not ok2:
        raise ValueError("Update failed.")
    archive_path = _archive_next_path(req_obj, deposition_id, verbose, log)
    shutil.copyfile(file_path, archive_path)
    ok3 = sU.dbLoad(file_path)
    killAllWF(deposition_id, "statMod")
    if not ok3:
        raise ValueError("Update failed.")
    detail = "hold date %s" % new_date
    if notify:
        sent = False
        try:
            from wwpdb.apps.msgmodule.io.MessagingIo import MessagingIo

            mio = MessagingIo(req_obj, verbose=verbose, log=log)
            sent = bool(mio.sendHoldExtensionNotice(deposition_id, months, new_date, annotator))
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=log)
            sent = False
        if sent:
            detail += "; extension message sent"
        else:
            raise ValueError("Hold date saved (%s), but the extension message was not sent." % new_date)
    return detail


def run_set_auth(req_obj, deposition_id, annotator, extra, verbose=False, log=sys.stderr):
    from wwpdb.apps.wf_engine.engine.WFEapplications import killAllWF
    from wwpdb.utils.db.StatusHistoryUtils import StatusHistoryUtils

    send_letter = _truthy((extra or {}).get("send_letter"))
    if (extra or {}).get("send_letter") is None:
        send_letter = True
    _du, file_path = fetch_model(req_obj, deposition_id, verbose, log)
    info, em = read_entry_info(file_path, verbose, log)
    has_pdb, has_em = _acc_flags(info)
    _check_auth_policy(info, em, has_pdb, has_em)
    org_status = str(info.get("status_code") or "")
    status_code = "AUTH"
    if str(org_status).upper() == "REL":
        status_code = "REL"
    post_rel = info.get("post_rel_status_code") or None
    status_d = {}
    if has_em:
        status_d["em_current_status"] = "AUTH"
    sU = _status_update(req_obj, verbose, log)
    try:
        shu = StatusHistoryUtils(reqObj=req_obj, verbose=verbose, log=log)
        shu.createHistory([deposition_id], overWrite=False, statusUpdateAuthWait=status_code)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=log)
    ok1 = True
    if has_pdb:
        ok1 = sU.wfLoad(
            deposition_id,
            status_code,
            initialDepositionDate=info.get("deposit_date") or None,
            postRelStatusCode=post_rel,
            postRelRecvdCoord=info.get("post_rel_recvd_coord") or None,
            postRelRecvdCoordDate=info.get("post_rel_recvd_coord_date") or None,
        )
    ok1a = True
    if has_em:
        ok1a = sU.wfEmLoad(deposition_id, statusCode="AUTH", annotatorInitials=annotator)
    if not (ok1 and ok1a):
        raise ValueError("WF status database update failed.")
    ok2 = sU.setBoth(
        file_path,
        file_path,
        info.get("reqacctypes") or "",
        status_code,
        status_d,
        "unassigned",
        annotatorInitials=None,
        expMethods=info.get("experimental_methods") or None,
        postRelStatusCode=post_rel,
    )
    if ok2:
        archive_path = _archive_next_path(req_obj, deposition_id, verbose, log)
        shutil.copyfile(file_path, archive_path)
    killAllWF(deposition_id, "statMod")
    ok3 = sU.dbLoad(file_path)
    if not (ok2 and ok3):
        try:
            sU.wfRollBack(idCode=deposition_id)
        except Exception:  # noqa: BLE001
            pass
        raise ValueError("Data file status update failed.")
    try:
        shu = StatusHistoryUtils(reqObj=req_obj, verbose=verbose, log=log)
        shu.updateEntryStatusHistory(
            entryIdList=[deposition_id],
            statusCode=status_code,
            annotatorInitials=annotator,
            details="Update by console",
            statusCodePrior=org_status,
        )
        shu.loadEntryStatusHistory(entryIdList=[deposition_id])
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=log)
    detail = "set to %s" % status_code
    if send_letter:
        try:
            from wwpdb.apps.console.console import msg_ops

            letter = msg_ops.send_template(req_obj, deposition_id, annotator, "cmps_vldtn", verbose=verbose, log=log)
            detail += "; " + letter
        except Exception as exc:  # noqa: BLE001
            raise ValueError("AUTH done, letter failed: %s" % (exc,))  # pylint: disable=raise-missing-from
    return detail
