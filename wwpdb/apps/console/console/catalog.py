##
# File:  catalog.py
# Date:  28-Oct-2026
#
# Action ids and Level 2 module choices for the annotator batch console.
##
"""Catalog of console actions. Keep in sync with htdocs/console/js/console.js labels."""

ACTION_ADD_TO_MY_TODO = "add_to_my_todo"
ACTION_REMOVE_FROM_MY_TODO = "remove_from_my_todo"
ACTION_RUN_OR_RESTART_LEVEL2_MODULE = "run_or_restart_level2_module"
ACTION_RELOAD_DATA_FILE = "reload_data_file"
ACTION_EXTEND_HOLD_DATE = "extend_hold_date"
ACTION_SET_AUTH_VALIDATION_LETTER = "set_auth_validation_letter"
ACTION_SEND_TEMPLATE_MESSAGE = "send_template_message"
ACTION_ADD_INTERNAL_NOTE = "add_internal_note"
ACTION_SET_INTERNAL_NOTES_FLAG = "set_internal_notes_flag"
ACTION_ANNMOD_FINISH = "annmod_finish"
ACTION_ANNMOD_ASSIGN_ALL_MONOMERS = "annmod_assign_all_monomers"

IMPLEMENTED_ACTION_IDS = frozenset(
    (
        ACTION_ADD_TO_MY_TODO,
        ACTION_REMOVE_FROM_MY_TODO,
        ACTION_RUN_OR_RESTART_LEVEL2_MODULE,
        ACTION_RELOAD_DATA_FILE,
        ACTION_EXTEND_HOLD_DATE,
        ACTION_SET_AUTH_VALIDATION_LETTER,
        ACTION_SEND_TEMPLATE_MESSAGE,
        ACTION_ADD_INTERNAL_NOTE,
        ACTION_SET_INTERNAL_NOTES_FLAG,
        ACTION_ANNMOD_FINISH,
        ACTION_ANNMOD_ASSIGN_ALL_MONOMERS,
    )
)

ACTION_LABELS = {
    ACTION_ADD_TO_MY_TODO: "Add to my TO DO",
    ACTION_REMOVE_FROM_MY_TODO: "Remove from my TO DO",
    ACTION_RUN_OR_RESTART_LEVEL2_MODULE: "Run or Restart a module",
    ACTION_RELOAD_DATA_FILE: "Reload data file",
    ACTION_EXTEND_HOLD_DATE: "Extend hold date",
    ACTION_SET_AUTH_VALIDATION_LETTER: "Set to AUTH and send Validation Letter",
    ACTION_SEND_TEMPLATE_MESSAGE: "Send template message",
    ACTION_ADD_INTERNAL_NOTE: "Add internal note",
    ACTION_SET_INTERNAL_NOTES_FLAG: "Enable or disable internal notes",
    ACTION_ANNMOD_FINISH: "Open AnnMod and Finish",
    ACTION_ANNMOD_ASSIGN_ALL_MONOMERS: "Open AnnMod, assign all monomers, and Finish",
}

# Communication UI ids (cmps_*) and the context_type stored on the message.
MESSAGE_TEMPLATES = (
    {"id": "cmps_default", "context": "default", "label": "Default"},
    {"id": "cmps_vldtn", "context": "vldtn", "label": "Validation Report"},
    {"id": "cmps_approval-expl", "context": "approval-expl", "label": "Approval Explicit"},
    {"id": "cmps_approval-impl", "context": "approval-impl", "label": "Approval Implicit"},
    {"id": "cmps_reminder", "context": "reminder", "label": "Reminder"},
    {"id": "cmps_extension-3mo", "context": "extension-3mo", "label": "Extension 3 months"},
    {"id": "cmps_extension-6mo", "context": "extension-6mo", "label": "Extension 6 months"},
    {"id": "cmps_release-publ", "context": "release-publ", "label": "Release w/ Publication"},
    {"id": "cmps_release-nopubl", "context": "release-nopubl", "label": "Release w/o Publication"},
    {"id": "cmps_system-unlocked", "context": "system-unlocked", "label": "System Unlocked"},
    {"id": "cmps_withdrawn", "context": "withdrawn", "label": "Withdrawn"},
)

AUTOMSG_CONTEXTS = frozenset(
    ("approval-expl", "approval-impl", "reminder", "release-publ", "release-nopubl")
)
HOLD_EXTENSION_CONTEXTS = {"extension-3mo": "3", "extension-6mo": "6"}

# id -> workflow class_id used in status.communication / wf_class_dict
LEVEL2_MODULES = (
    {"id": "reportmod", "class_id": "ReportMod", "label": "ReportMod", "has_run_ui": False},
    {"id": "transmod", "class_id": "TransMod", "label": "TransMod", "has_run_ui": True},
    {"id": "ligmod", "class_id": "LigMod", "label": "LigMod", "has_run_ui": True},
    {"id": "seqmod", "class_id": "SeqMod", "label": "SeqMod", "has_run_ui": True},
    {"id": "annmod", "class_id": "AnnMod", "label": "AnnMod", "has_run_ui": True},
    {"id": "valmod", "class_id": "ValMod", "label": "ValMod", "has_run_ui": False},
    {"id": "reportmod2", "class_id": "ReportMod2", "label": "ReportMod2", "has_run_ui": False},
    {"id": "statmod", "class_id": "StatMod", "label": "StatMod", "has_run_ui": False},
)

LEVEL2_OPERATIONS = (
    {"id": "run", "label": "Run"},
    {"id": "run_ui", "label": "Run+UI"},
    {"id": "restart", "label": "Restart"},
)


def action_label(action_id):
    return ACTION_LABELS.get(action_id, action_id)


def level2_module_by_id(module_id):
    wanted = str(module_id or "").strip().lower()
    for row in LEVEL2_MODULES:
        if row["id"] == wanted:
            return row
    return None


def validate_level2_choice(module_id, operation):
    row = level2_module_by_id(module_id)
    op = str(operation or "").strip().lower()
    if not row:
        raise ValueError("Choose a Level 2 module.")
    if op not in ("run", "run_ui", "restart"):
        raise ValueError("Choose Run, Run+UI, or Restart.")
    if op == "run_ui" and not row.get("has_run_ui"):
        raise ValueError("Run+UI is not available for that module. Choose Run or Restart.")
    return row, op


def message_template_by_id(template_id):
    wanted = str(template_id or "").strip()
    if wanted.startswith("cmps_"):
        wanted_ctx = wanted[5:]
    else:
        wanted_ctx = wanted
    for row in MESSAGE_TEMPLATES:
        if row["id"] == wanted or row["context"] == wanted or row["context"] == wanted_ctx:
            return row
    return None


def validate_message_template(template_id):
    row = message_template_by_id(template_id)
    if not row:
        raise ValueError("Choose a Communication template.")
    return row


def validate_hold_months(raw):
    months = str(raw or "").strip()
    if months not in ("3", "6"):
        raise ValueError("Choose 3 or 6 months.")
    return months


def validate_notes_flag(raw):
    val = str(raw or "").strip().lower()
    if val in ("enable", "on", "true", "yes", "1"):
        return "true"
    if val in ("disable", "off", "false", "no", "0"):
        return "false"
    raise ValueError("Choose enable or disable for the notes flag.")
