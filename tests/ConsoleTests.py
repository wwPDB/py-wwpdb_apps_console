##
# File: ConsoleTests.py
# Date:  28-Oct-2026
#
# Unit tests for the annotator batch console helpers (no live OneDep backends).
##
"""Test cases for wwpdb.apps.workmanager.console"""

import shutil
import tempfile
import unittest

if __package__ is None or __package__ == "":
    from os import path
    import sys

    sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from wwpdb.apps.console.console import actions, auth, catalog, jobs
from wwpdb.apps.console.console.status_ops import compute_extended_hold_date


class _FakeSdb(object):
    def __init__(self, selected=None):
        self.selected = list(selected or [])
        self.added = None
        self.removed = None

    def getAnnoSelection(self, depositionids=None):
        wanted = list(depositionids or [])
        hits = [row for row in self.selected if row in wanted or (isinstance(row, dict) and row.get("dep_set_id") in wanted)]
        return hits

    def addToMyList(self, deposition_id, annotator):
        self.added = (deposition_id, annotator)
        self.selected.append(deposition_id)

    def removeFromMyList(self, deposition_id):
        self.removed = deposition_id
        self.selected = [row for row in self.selected if row != deposition_id]


class CatalogTests(unittest.TestCase):
    def testActionLabel(self):
        self.assertEqual(catalog.action_label("add_to_my_todo"), "Add to my TO DO")
        self.assertEqual(catalog.action_label("not-a-real-action"), "not-a-real-action")

    def testLevel2Choice(self):
        row, op = catalog.validate_level2_choice("ligmod", "run_ui")
        self.assertEqual(row["class_id"], "LigMod")
        self.assertEqual(op, "run_ui")
        self.assertRaises(ValueError, catalog.validate_level2_choice, "nope", "run")
        self.assertRaises(ValueError, catalog.validate_level2_choice, "ligmod", "jump")
        self.assertRaises(ValueError, catalog.validate_level2_choice, "valmod", "run_ui")

    def testMessageTemplate(self):
        row = catalog.validate_message_template("cmps_vldtn")
        self.assertEqual(row["context"], "vldtn")
        self.assertEqual(catalog.message_template_by_id("reminder")["id"], "cmps_reminder")
        self.assertRaises(ValueError, catalog.validate_message_template, "nope")

    def testHoldAndNotes(self):
        self.assertEqual(catalog.validate_hold_months("3"), "3")
        self.assertEqual(catalog.validate_hold_months("6"), "6")
        self.assertRaises(ValueError, catalog.validate_hold_months, "12")
        self.assertEqual(catalog.validate_notes_flag("enable"), "true")
        self.assertEqual(catalog.validate_notes_flag("disable"), "false")
        self.assertRaises(ValueError, catalog.validate_notes_flag, "maybe")


class JobTests(unittest.TestCase):
    def setUp(self):
        self.session_path = tempfile.mkdtemp(prefix="console-job-")

    def tearDown(self):
        shutil.rmtree(self.session_path, ignore_errors=True)

    def testParseIds(self):
        ids = jobs.parse_deposition_ids("D_1000000001, d1000000002 junk D_1000000001")
        self.assertEqual(ids, ["D_1000000001", "D_1000000002"])
        self.assertEqual(jobs.parse_deposition_ids(""), [])

    def testJobLifecycle(self):
        progress = jobs.new_job(self.session_path, "add_to_my_todo", "DH", ["D_1000000001", "D_1000000002"])
        job_id = progress["job_id"]
        self.assertEqual(progress["waiting"], 2)
        jobs.set_row(self.session_path, job_id, "D_1000000001", "ok")
        jobs.set_row(self.session_path, job_id, "D_1000000002", "failed", "boom")
        jobs.append_log(self.session_path, job_id, "hello")
        jobs.finish_job(self.session_path, job_id, status="done")
        loaded = jobs.load_progress(self.session_path, job_id)
        self.assertEqual(loaded["ok"], 1)
        self.assertEqual(loaded["failed"], 1)
        self.assertEqual(loaded["status"], "done")
        self.assertTrue(jobs.request_cancel(self.session_path, job_id))
        self.assertTrue(jobs.cancel_requested(self.session_path, job_id))
        self.assertIsNone(jobs.load_progress(self.session_path, "missing"))
        self.assertFalse(jobs.request_cancel(self.session_path, "missing"))


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.session_path = tempfile.mkdtemp(prefix="console-auth-")

    def tearDown(self):
        shutil.rmtree(self.session_path, ignore_errors=True)

    def testGroupAndSession(self):
        self.assertTrue(auth.group_allowed({"code": "ann"}))
        self.assertFalse(auth.group_allowed({"code": "DEP"}))
        stored = auth.write_auth(self.session_path, {"user_name": "dh", "initials": "DH", "code": "ANN", "first_name": "D", "last_name": "H"})
        self.assertEqual(stored["annotator"], "DH")
        self.assertEqual(auth.require_console_user(self.session_path, "DH")["annotator"], "DH")
        self.assertRaises(ValueError, auth.require_console_user, self.session_path, "XX")
        auth.clear_auth(self.session_path)
        self.assertRaises(ValueError, auth.require_console_user, self.session_path, "DH")


class StatusHelperTests(unittest.TestCase):
    def testHoldDate(self):
        self.assertEqual(compute_extended_hold_date("2020-01-15", 3), "2021-04-15")
        self.assertEqual(compute_extended_hold_date("2020-01-31", 3), "2021-05-01")
        self.assertRaises(ValueError, compute_extended_hold_date, "", 3)
        self.assertRaises(ValueError, compute_extended_hold_date, "2020-01-15", "x")
        self.assertRaises(ValueError, compute_extended_hold_date, "not-a-date", 3)


class ActionTests(unittest.TestCase):
    def testAddRemoveTodo(self):
        sdb = _FakeSdb()
        self.assertEqual(actions.run_add_to_my_todo(sdb, "D_1000000001", "DH"), "added to TO DO")
        self.assertEqual(actions.run_add_to_my_todo(sdb, "D_1000000001", "DH"), "already on TO DO")
        self.assertEqual(actions.run_remove_from_my_todo(sdb, "D_1000000001", "DH"), "removed from TO DO")
        self.assertEqual(actions.run_remove_from_my_todo(sdb, "D_1000000001", "DH"), "not on TO DO")


if __name__ == "__main__":
    unittest.main()
