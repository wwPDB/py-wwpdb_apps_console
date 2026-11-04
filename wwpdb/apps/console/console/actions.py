##
# File:  actions.py
# Date:  28-Oct-2026
##
"""Per-deposition backends for console actions (To Do, Level 2, Status, Communication, AnnMod)."""

from wwpdb.apps.console.console import catalog
from wwpdb.apps.workmanager.db_access.StatusDbApi import StatusDbApi


def _level2_class_id(module_row, operation):
    class_id = module_row["class_id"]
    if operation == "run_ui":
        return class_id + "UI"
    return class_id


def _level2_class_file(sdb, class_id, operation):
    class_info = sdb.getWfClassByID(classID=class_id)
    if not class_info or not class_info.get("class_file"):
        raise ValueError("Unknown workflow class '%s'." % class_id)
    class_file = str(class_info["class_file"])
    if operation == "restart":
        if class_file.find(".bf.xml") < 0:
            class_file = "Annotation.bf.xml:" + str(class_id)
    return class_file


def run_add_to_my_todo(sdb, deposition_id, annotator):
    existing = sdb.getAnnoSelection(depositionids=[deposition_id])
    if existing:
        return "already on TO DO"
    sdb.addToMyList(deposition_id, annotator)
    return "added to TO DO"


def run_remove_from_my_todo(sdb, deposition_id, annotator):  # pylint: disable=unused-argument
    existing = sdb.getAnnoSelection(depositionids=[deposition_id])
    if not existing:
        return "not on TO DO"
    sdb.removeFromMyList(deposition_id)
    return "removed from TO DO"


def run_level2(sdb, deposition_id, module_row, operation):
    class_id = _level2_class_id(module_row, operation)
    class_file = _level2_class_file(sdb, class_id, operation)
    instance_id = None
    last = sdb.getLastWFInstance(depositionid=deposition_id, classid=class_id)
    if last and last.get("wf_inst_id"):
        instance_id = last["wf_inst_id"]
    msg = sdb.insertCommunicationCommand(
        depositionid=deposition_id,
        instid=instance_id,
        classid=class_id,
        command="restartGoWF",
        classname=class_file,
        dataversion="latest",
    )
    if msg != "OK":
        raise ValueError(msg or "Failed to queue workflow command.")
    op_label = "Run+UI" if operation == "run_ui" else ("Restart" if operation == "restart" else "Run")
    return "queued %s %s" % (op_label, class_id)


def run_action(site_id, action_id, deposition_id, annotator, extra, verbose=False, log=None, req_obj=None):
    sdb = StatusDbApi(siteId=site_id, verbose=verbose, log=log)
    if action_id == catalog.ACTION_ADD_TO_MY_TODO:
        return run_add_to_my_todo(sdb, deposition_id, annotator)
    if action_id == catalog.ACTION_REMOVE_FROM_MY_TODO:
        return run_remove_from_my_todo(sdb, deposition_id, annotator)
    if action_id == catalog.ACTION_RUN_OR_RESTART_LEVEL2_MODULE:
        module_row, operation = catalog.validate_level2_choice(
            (extra or {}).get("level2_module"),
            (extra or {}).get("level2_operation"),
        )
        return run_level2(sdb, deposition_id, module_row, operation)
    if action_id in (
        catalog.ACTION_RELOAD_DATA_FILE,
        catalog.ACTION_EXTEND_HOLD_DATE,
        catalog.ACTION_SET_AUTH_VALIDATION_LETTER,
        catalog.ACTION_SEND_TEMPLATE_MESSAGE,
        catalog.ACTION_ADD_INTERNAL_NOTE,
        catalog.ACTION_SET_INTERNAL_NOTES_FLAG,
        catalog.ACTION_ANNMOD_FINISH,
        catalog.ACTION_ANNMOD_ASSIGN_ALL_MONOMERS,
    ):
        if req_obj is None:
            raise ValueError("This action needs a Work Manager session.")
    if action_id == catalog.ACTION_RELOAD_DATA_FILE:
        from wwpdb.apps.console.console import status_ops

        return status_ops.run_reload(req_obj, deposition_id, annotator, verbose=verbose, log=log)
    if action_id == catalog.ACTION_EXTEND_HOLD_DATE:
        from wwpdb.apps.console.console import status_ops

        return status_ops.run_extend_hold(req_obj, deposition_id, annotator, extra, verbose=verbose, log=log)
    if action_id == catalog.ACTION_SET_AUTH_VALIDATION_LETTER:
        from wwpdb.apps.console.console import status_ops

        return status_ops.run_set_auth(req_obj, deposition_id, annotator, extra, verbose=verbose, log=log)
    if action_id == catalog.ACTION_SEND_TEMPLATE_MESSAGE:
        from wwpdb.apps.console.console import msg_ops

        return msg_ops.send_template(
            req_obj, deposition_id, annotator, (extra or {}).get("message_template_id"), verbose=verbose, log=log
        )
    if action_id == catalog.ACTION_ADD_INTERNAL_NOTE:
        from wwpdb.apps.console.console import msg_ops

        return msg_ops.add_internal_note(req_obj, deposition_id, annotator, extra, verbose=verbose, log=log)
    if action_id == catalog.ACTION_SET_INTERNAL_NOTES_FLAG:
        from wwpdb.apps.console.console import msg_ops

        return msg_ops.set_notes_flag(req_obj, deposition_id, annotator, extra, verbose=verbose, log=log)
    if action_id == catalog.ACTION_ANNMOD_FINISH:
        from wwpdb.apps.console.console import annmod_ops

        return annmod_ops.run_open_and_finish(req_obj, deposition_id, annotator, extra=None, verbose=verbose, log=log)
    if action_id == catalog.ACTION_ANNMOD_ASSIGN_ALL_MONOMERS:
        from wwpdb.apps.console.console import annmod_ops

        extra_ann = dict(extra or {})
        extra_ann["assign_all_monomers"] = True
        return annmod_ops.run_open_and_finish(
            req_obj, deposition_id, annotator, extra=extra_ann, verbose=verbose, log=log
        )
    raise ValueError("Unknown or not-yet-implemented action.")
