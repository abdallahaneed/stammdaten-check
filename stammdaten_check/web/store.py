"""SQLite storage for runs and the work on their findings."""
import json
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .. import engine, extracts
from ..db import SQL_DIR

STATUSES = ("open", "accepted", "fixed", "false_positive")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NotFound(Exception):
    pass


class BadInput(Exception):
    pass


class Store:
    def __init__(self, home):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.db_path = self.home / "stammdaten.db"
        with self.connect() as con:
            con.executescript((SQL_DIR / "store_schema.sql").read_text(encoding="utf-8"))

    def connect(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def sql(self, name):
        return (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")

    # ---------- runs ----------

    def unpack(self, upload: bytes, target: Path):
        """Take only the CSV files out of the zip, flat, by base name.
        Paths inside the archive are ignored, so '../../etc/x.csv' cannot escape."""
        if len(upload) > MAX_UPLOAD_BYTES:
            raise BadInput("upload larger than 50 MB")
        target.mkdir(parents=True, exist_ok=True)
        tmp = target / "_upload.zip"
        tmp.write_bytes(upload)
        try:
            with zipfile.ZipFile(tmp) as z:
                names = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
                if not names:
                    raise BadInput("the zip contains no CSV files")
                for n in names:
                    base = Path(n).name.lower()
                    if base.startswith("._"):
                        continue  # macOS resource forks
                    with z.open(n) as src, open(target / base, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        except zipfile.BadZipFile:
            raise BadInput("not a valid zip file") from None
        finally:
            tmp.unlink(missing_ok=True)

    def create_run(self, label, path, source, fill):
        """fill(folder) puts the extracts into the folder (unzip or generate)."""
        if path not in ("brownfield", "greenfield", "both"):
            raise BadInput("path must be brownfield, greenfield or both")
        with self.connect() as con:
            cur = con.execute(
                "INSERT INTO runs (created_at, label, path, source, extract_dir, totals_json) "
                "VALUES (?, ?, ?, ?, '', '{}')", (now(), label, path, source))
            run_id = cur.lastrowid
        folder = self.home / "runs" / str(run_id)
        try:
            fill(folder)
            cfg = engine.load_config()
            cfg["run"]["path"] = path
            result = engine.run(folder, cfg)
        except (extracts.ExtractError, BadInput) as e:
            self.delete_run(run_id)
            raise BadInput(str(e)) from None
        except Exception:
            self.delete_run(run_id)
            raise

        f = result.findings.fillna("")
        rows = [(run_id, r.rule, r.severity, r.object, r.key, r.field, r.message, r.fix,
                 r.related, float(r.weight)) for r in f.itertuples(index=False)]
        with self.connect() as con:
            con.executemany(
                "INSERT INTO findings (run_id, rule, severity, object, key, field, message, fix, related, weight) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            con.execute("UPDATE runs SET extract_dir = ?, seconds = ?, totals_json = ? WHERE id = ?",
                        (str(folder), round(sum(result.rule_times.values()), 3),
                         json.dumps(result.totals), run_id))
        return run_id

    def list_runs(self):
        with self.connect() as con:
            rows = con.execute(
                "SELECT r.id, r.created_at, r.label, r.path, r.source, "
                "COUNT(f.id) AS findings, SUM(f.status = 'open') AS open "
                "FROM runs r LEFT JOIN findings f ON f.run_id = r.id "
                "WHERE r.extract_dir <> '' GROUP BY r.id ORDER BY r.id DESC").fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id):
        with self.connect() as con:
            run = con.execute("SELECT * FROM runs WHERE id = ? AND extract_dir <> ''", (run_id,)).fetchone()
            if run is None:
                raise NotFound(f"run {run_id} not found")
            readiness = [dict(r) for r in con.execute(self.sql("run_readiness"), {"run_id": run_id})]
            progress = [dict(r) for r in con.execute(self.sql("run_progress"), {"run_id": run_id})]
            sev = dict(con.execute(
                "SELECT severity, COUNT(*) FROM findings WHERE run_id = ? GROUP BY severity", (run_id,)).fetchall())
        out = dict(run)
        out["totals"] = json.loads(out.pop("totals_json"))
        out.pop("extract_dir")
        out.update(readiness=readiness, progress=progress, bySeverity=sev)
        return out

    def delete_run(self, run_id):
        with self.connect() as con:
            con.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        shutil.rmtree(self.home / "runs" / str(run_id), ignore_errors=True)

    def extract_dir(self, run_id):
        with self.connect() as con:
            row = con.execute("SELECT extract_dir FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None or not row["extract_dir"]:
            raise NotFound(f"run {run_id} not found")
        return Path(row["extract_dir"])

    def latest_run_id(self):
        with self.connect() as con:
            row = con.execute("SELECT MAX(id) AS id FROM runs WHERE extract_dir <> ''").fetchone()
        return row["id"]

    # ---------- findings ----------

    def findings(self, run_id, rule=None, severity=None, obj=None, status=None, q=None,
                 limit=50, offset=0):
        self.get_run(run_id)
        where, params = ["run_id = ?"], [run_id]
        for col, val in (("rule", rule), ("severity", severity), ("object", obj), ("status", status)):
            if val:
                where.append(f"{col} = ?")  # column names are fixed above, never from the request
                params.append(val)
        if q:
            where.append("(key LIKE ? OR message LIKE ? OR related LIKE ?)")
            params += [f"%{q}%"] * 3
        clause = " AND ".join(where)
        order = ("CASE severity WHEN 'blocker' THEN 0 WHEN 'error' THEN 1 "
                 "WHEN 'warning' THEN 2 ELSE 3 END, rule, key")
        with self.connect() as con:
            total = con.execute(f"SELECT COUNT(*) FROM findings WHERE {clause}", params).fetchone()[0]
            rows = con.execute(f"SELECT * FROM findings WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
                               params + [limit, offset]).fetchall()
        return [dict(r) for r in rows], total

    def get_finding(self, finding_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
            if row is None:
                raise NotFound(f"finding {finding_id} not found")
            events = con.execute("SELECT at, changed_by, old_status, new_status, comment FROM finding_events "
                                 "WHERE finding_id = ? ORDER BY id", (finding_id,)).fetchall()
        out = dict(row)
        out["history"] = [dict(e) for e in events]
        return out

    def update_finding(self, finding_id, changed_by, status=None, owner=None, comment=None):
        if status is not None and status not in STATUSES:
            raise BadInput(f"status must be one of {', '.join(STATUSES)}")
        if status == "false_positive" and not (comment or "").strip():
            raise BadInput("a false positive needs a comment that says why")
        current = self.get_finding(finding_id)
        new = {
            "status": status if status is not None else current["status"],
            "owner": owner if owner is not None else current["owner"],
            "comment": comment if comment is not None else current["comment"],
        }
        with self.connect() as con:
            con.execute("UPDATE findings SET status = ?, owner = ?, comment = ?, updated_at = ? WHERE id = ?",
                        (new["status"], new["owner"], new["comment"], now(), finding_id))
            con.execute("INSERT INTO finding_events (finding_id, at, changed_by, old_status, new_status, comment) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (finding_id, now(), changed_by, current["status"], new["status"], comment or ""))
        return self.get_finding(finding_id)

    def update_many(self, ids, changed_by, status=None, owner=None, comment=None):
        """Same rules as update_finding, for a selection from the table. All or nothing."""
        if status is not None and status not in STATUSES:
            raise BadInput(f"status must be one of {', '.join(STATUSES)}")
        if status == "false_positive" and not (comment or "").strip():
            raise BadInput("a false positive needs a comment that says why")
        ids = list(dict.fromkeys(ids))
        with self.connect() as con:
            marks = ",".join("?" * len(ids))
            rows = con.execute(f"SELECT id, status, owner, comment FROM findings WHERE id IN ({marks})", ids).fetchall()
            if len(rows) != len(ids):
                found = {r["id"] for r in rows}
                raise NotFound(f"findings not found: {', '.join(str(i) for i in ids if i not in found)}")
            at = now()
            for r in rows:
                new_status = status if status is not None else r["status"]
                con.execute("UPDATE findings SET status = ?, owner = ?, comment = ?, updated_at = ? WHERE id = ?",
                            (new_status, owner if owner is not None else r["owner"],
                             comment if comment is not None else r["comment"], at, r["id"]))
                con.execute("INSERT INTO finding_events (finding_id, at, changed_by, old_status, new_status, comment) "
                            "VALUES (?, ?, ?, ?, ?, ?)", (r["id"], at, changed_by, r["status"], new_status, comment or ""))
        return len(rows)

    def findings_frame(self, run_id):
        with self.connect() as con:
            return pd.read_sql_query(
                "SELECT rule, severity, object, key, field, message, fix, related, weight, "
                "status, owner, comment FROM findings WHERE run_id = ?", con, params=(run_id,))
