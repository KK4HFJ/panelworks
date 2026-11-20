"""
Data and Grid: VB's Data control and DBGrid, on SQLite, with no-code logging.

  Data   invisible. A SQLite file beside the form (DatabaseName, default <form>.db).
         LogFields lines like "level = barLevel.Value" say what a row holds;
         LogEvery = 60 logs a row every minute, f.datLog.Log() logs one now.
         Columns are created (and added later) automatically. RecordSource is
         the query a bound Grid shows; Query/Execute run your own SQL;
         ExportCSV writes a file Excel opens.
  Grid   a table. DataSource = "datLog" shows that Data control's RecordSource
         and refreshes after every Log. Or fill it from code with AddRow/Rows.
"""
import csv
import os
import re
import sqlite3
import time
import tkinter as tk
from tkinter import ttk

from .runtime import Control, VBObject, register_control

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_fields(lines):
    """['level = barLevel.Value', 'pump = shpPump.FillColor'] -> [(column, obj, prop)]"""
    out = []
    for line in lines or []:
        line = str(line).strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"LogFields line '{line}': write it as  column = Object.Property")
        col, src = (x.strip() for x in line.split("=", 1))
        if not _IDENT.match(col) or col.lower() in ("id", "time"):
            raise ValueError(f"LogFields: '{col}' can't be a column name (letters, digits, _; not id/time)")
        if src.count(".") < 1:
            raise ValueError(f"LogFields line '{line}': the right side must be Object.Property")
        obj, prop = src.split(".", 1)
        out.append((col, obj.strip(), prop.strip()))
    return out


def _as_number(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    if isinstance(v, bool):
        return int(v)
    try:
        f = float(str(v).strip())
        return int(f) if f.is_integer() and "." not in str(v) else f
    except (TypeError, ValueError):
        return v


@register_control
class Data(VBObject):
    """Invisible SQLite logger and query source."""
    TYPE = "Data"
    EVENTS = ("Logged", "Error")
    PERSIST_ORDER = ("DatabaseName", "Table", "LogFields", "LogEvery", "RecordSource")

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_db="", _table="log", _fields=[], _every=0, _source="", _conn=None,
                         _after=None, _rows=[], _cols=[], _last_error="").items():
            object.__setattr__(self, k, v)

    # ---- lifecycle -----------------------------------------------------------------
    def on_form_loaded(self):
        try:
            self._open()
        except Exception as e:
            self._error(f"opening {self.get_Path()}: {e}")
            return
        self._schedule()
        # fill bound grids after Form_Load, which may still be adding columns to a new database
        root = getattr(self._form, "root", None)
        if root is not None:
            root.after(0, self._notify_grids)
        else:
            self._notify_grids()

    def destroy(self):
        object.__setattr__(self, "_every", 0)
        self._schedule()
        if self._conn is not None:
            self._conn.close()
            object.__setattr__(self, "_conn", None)

    def _error(self, msg):
        object.__setattr__(self, "_last_error", msg)
        print(f"[data] {self.Name}: {msg}")
        self.fire("Error", msg)

    # ---- properties ------------------------------------------------------------------
    def get_DatabaseName(self): return self._db
    def set_DatabaseName(self, v): object.__setattr__(self, "_db", str(v).strip())

    def get_Path(self):
        """Full path of the database file."""
        name = self._db or f"{getattr(self._form, 'spec_name', 'panel')}.db"
        if os.path.isabs(name):
            return name
        from .util import data_dir
        return os.path.join(data_dir(getattr(self._form, "path", None)), name)

    def get_Table(self): return self._table
    def set_Table(self, v):
        v = str(v).strip()
        if not _IDENT.match(v):
            raise ValueError("Table: letters, digits and _ only")
        object.__setattr__(self, "_table", v)

    def get_LogFields(self): return list(self._fields)
    def set_LogFields(self, v):
        lines = [x for x in (v.splitlines() if isinstance(v, str) else v) if str(x).strip()]
        parse_fields(lines)                              # refuse mistakes now, not at the first log
        object.__setattr__(self, "_fields", [str(x).strip() for x in lines])

    def get_LogEvery(self): return self._every
    def set_LogEvery(self, v):
        object.__setattr__(self, "_every", max(0, float(v)))
        self._schedule()

    def get_RecordSource(self):
        return self._source or f"SELECT * FROM {self._table} ORDER BY id DESC LIMIT 100"
    def set_RecordSource(self, v): object.__setattr__(self, "_source", str(v).strip())

    def get_RecordCount(self):
        if self._conn is None:
            return 0
        try:
            return self._conn.execute(f"SELECT COUNT(*) FROM {self._table}").fetchone()[0]
        except sqlite3.Error:
            return 0

    def get_LastError(self): return self._last_error
    def get_Columns(self): return list(self._cols)

    # ---- the database ------------------------------------------------------------------
    def _open(self):
        if self._conn is None:
            path = self.get_Path()
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            conn = sqlite3.connect(path, isolation_level=None)       # autocommit
            object.__setattr__(self, "_conn", conn)
        self._ensure_table()

    def _ensure_table(self):
        c = self._conn
        c.execute(f"CREATE TABLE IF NOT EXISTS {self._table} "
                  "(id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT)")
        have = {r[1] for r in c.execute(f"PRAGMA table_info({self._table})")}
        for col, _, _ in parse_fields(self._fields):
            if col not in have:                                      # fields added later
                c.execute(f"ALTER TABLE {self._table} ADD COLUMN {col}")

    def _schedule(self):
        root = getattr(self._form, "root", None)
        if root is None:
            return
        if self._after:
            try:
                root.after_cancel(self._after)
            except tk.TclError:
                pass
            object.__setattr__(self, "_after", None)
        if self._every > 0 and self._conn is not None:
            object.__setattr__(self, "_after", root.after(int(self._every * 1000), self._tick))

    def _tick(self):
        object.__setattr__(self, "_after", None)
        self.m_Log()
        self._schedule()

    # ---- methods ------------------------------------------------------------------------
    def m_Log(self, values=None):
        """Log a row now: the LogFields' current values, or a dict you pass
        (f.datLog.Log({"weight": 1234, "ticket": "A17"}))."""
        try:
            self._open()
            row = {}
            if values is None:
                for col, obj, prop in parse_fields(self._fields):
                    row[col] = _as_number(self._form.obj(obj).get(prop))
            else:
                if not isinstance(values, dict):
                    raise ValueError("Log(values): pass a dict of column: value")
                for col in values:
                    if not _IDENT.match(str(col)) or str(col).lower() in ("id", "time"):
                        raise ValueError(f"'{col}' can't be a column name")
                have = {r[1] for r in self._conn.execute(f"PRAGMA table_info({self._table})")}
                for col in values:
                    if col not in have:
                        self._conn.execute(f"ALTER TABLE {self._table} ADD COLUMN {col}")
                row = {k: _as_number(v) for k, v in values.items()}
            row = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), **row}
            cols = ", ".join(row)
            marks = ", ".join("?" * len(row))
            cur = self._conn.execute(f"INSERT INTO {self._table} ({cols}) VALUES ({marks})", list(row.values()))
            row = {"id": cur.lastrowid, **row}
        except Exception as e:
            self._error(f"Log: {e}")
            return None
        self._notify_grids()
        self.fire("Logged", row)
        return row

    def m_AddColumns(self, *names):
        """AddColumns("plate", "gross", ...): make sure these columns exist in Table
        (they're added if missing; existing data is kept). Returns the ones added."""
        self._open()
        if len(names) == 1 and isinstance(names[0], (list, tuple)):
            names = names[0]
        have = {r[1] for r in self._conn.execute(f"PRAGMA table_info({self._table})")}
        added = []
        for n in names:
            n = str(n).strip()
            if not _IDENT.match(n):
                raise ValueError(f"'{n}' can't be a column name")
            if n not in have:
                self._conn.execute(f"ALTER TABLE {self._table} ADD COLUMN {n}")
                added.append(n)
        return added

    def m_Query(self, sql=None, params=None):
        """Run a SELECT and return the rows as a list of dicts (default: RecordSource)."""
        self._open()
        cur = self._conn.execute(sql or self.get_RecordSource(), list(params or []))
        cols = [d[0] for d in cur.description or []]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if sql is None:
            object.__setattr__(self, "_cols", cols)
            object.__setattr__(self, "_rows", rows)
        return rows

    def m_Execute(self, sql, params=None):
        """Run any SQL (UPDATE, DELETE, CREATE...). Returns the number of rows changed."""
        self._open()
        n = self._conn.execute(sql, list(params or [])).rowcount
        self._notify_grids()
        return n

    def m_Refresh(self):
        """Re-run RecordSource and update bound Grids."""
        self._notify_grids()

    def m_ExportCSV(self, path=None, sql=None):
        """Write the RecordSource (or sql) to a CSV file; returns its path."""
        self._open()
        path = path or os.path.splitext(self.get_Path())[0] + f"-{self._table}.csv"
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(self.get_Path()), path)
        cur = self._conn.execute(sql or self.get_RecordSource())
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:   # BOM: Excel reads UTF-8
            w = csv.writer(fh)
            w.writerow([d[0] for d in cur.description])
            w.writerows(cur.fetchall())
        return path

    def m_Clear(self):
        """Delete every row (asks nothing: use with care)."""
        return self.m_Execute(f"DELETE FROM {self._table}")

    def _notify_grids(self):
        objs = getattr(self._form, "objects", {})
        bound = [o for o in objs.values() if o.TYPE == "Grid" and o.get_DataSource() == self.Name]
        if not bound or self._conn is None:
            return
        try:
            rows = self.m_Query()
        except Exception as e:
            self._error(f"RecordSource: {e}")
            return
        for g in bound:
            g._show(self._cols, rows)


@register_control
class Grid(Control):
    """A table of rows. Bind it to a Data control (DataSource) or fill it in code."""
    TYPE = "Grid"
    EVENTS = ("Click", "DblClick")
    DEFAULT_SIZE = (320, 150)
    PERSIST_ORDER = ("DataSource", "Columns")

    def create(self, parent):
        object.__setattr__(self, "_source", "")
        object.__setattr__(self, "_cols", [])
        frame = tk.Frame(parent)
        tv = ttk.Treeview(frame, show="headings", selectmode="browse")
        sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tv.pack(side="left", fill="both", expand=True)
        tv.bind("<<TreeviewSelect>>", lambda e: self.fire("Click"))
        tv.bind("<Double-Button-1>", lambda e: self.fire("DblClick"))
        object.__setattr__(self, "tree", tv)
        return frame

    def _apply_font(self):
        super()._apply_font()
        try:
            ttk.Style(self.widget).configure("Treeview", font=self._tkfont)
        except tk.TclError:
            pass

    def get_Enabled(self): return True
    def set_Enabled(self, v): pass

    def get_DataSource(self): return self._source
    def set_DataSource(self, v): object.__setattr__(self, "_source", str(v).strip())

    def get_Columns(self): return list(self._cols)
    def set_Columns(self, cols):
        cols = [str(c) for c in (cols.splitlines() if isinstance(cols, str) else cols) if str(c).strip()]
        self._setup(cols)

    def _setup(self, cols):
        object.__setattr__(self, "_cols", list(cols))
        tv = self.tree
        tv.configure(columns=cols)
        width = max(40, (self._geom["width"] - 20) // max(1, len(cols)))
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=width, minwidth=30, stretch=True, anchor="w")

    def _show(self, cols, rows):
        if list(cols) != self._cols:
            self._setup(cols)
        tv = self.tree
        tv.delete(*tv.get_children())
        widths = [self._tkfont.measure(str(c)) + 18 for c in self._cols]
        for k, r in enumerate(rows):
            vals = [r.get(c, "") if isinstance(r, dict) else r[i] for i, c in enumerate(self._cols)]
            vals = ["" if v is None else v for v in vals]
            tv.insert("", "end", values=vals)
            if k < 200:                                       # size columns to their content
                widths = [max(w, self._tkfont.measure(str(v)) + 14) for w, v in zip(widths, vals)]
        for c, w in zip(self._cols, widths):
            tv.column(c, width=min(w, 320))

    def get_Rows(self):
        return [list(self.tree.item(i, "values")) for i in self.tree.get_children()]
    def set_Rows(self, rows):
        self._show(self._cols, [list(r) for r in rows])

    def get_RowCount(self): return len(self.tree.get_children())

    def get_Row(self):
        """Index of the selected row (0 = first), or -1."""
        sel = self.tree.selection()
        return self.tree.index(sel[0]) if sel else -1
    def set_Row(self, i):
        kids = self.tree.get_children()
        i = int(i)
        if 0 <= i < len(kids):
            self.tree.selection_set(kids[i])
            self.tree.see(kids[i])

    def get_Text(self):
        """The selected row's values joined with tabs, or empty."""
        sel = self.tree.selection()
        return "\t".join(map(str, self.tree.item(sel[0], "values"))) if sel else ""

    def m_AddRow(self, *values):
        """AddRow(v1, v2, ...): add a row at the end (or AddRow([v1, v2]))."""
        if len(values) == 1 and isinstance(values[0], (list, tuple)):
            values = values[0]
        self.tree.insert("", "end", values=list(values))

    def m_Clear(self):
        self.tree.delete(*self.tree.get_children())

    def m_Cell(self, row, column):
        """Cell(row, column): one value; column is a number or a column name."""
        kids = self.tree.get_children()
        vals = self.tree.item(kids[int(row)], "values")
        idx = self._cols.index(column) if isinstance(column, str) else int(column)
        return vals[idx]

    def m_Refresh(self):
        src = self._form.objects.get(self._source) if hasattr(self._form, "objects") else None
        if src is not None and src.TYPE == "Data":
            src.m_Refresh()
