##
# File:  related_entries.py
# Date:  25-Nov-2026
##
"""Cross-link a set of depositions via pdbx_database_related.

Console-owned port of the make_related_entries behavior. Archive access uses
PathInfo and the mmCIF reader. The command-line script in py-wwpdb_scripts is
unchanged and is not imported here.
"""

import os
import shutil
import sys
import tempfile

CATEGORY = "pdbx_database_related"
ITEMS = ("db_name", "db_id", "content_type", "details")
EMPTY_CIF_VALUES = ("", ".", "?", None)

DB_NAME_CONTENT_TYPE_DEFAULTS = {
    "BMRB": "unspecified",
    "PDB-Dev": "unspecified",
    "SASBDB": "associated SAS data",
    "BIOISIS": "associated SAS data",
    "TargetDB": "unspecified",
    "TargetTrack": "unspecified",
    "PDB": "unspecified",
    "EMDB": "other EM volume",
}

def _safe_token(value):
    text = str(value or "")
    for char in text:
        ok = ("A" <= char <= "Z") or ("a" <= char <= "z") or ("0" <= char <= "9") or char in ("_", "-")
        if not ok:
            raise ValueError("Unsafe identifier %r" % text)
    if not text:
        raise ValueError("Empty identifier")
    return text


class EntryInfo(object):
    """Deposition metadata needed to build one pdbx_database_related citation."""

    def __init__(self, depid, exp_method, pdb_id, emdb_id, bmrb_id, sasbdb_id=None):
        self.depid = depid
        self.exp_method = (exp_method or "").strip()
        self.pdb_id = _clean_accession(pdb_id)
        self.emdb_id = _normalize_emdb_id(emdb_id)
        self.bmrb_id = _clean_accession(bmrb_id)
        self.sasbdb_id = _normalize_sasbdb_id(sasbdb_id)

    def related_row(self, em_content_type="other EM volume"):
        """Return (db_name, db_id, content_type) when another entry cites this one."""
        method = self.exp_method.upper()
        if "SOLUTION SCATTERING" in method:
            if self.sasbdb_id:
                return ("SASBDB", self.sasbdb_id, DB_NAME_CONTENT_TYPE_DEFAULTS["SASBDB"])
            if self.pdb_id:
                return ("PDB", self.pdb_id, DB_NAME_CONTENT_TYPE_DEFAULTS["PDB"])
            raise ValueError("%s: SAS deposition has no SASBDB id (check mmcif) or PDB id" % self.depid)
        if "SOLUTION NMR" in method or "SOLID-STATE NMR" in method:
            if self.bmrb_id:
                return ("BMRB", self.bmrb_id, DB_NAME_CONTENT_TYPE_DEFAULTS["BMRB"])
            if self.pdb_id:
                return ("PDB", self.pdb_id, DB_NAME_CONTENT_TYPE_DEFAULTS["PDB"])
            raise ValueError("%s: NMR deposition has no BMRB or PDB id" % self.depid)
        if "ELECTRON MICROSCOPY" in method or "ELECTRON CRYSTALLOGRAPHY" in method:
            if self.pdb_id:
                return ("PDB", self.pdb_id, DB_NAME_CONTENT_TYPE_DEFAULTS["PDB"])
            if self.emdb_id:
                return ("EMDB", self.emdb_id, em_content_type)
            raise ValueError("%s: EM/EC deposition has no PDB or EMDB id" % self.depid)
        if self.pdb_id:
            return ("PDB", self.pdb_id, DB_NAME_CONTENT_TYPE_DEFAULTS["PDB"])
        if self.emdb_id:
            return ("EMDB", self.emdb_id, em_content_type)
        if self.bmrb_id:
            return ("BMRB", self.bmrb_id, DB_NAME_CONTENT_TYPE_DEFAULTS["BMRB"])
        raise ValueError("%s: cannot determine related accession (exp_method=%r)" % (self.depid, self.exp_method))

    def own_accession_keys(self):
        keys = set()
        if self.pdb_id:
            keys.add(("PDB", self.pdb_id.upper()))
        if self.emdb_id:
            keys.add(("EMDB", self.emdb_id.upper()))
        if self.bmrb_id:
            keys.add(("BMRB", self.bmrb_id.upper()))
        if self.sasbdb_id:
            keys.add(("SASBDB", self.sasbdb_id.upper()))
        return keys


def _clean_accession(value):
    if value in EMPTY_CIF_VALUES:
        return None
    text = str(value).strip()
    if text.upper() in ("?", "."):
        return None
    return text


def _normalize_emdb_id(value):
    text = _clean_accession(value)
    if not text:
        return None
    upper = text.upper()
    if upper.startswith("EMD-"):
        return upper
    if upper.startswith("EMD"):
        return "EMD-%s" % upper[3:].lstrip("-")
    digits = "".join(char for char in upper if char.isdigit())
    if digits:
        return "EMD-%s" % digits
    return upper


def _normalize_sasbdb_id(value):
    text = _clean_accession(value)
    if not text:
        return None
    return text.upper()


def _row_key(db_name, db_id, content_type):
    return (
        (db_name or "").strip(),
        (db_id or "").strip().upper(),
        (content_type or "").strip().lower(),
    )


def _is_empty_row(row):
    db_name = row.get("db_name", "")
    db_id = row.get("db_id", "")
    return db_name in EMPTY_CIF_VALUES and db_id in EMPTY_CIF_VALUES


def _find_reusable_index(rows, db_name):
    for index, row in enumerate(rows):
        item_db_name = row.get("db_name", "")
        item_db_id = row.get("db_id", "")
        item_content_type = row.get("content_type", "")
        name_ok = item_db_name == db_name and item_db_name not in EMPTY_CIF_VALUES
        gap = item_db_id in EMPTY_CIF_VALUES or item_content_type in EMPTY_CIF_VALUES
        if name_ok and gap:
            return index
    return None


def rows_to_add(current, others, existing_rows, em_content_type):
    """Missing related rows for one entry. Does not read or write a file."""
    existing_keys = set()
    for row in existing_rows or []:
        if _is_empty_row(row):
            continue
        existing_keys.add(_row_key(row.get("db_name", ""), row.get("db_id", ""), row.get("content_type", "")))
    own_keys = current.own_accession_keys()
    planned = []
    for other in others:
        if other.depid == current.depid:
            continue
        db_name, db_id, content_type = other.related_row(em_content_type=em_content_type)
        if (db_name, db_id.upper()) in own_keys:
            continue
        key = _row_key(db_name, db_id, content_type)
        if key in existing_keys:
            continue
        planned.append((db_name, db_id, content_type))
        existing_keys.add(key)
    return planned


def apply_planned_rows(existing_rows, planned):
    """Return the category rows after filling gaps and appending new citations."""
    rows = [dict(row) for row in (existing_rows or [])]
    for db_name, db_id, content_type in planned:
        index = _find_reusable_index(rows, db_name)
        if index is None and len(rows) == 1 and rows[0].get("db_id") in EMPTY_CIF_VALUES:
            index = 0
        if index is not None:
            rows[index]["db_name"] = db_name
            rows[index]["db_id"] = db_id
            rows[index]["content_type"] = content_type
            rows[index]["details"] = ""
            continue
        if rows:
            new_row = dict(rows[0])
        else:
            new_row = {}
            for item in ITEMS:
                new_row[item] = ""
        new_row["db_name"] = db_name
        new_row["db_id"] = db_id
        new_row["content_type"] = content_type
        new_row["details"] = ""
        rows.append(new_row)
    return rows


def describe_related_result(updated, rows, error, dry_run):
    if error:
        return error
    if not updated:
        return "unchanged"
    parts = ["%s %s (%s)" % (row["db_name"], row["db_id"], row["content_type"]) for row in rows]
    verb = "would add" if dry_run else "added"
    if not parts:
        return verb
    return verb + " " + "; ".join(parts)


def _resolve_depid(identifier, lookup):
    identifier = identifier.strip()
    if not identifier:
        return None
    if identifier.startswith("D_"):
        return identifier
    found = lookup.dep_id_for_pdb_or_emdb(identifier)
    if found:
        return found
    if identifier.isdigit():
        found = lookup.dep_id_for_bmrb(identifier)
        if found:
            return found
    if identifier.upper().startswith("SAS"):
        found = lookup.dep_id_for_sas(identifier)
        if found:
            return found
    return None


def resolve_entry_identifiers(identifiers, lookup):
    depids = []
    seen = set()
    for raw in identifiers:
        entry = str(raw or "").strip()
        if not entry or entry.startswith("#"):
            continue
        depid = _resolve_depid(entry, lookup)
        if not depid:
            raise ValueError("Could not resolve deposition id for %r" % entry)
        if depid not in seen:
            seen.add(depid)
            depids.append(depid)
    return depids


def _sas_id_from_categories(loaded):
    if not loaded:
        return None
    for row in loaded.get("database_2") or []:
        if row.get("database_id") == "SASBDB":
            return _normalize_sasbdb_id(row.get("database_code"))
    for row in loaded.get(CATEGORY) or []:
        if row.get("db_name") in ("SASBDB", "BIOISIS"):
            return _normalize_sasbdb_id(row.get("db_id"))
    return None


def load_entry_info(depid, lookup, archive):
    row = lookup.fetch(depid)
    if not row:
        raise ValueError("Deposition %s not found in status.deposition" % depid)
    _depid, exp_method, pdb_id, emdb_id, bmrb_id = row
    sasbdb_id = None
    if exp_method and "SOLUTION SCATTERING" in str(exp_method).upper():
        sasbdb_id = _sas_id_from_categories(archive.read_categories(depid))
    return EntryInfo(
        depid=depid,
        exp_method=exp_method or "",
        pdb_id=pdb_id,
        emdb_id=emdb_id,
        bmrb_id=bmrb_id,
        sasbdb_id=sasbdb_id,
    )


def prepare(identifiers, em_content_type, lookup, archive):
    """Resolve the set and how each entry will be cited. Does not write models."""
    depids = resolve_entry_identifiers(identifiers, lookup)
    if len(depids) < 2:
        raise ValueError("At least two depositions are required to create mutual related links")
    infos = [load_entry_info(depid, lookup, archive) for depid in depids]
    citations = []
    for info in infos:
        db_name, db_id, content_type = info.related_row(em_content_type=em_content_type)
        citations.append(
            {
                "deposition_id": info.depid,
                "db_name": db_name,
                "db_id": db_id,
                "content_type": content_type,
                "exp_method": info.exp_method,
            }
        )
    return {
        "deposition_ids": depids,
        "entry_infos": infos,
        "citations": citations,
        "em_content_type": em_content_type,
    }


def apply_one(depid, entry_infos, em_content_type, dry_run, archive):
    """Plan or write related rows for one deposition. Returns updated, rows, error."""
    current = None
    for info in entry_infos:
        if info.depid == depid:
            current = info
            break
    if current is None:
        raise ValueError("Internal error: %s not in the related set" % depid)
    loaded = archive.read_categories(depid)
    if loaded is None:
        return {"deposition_id": depid, "updated": False, "rows": [], "error": "no latest model mmCIF found"}
    existing = loaded.get(CATEGORY) or []
    planned = rows_to_add(current, entry_infos, existing, em_content_type)
    if not planned:
        return {"deposition_id": depid, "updated": False, "rows": [], "error": ""}
    row_dicts = []
    for db_name, db_id, content_type in planned:
        row_dicts.append({"db_name": db_name, "db_id": db_id, "content_type": content_type})
    if not dry_run:
        archive.write_related(depid, apply_planned_rows(existing, planned))
    return {"deposition_id": depid, "updated": True, "rows": row_dicts, "error": ""}


def _outcome(entry, dry_run):
    if entry["error"]:
        return "failed", "failed"
    if entry["updated"] and dry_run:
        return "would_update", "ok"
    if entry["updated"]:
        return "updated", "ok"
    return "unchanged", "ok"


def apply_plan(session_path, job_id, plan, dry_run, archive):
    """Run the set, one entry at a time, updating console job rows. Returns True if cancelled."""
    from wwpdb.apps.console.console import jobs

    infos = plan["entry_infos"]
    em_content_type = plan["em_content_type"]
    cancelled = False
    for depid in plan["deposition_ids"]:
        if jobs.cancel_requested(session_path, job_id):
            cancelled = True
            jobs.append_log(session_path, job_id, "Cancel requested; remaining IDs skipped.")
            break
        jobs.set_row(session_path, job_id, depid, "running")
        jobs.append_log(session_path, job_id, "[%s] running" % depid)
        try:
            entry = apply_one(depid, infos, em_content_type, dry_run, archive)
        except Exception as exc:  # noqa: BLE001
            err = str(exc) or "Action failed."
            jobs.set_row(session_path, job_id, depid, "failed", error=err, detail=err, outcome="failed")
            jobs.append_log(session_path, job_id, "[%s] FAILED %s" % (depid, err))
            continue
        outcome, status = _outcome(entry, dry_run)
        detail = describe_related_result(entry["updated"], entry["rows"], entry["error"], dry_run)
        jobs.set_row(
            session_path,
            job_id,
            depid,
            status,
            error=entry["error"],
            detail=detail,
            outcome=outcome,
        )
        label = "FAILED" if status == "failed" else "OK"
        jobs.append_log(session_path, job_id, "[%s] %s %s" % (depid, label, detail))
    return cancelled


class SqlDepositionLookup(object):
    """status.deposition queries. Identifiers are restricted to a safe token alphabet."""

    def _rows(self, sql):
        try:
            from wwpdb.utils.wf.dbapi.WfDbApi import WfDbApi  # pylint: disable=import-error
        except ImportError as exc:
            raise ValueError("Status database access is not available on this host.") from exc
        return WfDbApi().runSelectSQL(sql) or []

    def fetch(self, depid):
        depid = _safe_token(depid)
        sql = (
            "SELECT dep_set_id, exp_method, pdb_id, emdb_id, bmrb_id "
            "FROM status.deposition WHERE dep_set_id = '%s'" % depid
        )
        rows = self._rows(sql)
        return rows[0] if rows else None

    def dep_id_for_pdb_or_emdb(self, code):
        code = _safe_token(code)
        sql = (
            "SELECT dep_set_id FROM status.deposition "
            "WHERE lower(pdb_id) = lower('%s') OR upper(emdb_id) = upper('%s')" % (code, code)
        )
        rows = self._rows(sql)
        return rows[0][0] if rows else None

    def dep_id_for_bmrb(self, code):
        code = _safe_token(code)
        alt = code.lstrip("0") or "0"
        alt = _safe_token(alt)
        sql = "SELECT dep_set_id FROM status.deposition WHERE bmrb_id = '%s' OR bmrb_id = '%s'" % (code, alt)
        rows = self._rows(sql)
        return rows[0][0] if rows else None

    def dep_id_for_sas(self, code):
        code = _safe_token(code).upper()
        sql = "SELECT dep_set_id FROM status.deposition WHERE upper(pdb_id) = '%s'" % code
        rows = self._rows(sql)
        return rows[0][0] if rows else None


def _item_name(key):
    if isinstance(key, (list, tuple)):
        return key[0]
    return key


def _category_rows(container, name):
    cat = container.getObj(name)
    if cat is None:
        return []
    items = [_item_name(key) for key in cat.getAttributeListWithOrder()]
    rows = []
    for index in range(len(cat.data)):
        row = {}
        for item in items:
            row[item] = cat.getValueOrDefault(attributeName=item, defaultValue="", rowIndex=index)
        rows.append(row)
    return rows


def _replace_related(container, rows):
    from mmcif.api.DataCategory import DataCategory  # pylint: disable=import-error

    items = list(ITEMS)
    for row in rows:
        for key in row:
            if key not in items:
                items.append(key)
    values = []
    for row in rows:
        values.append(["" if row.get(item) is None else str(row.get(item)) for item in items])
    cat = DataCategory(CATEGORY, items, values)
    if container.getObj(CATEGORY) is None:
        container.append(cat)
        return
    if hasattr(container, "replace"):
        container.replace(cat)
        return
    if hasattr(container, "remove"):
        container.remove(CATEGORY)
        container.append(cat)
        return
    raise ValueError("mmCIF container cannot replace %s." % CATEGORY)


def _read_mmcif(path):
    from mmcif.io.IoAdapterCore import IoAdapterCore  # pylint: disable=import-error

    data = IoAdapterCore().readFile(path)
    if not data:
        raise ValueError("Could not read %s" % path)
    return data


def _write_mmcif(path, containers):
    from mmcif.io.IoAdapterCore import IoAdapterCore  # pylint: disable=import-error

    IoAdapterCore().writeFile(path, containers)


class PathInfoArchive(object):
    """Latest archive model in, next model version out."""

    def __init__(self, site_id, session_path, verbose=False, log=sys.stderr):
        self.site_id = site_id
        self.session_path = session_path
        self.verbose = verbose
        self.log = log

    def _path(self, depid, version_id):
        try:
            from wwpdb.io.locator.PathInfo import PathInfo  # pylint: disable=import-error
        except ImportError as exc:
            raise ValueError("Archive path lookup is not available on this host.") from exc
        locator = PathInfo(siteId=self.site_id, sessionPath=self.session_path, verbose=self.verbose, log=self.log)
        return locator.getModelPdbxFilePath(
            dataSetId=depid, wfInstanceId=None, fileSource="archive", versionId=version_id, mileStone=None
        )

    def read_categories(self, depid):
        path = self._path(depid, "latest")
        if not path or not os.path.isfile(path):
            return None
        containers = _read_mmcif(path)
        container = containers[0]
        return {
            CATEGORY: _category_rows(container, CATEGORY),
            "database_2": _category_rows(container, "database_2"),
        }

    def write_related(self, depid, rows):
        latest = self._path(depid, "latest")
        nxt = self._path(depid, "next")
        if not latest or not os.path.isfile(latest):
            raise ValueError("%s: no latest model mmCIF found" % depid)
        if not nxt:
            raise ValueError("%s: no next model path" % depid)
        work = tempfile.mkdtemp(prefix="related-entries-")
        try:
            dest = os.path.join(work, os.path.basename(latest))
            shutil.copy(latest, dest)
            containers = _read_mmcif(dest)
            _replace_related(containers[0], rows)
            _write_mmcif(dest, containers)
            shutil.copy(dest, nxt)
        finally:
            shutil.rmtree(work, ignore_errors=True)
