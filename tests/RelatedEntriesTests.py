##
# File: RelatedEntriesTests.py
# Date:  25-Nov-2026
#
# Citation rules, merge planning, and the set-level job. No live archive.
##
"""Tests for make-related-entries in the console."""

import shutil
import tempfile
import unittest

if __package__ is None or __package__ == "":
    from os import path
    import sys

    sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from wwpdb.apps.console.console import catalog, jobs, related_entries
from wwpdb.apps.console.console.related_entries import EntryInfo


def _info(depid, method, pdb=None, emdb=None, bmrb=None, sas=None):
    return EntryInfo(depid, method, pdb, emdb, bmrb, sas)


class _Lookup(object):
    def __init__(self, by_dep, by_code=None):
        self.by_dep = by_dep
        self.by_code = dict(by_code or {})

    def fetch(self, depid):
        return self.by_dep.get(depid)

    def dep_id_for_pdb_or_emdb(self, code):
        return self.by_code.get(code.upper())

    def dep_id_for_bmrb(self, code):
        return self.by_code.get("BMRB:" + code)

    def dep_id_for_sas(self, code):
        return self.by_code.get("SAS:" + code.upper())


class _Archive(object):
    def __init__(self, models):
        self.models = models
        self.writes = []

    def read_categories(self, depid):
        model = self.models.get(depid)
        if model is None:
            return None
        return {
            "pdbx_database_related": [dict(row) for row in model.get("pdbx_database_related") or []],
            "database_2": [dict(row) for row in model.get("database_2") or []],
        }

    def write_related(self, depid, rows):
        self.writes.append((depid, rows))
        self.models[depid]["pdbx_database_related"] = rows


class CitationTests(unittest.TestCase):
    def testXrayUsesPdb(self):
        info = _info("D_1", "X-RAY DIFFRACTION", pdb="1abc")
        self.assertEqual(info.related_row(), ("PDB", "1abc", "unspecified"))

    def testNmrPrefersBmrb(self):
        info = _info("D_1", "SOLUTION NMR", pdb="1abc", bmrb="12345")
        self.assertEqual(info.related_row(), ("BMRB", "12345", "unspecified"))

    def testNmrFallsBackToPdb(self):
        info = _info("D_1", "SOLID-STATE NMR", pdb="1abc")
        self.assertEqual(info.related_row(), ("PDB", "1abc", "unspecified"))

    def testEmWithModelUsesPdb(self):
        info = _info("D_1", "ELECTRON MICROSCOPY", pdb="7abc", emdb="EMD-1001")
        self.assertEqual(info.related_row("consensus EM volume"), ("PDB", "7abc", "unspecified"))

    def testEmVolumeUsesRequestedContentType(self):
        info = _info("D_1", "ELECTRON MICROSCOPY", emdb="emd-1001")
        self.assertEqual(info.related_row("focused EM volume"), ("EMDB", "EMD-1001", "focused EM volume"))

    def testEmWithoutAccessionRaises(self):
        info = _info("D_1", "ELECTRON MICROSCOPY")
        self.assertRaises(ValueError, info.related_row)

    def testSasUsesSasbdb(self):
        info = _info("D_1", "SOLUTION SCATTERING", sas="SASDA1")
        self.assertEqual(info.related_row(), ("SASBDB", "SASDA1", "associated SAS data"))


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.left = _info("D_1", "X-RAY DIFFRACTION", pdb="1abc")
        self.right = _info("D_2", "X-RAY DIFFRACTION", pdb="1abd")
        self.both = [self.left, self.right]

    def testPlansTheOtherEntry(self):
        planned = related_entries.rows_to_add(self.left, self.both, [], "other EM volume")
        self.assertEqual(planned, [("PDB", "1abd", "unspecified")])

    def testSkipsRowAlreadyPresent(self):
        existing = [{"db_name": "PDB", "db_id": "1ABD", "content_type": "unspecified", "details": ""}]
        planned = related_entries.rows_to_add(self.left, self.both, existing, "other EM volume")
        self.assertEqual(planned, [])

    def testSkipsEmptyExistingRow(self):
        existing = [{"db_name": "", "db_id": "?", "content_type": "", "details": ""}]
        planned = related_entries.rows_to_add(self.left, self.both, existing, "other EM volume")
        self.assertEqual(planned, [("PDB", "1abd", "unspecified")])

    def testFillsIncompleteRowThenAppends(self):
        existing = [{"db_name": "PDB", "db_id": "?", "content_type": "?", "details": "keep-me", "extra": "x"}]
        planned = [("PDB", "1abd", "unspecified"), ("PDB", "1abe", "unspecified")]
        rows = related_entries.apply_planned_rows(existing, planned)
        self.assertEqual(rows[0]["db_id"], "1abd")
        self.assertEqual(rows[0]["details"], "")
        self.assertEqual(rows[0]["extra"], "x")
        self.assertEqual(rows[1]["db_id"], "1abe")
        self.assertEqual(rows[1]["extra"], "x")
        self.assertEqual(existing[0]["db_id"], "?")

    def testDescribe(self):
        rows = [{"db_name": "PDB", "db_id": "1abd", "content_type": "unspecified"}]
        would = related_entries.describe_related_result(True, rows, "", True)
        self.assertEqual(would, "would add PDB 1abd (unspecified)")
        added = related_entries.describe_related_result(True, rows, "", False)
        self.assertEqual(added, "added PDB 1abd (unspecified)")
        self.assertEqual(related_entries.describe_related_result(False, [], "", True), "unchanged")
        missing = related_entries.describe_related_result(False, [], "no latest model mmCIF found", True)
        self.assertEqual(missing, "no latest model mmCIF found")


class PrepareTests(unittest.TestCase):
    def _lookup(self):
        return _Lookup(
            {
                "D_1000000001": ("D_1000000001", "X-RAY DIFFRACTION", "1abc", None, None),
                "D_1000000002": ("D_1000000002", "X-RAY DIFFRACTION", "1abd", None, None),
                "D_1000000003": ("D_1000000003", "SOLUTION SCATTERING", None, None, None),
            },
            {"1ABC": "D_1000000001", "1ABD": "D_1000000002"},
        )

    def testResolvesAccessionsAndCites(self):
        archive = _Archive({})
        plan = related_entries.prepare(["1abc", "D_1000000002"], "other EM volume", self._lookup(), archive)
        self.assertEqual(plan["deposition_ids"], ["D_1000000001", "D_1000000002"])
        self.assertEqual(plan["citations"][0]["db_id"], "1abc")
        self.assertEqual(plan["citations"][1]["content_type"], "unspecified")

    def testRejectsASingleDeposition(self):
        self.assertRaises(
            ValueError,
            related_entries.prepare,
            ["D_1000000001"],
            "other EM volume",
            self._lookup(),
            _Archive({}),
        )

    def testUnknownAccession(self):
        self.assertRaises(
            ValueError,
            related_entries.resolve_entry_identifiers,
            ["9zzz"],
            self._lookup(),
        )

    def testSasIdComesFromTheModel(self):
        archive = _Archive(
            {
                "D_1000000003": {
                    "database_2": [{"database_id": "SASBDB", "database_code": "sasda1"}],
                    "pdbx_database_related": [],
                }
            }
        )
        info = related_entries.load_entry_info("D_1000000003", self._lookup(), archive)
        self.assertEqual(info.related_row(), ("SASBDB", "SASDA1", "associated SAS data"))

    def testDryRunDoesNotWrite(self):
        archive = _Archive(
            {
                "D_1000000001": {"pdbx_database_related": [], "database_2": []},
                "D_1000000002": {"pdbx_database_related": [], "database_2": []},
            }
        )
        plan = related_entries.prepare(["D_1000000001", "D_1000000002"], "other EM volume", self._lookup(), archive)
        session = tempfile.mkdtemp(prefix="related-job-")
        try:
            progress = jobs.new_job(session, "make_related_entries", "DH", plan["deposition_ids"])
            cancelled = related_entries.apply_plan(session, progress["job_id"], plan, True, archive)
            self.assertFalse(cancelled)
            self.assertEqual(archive.writes, [])
            loaded = jobs.load_progress(session, progress["job_id"])
            outcomes = [row["outcome"] for row in loaded["rows"]]
            self.assertEqual(outcomes, ["would_update", "would_update"])
            self.assertIn("would add PDB 1abd", loaded["rows"][0]["detail"])
        finally:
            shutil.rmtree(session, ignore_errors=True)

    def testWriteRecordsRowsAndMissingModelFails(self):
        archive = _Archive(
            {
                "D_1000000001": {"pdbx_database_related": [], "database_2": []},
            }
        )
        plan = related_entries.prepare(["D_1000000001", "D_1000000002"], "other EM volume", self._lookup(), archive)
        session = tempfile.mkdtemp(prefix="related-job-")
        try:
            progress = jobs.new_job(session, "make_related_entries", "DH", plan["deposition_ids"])
            related_entries.apply_plan(session, progress["job_id"], plan, False, archive)
            self.assertEqual(len(archive.writes), 1)
            self.assertEqual(archive.writes[0][0], "D_1000000001")
            self.assertEqual(archive.writes[0][1][0]["db_id"], "1abd")
            loaded = jobs.load_progress(session, progress["job_id"])
            by_id = {row["deposition_id"]: row for row in loaded["rows"]}
            self.assertEqual(by_id["D_1000000001"]["outcome"], "updated")
            self.assertEqual(by_id["D_1000000002"]["outcome"], "failed")
            self.assertEqual(loaded["failed"], 1)
            self.assertEqual(loaded["ok"], 1)
        finally:
            shutil.rmtree(session, ignore_errors=True)


class TokenAndCatalogTests(unittest.TestCase):
    def testParseTokens(self):
        tokens = jobs.parse_entry_tokens("1abc, EMD-1001 D1000000001\n34567 SASDA1 #note")
        self.assertEqual(tokens, ["1ABC", "EMD-1001", "D_1000000001", "34567", "SASDA1"])

    def testRejectsJunk(self):
        self.assertRaises(ValueError, jobs.parse_entry_tokens, "1abc not-an-id")

    def testEmContentTypeAndDryRun(self):
        self.assertEqual(catalog.validate_em_content_type(""), "other EM volume")
        self.assertEqual(catalog.validate_em_content_type("consensus EM volume"), "consensus EM volume")
        self.assertRaises(ValueError, catalog.validate_em_content_type, "associated EM volume")
        self.assertTrue(catalog.validate_dry_run(""))
        self.assertTrue(catalog.validate_dry_run("yes"))
        self.assertFalse(catalog.validate_dry_run("no"))
        self.assertFalse(catalog.validate_dry_run("write"))


if __name__ == "__main__":
    unittest.main()
