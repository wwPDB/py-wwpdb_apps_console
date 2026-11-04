##
# File:  msg_ops.py
# Date:  28-Oct-2026
##
"""Communication Module actions for the annotator batch console."""

import os
import sys

from wwpdb.apps.console.console import catalog
from wwpdb.apps.workmanager.db_access.StatusDbApi import StatusDbApi
from wwpdb.io.locator.PathInfo import PathInfo


def _exp_method(site_id, deposition_id, verbose, log):
    sdb = StatusDbApi(siteId=site_id, verbose=verbose, log=log)
    last = sdb.getLastInstance(depositionid=deposition_id)
    if last and last.get("dep_exp_method"):
        return str(last.get("dep_exp_method") or "")
    return ""


def _is_em(exp_method):
    text = str(exp_method or "").upper()
    return ("ELECTRON MICROSCOPY" in text) or ("ELECTRON CRYSTALLOGRAPHY" in text)


def _prepare_req(req_obj, deposition_id, annotator, exp_method):
    req_obj.setValue("identifier", deposition_id)
    req_obj.setValue("filesource", "archive")
    req_obj.setValue("annotator", annotator)
    req_obj.setValue("sender", annotator)
    req_obj.setValue("expmethod", exp_method or "")
    req_obj.setValue("content_type", "msgs")
    if _is_em(exp_method):
        req_obj.setValue("em_entry", "true")
    else:
        req_obj.setValue("em_entry", "false")


def _messaging_io(req_obj, verbose, log):
    from wwpdb.apps.msgmodule.io.MessagingIo import MessagingIo

    return MessagingIo(req_obj, verbose=verbose, log=log)


def _process(mio, msg_obj):
    ok, _updated, failed_refs = mio.processMsg(msg_obj)
    if not ok:
        extra = ""
        if failed_refs:
            extra = " Failed file types: " + ", ".join(failed_refs)
        raise ValueError("Failed to send message." + extra)
    return "message sent"


def send_template(req_obj, deposition_id, annotator, template_id, verbose=False, log=sys.stderr):
    from wwpdb.apps.msgmodule.depict.MessagingTemplates import MessagingTemplates
    from wwpdb.apps.msgmodule.models.Message import AutoMessage

    row = catalog.validate_message_template(template_id)
    context = row["context"]
    site_id = str(req_obj.getValue("WWPDB_SITE_ID") or "")
    exp_method = _exp_method(site_id, deposition_id, verbose, log)
    _prepare_req(req_obj, deposition_id, annotator, exp_method)
    mio = _messaging_io(req_obj, verbose, log)

    if context in catalog.AUTOMSG_CONTEXTS:
        result = mio.autoMsg([deposition_id], p_tmpltType=context, p_isEmdbEntry=_is_em(exp_method), p_sender=annotator)
        info = (result or {}).get(deposition_id) or {}
        if str(info.get("success") or "").lower() != "true":
            raise ValueError(info.get("append_msg") or "Failed to send message.")
        return "sent %s" % row["label"]

    if context in catalog.HOLD_EXTENSION_CONTEXTS:
        months = catalog.HOLD_EXTENSION_CONTEXTS[context]
        hold_date = ""
        try:
            from wwpdb.apps.console.console import status_ops

            _du, file_path = status_ops.fetch_model(req_obj, deposition_id, verbose, log)
            info, em = status_ops.read_entry_info(file_path, verbose, log)
            hold_date = str(info.get("hold_coord_date") or em.get("em_map_hold_date") or "").strip()
        except Exception:  # noqa: BLE001
            hold_date = ""
        if not hold_date:
            raise ValueError("No hold date on the model; cannot send an extension letter.")
        if not mio.sendHoldExtensionNotice(deposition_id, months, hold_date, annotator):  # pylint: disable=no-member
            raise ValueError("Failed to send extension message.")
        return "sent %s" % row["label"]

    mio.initializeDataStore()
    template_dict = {"identifier": deposition_id}
    mio.getMsgTmpltDataItems(template_dict)
    starter = mio.getStarterMsgBody()
    template_dict["starter_msg_body"] = starter if starter is not None else ""
    acc = template_dict.get("accession_ids") or deposition_id
    em_entry = str(template_dict.get("em_entry") or "").lower() == "true"
    map_only = str(template_dict.get("maponly") or "").lower() == "true" or str(template_dict.get("pdb_id") or "") == "[PDBID NOT AVAIL]"
    attach = True
    try:
        if context == "vldtn":
            body = MessagingTemplates.msgTmplt_vldtn % template_dict
            files_bit = "Processed files" if map_only else "Validation report and processed files"
            subject = "%s - %s are ready for your review" % (acc, files_bit)
            file_refs = mio.checkAvailFiles(deposition_id)
        elif context == "default":
            tmpl = MessagingTemplates.msgTmplt_default_em if em_entry else MessagingTemplates.msgTmplt_default
            body = tmpl % template_dict
            subject = "Communication regarding %s" % acc
            file_refs = []
            attach = False
        elif context == "withdrawn":
            if em_entry and map_only:
                tmpl = MessagingTemplates.msgTmplt_withdrawn_em_map_only
            elif em_entry:
                tmpl = MessagingTemplates.msgTmplt_withdrawn_em
            else:
                tmpl = MessagingTemplates.msgTmplt_withdrawn
            body = tmpl % template_dict
            has_have = template_dict.get("has_have") or "has "
            subject = "%s %sbeen withdrawn" % (acc, has_have)
            file_refs = mio.checkAvailFiles(deposition_id)
        elif context == "system-unlocked":
            status_code = str(template_dict.get("status_code") or "")
            pdb_id = str(template_dict.get("pdb_id") or "")
            if status_code == "REL" and pdb_id != "[PDBID NOT AVAIL]":
                tmpl = MessagingTemplates.msgTmplt_systemUnlockedPostRel
            elif em_entry:
                tmpl = MessagingTemplates.msgTmplt_systemUnlocked_em
            else:
                tmpl = MessagingTemplates.msgTmplt_systemUnlocked
            body = tmpl % template_dict
            subject = "System Unlocked"
            file_refs = []
            attach = False
        else:
            raise ValueError("Choose a Communication template.")
    except KeyError as exc:
        raise ValueError("Could not fill Communication template (missing %s)." % (exc,))  # pylint: disable=raise-missing-from
    if not attach:
        file_refs = []
    message_dict = {
        "deposition_data_set_id": deposition_id,
        "sender": annotator,
        "context_type": context,
        "context_value": None,
        "message_subject": subject,
        "message_text": body,
        "send_status": "Y",
        "message_type": "text",
    }
    msg_obj = AutoMessage(message_dict, file_refs or [], verbose, log)
    _process(mio, msg_obj)
    return "sent %s" % row["label"]


def add_internal_note(req_obj, deposition_id, annotator, extra, verbose=False, log=sys.stderr):
    from wwpdb.apps.msgmodule.models.Message import Note

    subject = str((extra or {}).get("note_subject") or "").strip()
    body = str((extra or {}).get("note_body") or "").strip()
    if not subject or not body:
        raise ValueError("Enter a note subject and body.")
    site_id = str(req_obj.getValue("WWPDB_SITE_ID") or "")
    exp_method = _exp_method(site_id, deposition_id, verbose, log)
    _prepare_req(req_obj, deposition_id, annotator, exp_method)
    req_obj.setValue("content_type", "notes")
    mio = _messaging_io(req_obj, verbose, log)
    message_dict = {
        "deposition_data_set_id": deposition_id,
        "sender": annotator,
        "context_type": "note",
        "context_value": None,
        "message_subject": subject,
        "message_text": body,
        "send_status": "Y",
        "message_type": "text",
        "message_state": "livemsg",
    }
    note = Note(message_dict, [], verbose, log)
    _process(mio, note)
    return "note added"


def _notes_flag_path(req_obj, deposition_id, verbose, log):
    site_id = str(req_obj.getValue("WWPDB_SITE_ID") or "")
    session_path = req_obj.getSessionPath()
    pI = PathInfo(siteId=site_id, sessionPath=session_path, verbose=verbose, log=log)
    archive_pth = pI.getArchivePath(deposition_id)
    return os.path.join(archive_pth, "NOTES_FLAGGING_STATUS")


def set_notes_flag(req_obj, deposition_id, annotator, extra, verbose=False, log=sys.stderr):  # pylint: disable=unused-argument
    wanted = catalog.validate_notes_flag((extra or {}).get("notes_flag"))
    path = _notes_flag_path(req_obj, deposition_id, verbose, log)
    current = ""
    if os.access(path, os.R_OK):
        fp = open(path, "r")
        try:
            current = (fp.read() or "").strip().lower()
        finally:
            fp.close()
    if current == wanted:
        return "notes flag already %s" % ("on" if wanted == "true" else "off")
    dest_dir = os.path.dirname(path)
    if dest_dir and not os.path.isdir(dest_dir):
        raise ValueError("Archive path not found for %s." % deposition_id)
    fp = open(path, "w")
    try:
        fp.write("%s\n" % wanted)
    finally:
        fp.close()
    try:
        sdb = StatusDbApi(siteId=str(req_obj.getValue("WWPDB_SITE_ID") or ""), verbose=verbose, log=log)
        last = sdb.getLastInstance(depositionid=deposition_id) or {}
        notify = str(last.get("dep_notify") or "")
        if wanted == "true":
            if "*" not in notify:
                notify = notify + "*"
        else:
            notify = notify.replace("*", "")
        sdb.runUpdate(table="deposition", where={"dep_set_id": deposition_id}, data={"notify": notify})
    except Exception:  # noqa: BLE001
        pass
    return "notes flag %s" % ("enabled" if wanted == "true" else "disabled")
