#!/usr/bin/env python3
"""Persistent memory CLI. Markdown as the source of truth, SQLite as the index."""

import argparse
import contextlib
import datetime as dt
import difflib
import io
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / ".index" / "index.db"

NOTE_DIRS = ("ltm", "stm", "projects", "policies", "archive")
WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
MARKER = re.compile(r"\s+!(final|local)\b")
POLICY_FENCE = re.compile(r"```yaml\s+policy\n(.*?)```", re.S)
INDEX_BLOCK = re.compile(r"(<!-- mem:index:start -->)(.*?)(<!-- mem:index:end -->)", re.S)
GRAPH_BLOCK = re.compile(r"(<!-- mem:graph:start -->)(.*?)(<!-- mem:graph:end -->)", re.S)

NL = chr(10)
TODAY = dt.date.today()
DEFAULT_WORK_TTL = 10  # work days, unless a policy says otherwise


def cli():
    """How to invoke this CLI, for the messages that suggest it.

    There is no `mem` command: the script is invoked directly. The interpreter
    changes with the platform -- `python` on Windows, `python3` elsewhere --
    and the path is written home-relative, so a user name containing spaces
    never lands in the text.
    """
    exe = "python" if sys.platform == "win32" else "python3"
    script = ROOT / "bin" / "mem.py"
    try:
        return f"{exe} ~/{script.relative_to(Path.home()).as_posix()}"
    except ValueError:
        return f"{exe} {script.as_posix()}"


# --------------------------------------------------------------------------- yaml


def _scalar(raw):
    v = raw.strip()
    if v.startswith(("'", '"')) and v.endswith(("'", '"')) and len(v) > 1:
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", ""):
        return None
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def parse_yaml(text, flags=None, prefix=""):
    """YAML subset: nested maps, lists, scalars, !final / !local markers."""
    if flags is None:
        flags = {}
    rows = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rows.append((len(raw) - len(raw.lstrip()), raw.strip()))
    obj, _ = _parse_rows(rows, 0, rows[0][0] if rows else 0, prefix, flags)
    return obj, flags


def _parse_rows(rows, i, indent, prefix, flags):
    if i >= len(rows):
        return {}, i
    container = [] if rows[i][1].startswith("- ") else {}
    while i < len(rows):
        cur_indent, line = rows[i]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            i += 1
            continue

        if line.startswith("- "):
            if not isinstance(container, list):
                break
            container.append(_scalar(line[2:]))
            i += 1
            continue

        if ":" not in line:
            i += 1
            continue

        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        path = f"{prefix}{key}"

        marks = [m.group(1) for m in MARKER.finditer(rest)]
        if marks:
            rest = MARKER.sub("", rest).strip()
            flags[path] = set(marks)

        if rest:
            container[key] = _scalar(rest)
            i += 1
            continue

        nxt = i + 1
        if nxt < len(rows) and rows[nxt][0] > cur_indent:
            child, i = _parse_rows(rows, nxt, rows[nxt][0], f"{path}.", flags)
            container[key] = child
        else:
            container[key] = None
            i += 1
    return container, i


# -------------------------------------------------------------------------- notes


def parse_note(path):
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            meta, _ = parse_yaml(text[4:end])
            body = text[end + 4 :].lstrip("\n")
    title = ""
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    policy, pflags = {}, {}
    fence = POLICY_FENCE.search(body)
    if fence:
        policy, pflags = parse_yaml(fence.group(1))
    return {
        "path": path,
        "rel": path.relative_to(ROOT).as_posix(),
        "meta": meta or {},
        "body": body,
        "title": title,
        "links": sorted({m.group(1).strip() for m in WIKILINK.finditer(body)}),
        "policy": policy,
        "pflags": pflags,
    }


def scan():
    notes = []
    for d in NOTE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            notes.append(parse_note(p))
    for p in sorted(ROOT.glob("*.md")):
        if p.name not in ("README.md",):
            notes.append(parse_note(p))
    return notes


def note_date(note, key, default=None):
    v = note["meta"].get(key)
    if not v:
        return default
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        return default


# --------------------------------------------------------------------------- index

SCHEMA = """
CREATE TABLE notes (
    rel TEXT PRIMARY KEY, name TEXT, type TEXT, scope TEXT, title TEXT,
    created TEXT, last_used TEXT, uses INTEGER, confidence TEXT,
    pin INTEGER, ttl_work_days INTEGER, created_work_day INTEGER,
    confirmations INTEGER, bytes INTEGER
);
CREATE TABLE links (src TEXT, dst TEXT);
CREATE TABLE tags (rel TEXT, tag TEXT);
CREATE TABLE projects (
    slug TEXT PRIMARY KEY, fs_path TEXT, repo TEXT, parent TEXT,
    status TEXT, lang TEXT, rel TEXT
);
CREATE TABLE project_links (src TEXT, dst TEXT, kind TEXT);
CREATE TABLE project_aliases (slug TEXT, alias TEXT);
CREATE INDEX idx_links_src ON links(src);
CREATE INDEX idx_links_dst ON links(dst);
CREATE INDEX idx_notes_type ON notes(type);
"""

DROP_SCHEMA = "".join(
    f"DROP TABLE IF EXISTS {t};"
    for t in ("notes", "links", "tags", "projects", "project_links", "project_aliases")
)


def build_index(verbose=True):
    # Tables are recreated rather than deleting the file: on Windows an unlink
    # fails while another connection is open (cmd_graph and cmd_gc keep one
    # alive while they reindex).
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(DROP_SCHEMA)
    con.executescript(SCHEMA)
    notes = scan()
    for n in notes:
        m = n["meta"]
        con.execute(
            "INSERT OR REPLACE INTO notes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                n["rel"],
                m.get("name") or n["path"].stem,
                m.get("type", "note"),
                m.get("scope", "global"),
                n["title"],
                str(m.get("created", "")),
                str(m.get("last_used", m.get("created", ""))),
                int(m.get("uses") or 0),
                m.get("confidence", "medium"),
                1 if m.get("pin") else 0,
                int(m.get("ttl_work_days") or 0),
                -1 if m.get("created_work_day") is None else int(m["created_work_day"]),
                int(m.get("confirmations") or 0),
                len(n["body"].encode("utf-8")),
            ),
        )
        for dst in n["links"]:
            con.execute("INSERT INTO links VALUES (?,?)", (n["rel"], dst))
        for tag in m.get("tags") or []:
            con.execute("INSERT INTO tags VALUES (?,?)", (n["rel"], str(tag)))

        if n["path"].name == "project.md":
            slug = n["path"].parent.name
            con.execute(
                "INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?,?,?)",
                (
                    slug,
                    expand(str(m.get("fs_path") or "")),
                    str(m.get("repo") or ""),
                    str(m.get("parent") or ""),
                    str(m.get("status") or "active"),
                    str(m.get("lang") or ""),
                    n["rel"],
                ),
            )
            for a in m.get("aliases") or []:
                con.execute("INSERT INTO project_aliases VALUES (?,?)", (slug, str(a).lower()))
        if n["path"].name == "links.md":
            slug = n["path"].parent.name
            for kind, dst in parse_links(n["body"]):
                con.execute("INSERT INTO project_links VALUES (?,?,?)", (slug, dst, kind))
    con.commit()
    if verbose:
        c = con.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        p = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        print(f"index: {c} notes, {p} projects -> {DB.relative_to(ROOT)}")
    return con


def parse_links(body):
    """Lines shaped like: `- depends-on :: other-project`"""
    out = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("- ") and "::" in line:
            kind, _, dst = line[2:].partition("::")
            out.append((kind.strip(), dst.strip().strip("[]")))
    return out


def db():
    if not DB.exists():
        return build_index(verbose=False)
    return sqlite3.connect(DB)


def expand(p):
    if not p:
        return ""
    return str(Path(os.path.expandvars(os.path.expanduser(p))))


def contract(p):
    """Inverse of expand(): folds the home directory back to `~`.

    The index keeps paths expanded because they get compared against the cwd,
    but whatever lands in a versioned file must stay as it was declared:
    otherwise every machine that regenerates the graph carves its own home
    into it, and the file becomes that machine's instead of the repo's.
    """
    if not p:
        return ""
    try:
        return "~/" + Path(p).relative_to(Path.home()).as_posix()
    except ValueError:
        return p


def write(path, text):
    """Always writes LF. Python's text mode on Windows would silently convert
    to CRLF, and every `mem graph` would dirty the working tree."""
    path.write_text(text, encoding="utf-8", newline="\n")


# ------------------------------------------------------------------- work-day counter


def set_front_field(path, key, value):
    """Updates one frontmatter key and leaves everything else untouched.

    The frontmatter is not rebuilt from `meta`: a parser round-trip would lose
    ordering, quoting and every key it cannot represent. Only the line that
    matters is touched, or appended at the end when missing.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---", 4)
    if end == -1:
        return False
    head, tail = text[4:end], text[end:]
    line = f"{key}: {value}"
    pat = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    head = pat.sub(line, head, count=1) if pat.search(head) else head.rstrip("\n") + "\n" + line
    write(path, f"---\n{head}{tail}")
    return True


def slug_of_scope(scope):
    """Slug of the project a note belongs to, or None when global.

    Accepts both `project:acme` and `acme`: hand-written notes use either
    form, and the counter has to be found in both cases.
    """
    s = str(scope or "global").strip()
    if not s or s == "global":
        return None
    return s.split(":", 1)[1] if s.startswith("project:") else s


def counter_path(slug):
    """File carrying the counter for a slug: the project, or MEMORY.md."""
    return ROOT / "projects" / slug / "project.md" if slug else ROOT / "MEMORY.md"


def work_days_of(slug):
    """Current tick for a slug. None when the project is not registered --
    which differs from 0, a registered project never opened yet."""
    p = counter_path(slug)
    if not p.exists():
        return None
    return int(parse_note(p)["meta"].get("work_days") or 0)


def bump_work_days(path):
    """Marks a work day on `path`'s counter. Returns the new value, or None
    when the day had already been counted.

    The tick is per day, not per session: several chats opened on the same day
    do not advance it, so the working tree gets dirtied by at most one line per
    project per day.
    """
    if not path.exists():
        return None
    meta = parse_note(path)["meta"]
    if str(meta.get("last_work_day") or "") == str(TODAY):
        return None
    days = int(meta.get("work_days") or 0) + 1
    if not set_front_field(path, "work_days", days):
        raise RuntimeError(f"{path.name} has no frontmatter: counter not writable")
    set_front_field(path, "last_work_day", TODAY)
    check = parse_note(path)["meta"]
    if int(check.get("work_days") or 0) != days or str(check.get("last_work_day")) != str(TODAY):
        raise RuntimeError(f"write not confirmed when re-reading {path.name}")
    return days


# --------------------------------------------------------------------------- policy


def merge(base, over, flags_base, flags_over, prefix="", conflicts=None):
    if conflicts is None:
        conflicts = []
    out = dict(base)
    for k, v in over.items():
        if k.startswith("~"):
            out.pop(k[1:], None)
            continue
        path = f"{prefix}{k}"
        if "final" in flags_base.get(path, set()):
            conflicts.append(path)
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v, flags_base, flags_over, f"{path}.", conflicts)
        elif isinstance(v, list) and isinstance(out.get(k), list):
            out[k] = out[k] + [x for x in v if x not in out[k]]
        else:
            out[k] = v
        if "final" in flags_over.get(path, set()):
            flags_base.setdefault(path, set()).add("final")
    return out


def strip_local(data, flags, prefix=""):
    out = {}
    for k, v in data.items():
        path = f"{prefix}{k}"
        if "local" in flags.get(path, set()):
            continue
        out[k] = strip_local(v, flags, f"{path}.") if isinstance(v, dict) else v
    return out


def policy_chain(target):
    """Policy chain from global down to the most specific node holding `target`."""
    target = Path(expand(str(target))).resolve()
    chain = [ROOT / "policies" / "global.md"]
    con = db()
    rows = con.execute("SELECT slug, fs_path FROM projects WHERE fs_path != ''").fetchall()
    matches = []
    for slug, fs_path in rows:
        try:
            p = Path(fs_path).resolve()
        except OSError:
            continue
        if p == target or p in target.parents:
            matches.append((len(p.parts), slug, ROOT / "projects" / slug / "policy.md"))
    for _, _slug, ppath in sorted(matches):
        if ppath.exists():
            chain.append(ppath)
    return chain


def resolve_policy(target):
    chain = policy_chain(target)
    acc, flags, conflicts = {}, {}, []
    prev_flags = {}
    for path in chain:
        note = parse_note(path)
        if prev_flags:
            acc = strip_local(acc, prev_flags, "")
        acc = merge(acc, note["policy"], flags, note["pflags"], "", conflicts)
        for k, v in note["pflags"].items():
            flags.setdefault(k, set()).update(v)
        prev_flags = note["pflags"]
    return acc, chain, conflicts


def policy_for_slug(slug):
    """Effective policy for a project's notes.

    It goes through the project's `fs_path` because resolve_policy() reasons
    over filesystem paths, not slugs. For global notes `policies/global.md` is
    read directly: resolving on ROOT would drag in the memory repo's own
    policy, which has nothing to do with a globally scoped note.
    """
    if not slug:
        return parse_note(ROOT / "policies" / "global.md")["policy"]
    note = ROOT / "projects" / slug / "project.md"
    if note.exists():
        fs = parse_note(note)["meta"].get("fs_path")
        if fs:
            return resolve_policy(fs)[0]
    return parse_note(ROOT / "policies" / "global.md")["policy"]


def render_yaml(data, indent=0):
    lines = []
    pad = "  " * indent
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}:")
            lines.extend(render_yaml(v, indent + 1))
        elif isinstance(v, list):
            lines.append(f"{pad}{k}: [{', '.join(str(x) for x in v)}]")
        elif isinstance(v, bool):
            lines.append(f"{pad}{k}: {'true' if v else 'false'}")
        elif v is None:
            lines.append(f"{pad}{k}:")
        else:
            lines.append(f"{pad}{k}: {v}")
    return lines


# ----------------------------------------------------------------------- commands


def cmd_index(args):
    build_index()


def cmd_scope(args):
    target = args.path or os.getcwd()
    policy, chain, conflicts = resolve_policy(target)
    print(f"# scope: {Path(expand(target)).resolve()}\n")
    print("## chain")
    for i, c in enumerate(chain):
        print(f"{'  ' * i}{'└─ ' if i else ''}{c.relative_to(ROOT).as_posix()}")
    print("\n## effective policy\n```yaml")
    print("\n".join(render_yaml(policy)))
    print("```")
    if conflicts:
        print("\n## overrides blocked by !final")
        for c in sorted(set(conflicts)):
            print(f"- {c}")


def cmd_graph(args):
    con = build_index(verbose=False)
    projects = con.execute(
        "SELECT slug, fs_path, parent, status, repo FROM projects ORDER BY slug"
    ).fetchall()
    plinks = con.execute("SELECT src, dst, kind FROM project_links").fetchall()

    lines = ["```mermaid", "graph TD"]
    if not projects:
        lines.append('    empty["no registered project"]')
    for slug, fs_path, parent, status, _repo in projects:
        label = f'{slug}<br/><i>{contract(fs_path) or "?"}</i>'
        lines.append(f'    {ident(slug)}["{label}"]:::{status or "active"}')
    for slug, _fs, parent, _st, _r in projects:
        if parent:
            lines.append(f"    {ident(parent)} --> {ident(slug)}")
    for src, dst, kind in plinks:
        lines.append(f"    {ident(src)} -.->|{kind}| {ident(dst)}")
    lines += [
        "",
        "    classDef active fill:#1f4d3a,stroke:#4dbd8a,color:#fff",
        "    classDef paused fill:#4d431f,stroke:#bda84d,color:#fff",
        "    classDef archived fill:#3a3a3a,stroke:#888,color:#ccc",
        "```",
    ]
    graph = "\n".join(lines)

    table = ["| project | path | parent | status | repo |", "|---|---|---|---|---|"]
    for slug, fs_path, parent, status, repo in projects:
        table.append(f"| [[{slug}]] | `{contract(fs_path) or '-'}` | {parent or '-'} | {status} | {repo or '-'} |")
    if not projects:
        table.append("| _(empty)_ | - | - | - | - |")

    out = ROOT / "projects" / "_graph.md"
    content = (
        "---\nname: _graph\ntype: reference\nscope: global\n"
        f"created: 2026-08-29\nlast_used: {TODAY}\n---\n\n"
        "# Project graph\n\n"
        "Generated by `mem graph`. Do not edit by hand.\n\n"
        "<!-- mem:graph:start -->\n" + graph + "\n<!-- mem:graph:end -->\n\n"
        "## Registry\n\n" + "\n".join(table) + "\n\nSee also [[MEMORY]] · [[inheritance]]\n"
    )
    write(out, content)
    write_memory_index(build_index(verbose=False))
    print(f"graph: {len(projects)} projects, {len(plinks)} links -> projects/_graph.md")


def ident(s):
    return re.sub(r"[^0-9A-Za-z_]", "_", s)


def write_memory_index(con):
    path = ROOT / "MEMORY.md"
    if not path.exists():
        return
    groups = [
        ("Policies", "SELECT rel, name, title FROM notes WHERE type='policy' ORDER BY name"),
        ("User", "SELECT rel, name, title FROM notes WHERE type='user' ORDER BY name"),
        ("Feedback", "SELECT rel, name, title FROM notes WHERE type='feedback' ORDER BY name"),
        ("Decisions", "SELECT rel, name, title FROM notes WHERE type='decision' ORDER BY name"),
        ("References", "SELECT rel, name, title FROM notes WHERE type='reference' ORDER BY name"),
        ("Projects", "SELECT rel, name, title FROM notes WHERE type='project' ORDER BY name"),
    ]
    out = []
    for label, q in groups:
        rows = con.execute(q).fetchall()
        if not rows:
            continue
        out.append(f"\n### {label}\n")
        for rel, name, title in rows:
            out.append(f"- [{title or name}]({rel}) — `{name}`")
    stm = con.execute("SELECT COUNT(*) FROM notes WHERE rel LIKE 'stm/%'").fetchone()[0]
    out.append(f"\n_Active STM: {stm} notes · updated {TODAY}_\n")
    body = path.read_text(encoding="utf-8")
    body = INDEX_BLOCK.sub(lambda m: m.group(1) + "\n" + "\n".join(out) + "\n" + m.group(3), body)
    write(path, body)


def stm_expiry(note):
    """Expiry verdict for an STM note: (expired, reason).

    Two regimes. With `created_work_day` the note expires on its own project's
    counter **or** on the calendar cap, whichever comes first: the counter
    protects occasional projects, where two calendar weeks carry no new
    information; the cap stops a note from becoming immortal just because the
    project has been idle for a year.

    Without that field it falls back to the calendar alone: a legacy note must
    not survive forever merely for having been born before the counter.
    """
    meta = note["meta"]
    slug = slug_of_scope(meta.get("scope"))
    pol = policy_for_slug(slug).get("memory") or {}
    created = note_date(note, "created", TODAY)
    age = (TODAY - created).days
    cap = int(pol.get("stm_cap_days") or 180)

    if meta.get("created_work_day") is None:
        ttl = int(pol.get("stm_ttl_days") or 14)
        return age > ttl, f"calendar {age}/{ttl}d, note without counter"

    if age > cap:
        return True, f"calendar cap {age}/{cap}d"

    tick = work_days_of(slug)
    if tick is None:
        return False, f"project `{slug}` not registered, only the cap applies ({age}/{cap}d)"

    used = tick - int(meta.get("created_work_day") or 0)
    ttl_w = int(meta.get("ttl_work_days") or pol.get("stm_work_ttl") or DEFAULT_WORK_TTL)
    return used > ttl_w, f"work {used}/{ttl_w} days"


def cmd_gc(args):
    con = db()
    # STM thresholds are resolved per note inside stm_expiry(), against the
    # project the note belongs to. Only what is genuinely global stays here:
    # the LTM evict and the compression threshold.
    policy, _, _ = resolve_policy(ROOT)
    mem = policy.get("memory", {}) or {}
    evict_days = int(mem.get("evict_after_days", 180))
    apply = args.apply

    expired = []
    for n in scan():
        if not n["rel"].startswith("stm/") or n["meta"].get("pin"):
            continue
        dead, why = stm_expiry(n)
        n["why"] = why
        if dead:
            expired.append(n)

    evictable = []
    inbound = {r[0] for r in con.execute("SELECT dst FROM links")}
    for n in scan():
        if not n["rel"].startswith("ltm/") or n["meta"].get("pin"):
            continue
        last = note_date(n, "last_used") or note_date(n, "created", TODAY)
        name = n["meta"].get("name") or n["path"].stem
        if (TODAY - last).days > evict_days and int(n["meta"].get("uses") or 0) == 0 and name not in inbound:
            evictable.append(n)


    # What stays and points at what leaves. Archiving breaks those references,
    # and the LTM notes holding them survive the GC: the damage is permanent.
    # Saying it BEFORE applying is the only moment left to decide -- afterwards
    # only red lines remain in `doctor`, which nobody can explain any more.
    doomed = {n["meta"].get("name") or n["path"].stem for n in expired}
    going = {n["rel"] for n in expired}
    orphaning = sorted(
        (n["rel"], dst)
        for n in scan()
        if n["rel"] not in going
        for dst in n["links"]
        if dst in doomed
    )

    print(f"# gc {'(apply)' if apply else '(dry-run)'}\n")
    n_exp = len(expired)
    print(f"- sweep: {n_exp} expired STM {'note' if n_exp == 1 else 'notes'} (work counter, or calendar cap)")
    print("- compress: expired ones merge into archive/stm/<project>-YYYY-MM.md")
    print(f"- evict: {len(evictable)} LTM notes idle for >{evict_days}d, 0 references")
    if orphaning:
        print(f"- ⚠ {len(orphaning)} references from notes that STAY to notes that leave:")
        for src, dst in orphaning:
            print(f"    {src} -> [[{dst}]]")
        print("    after archiving these become broken links: repoint them at the digest, or `pin` the cited notes")


    if not apply:
        for n in expired[:10]:
            print(f"    sweep  {n['rel']}  — {n['why']}")
        for n in evictable[:10]:
            print(f"    evict  {n['rel']}")
        print("\nRun with --apply to apply. Nothing is deleted: only moved into archive/.")
        return

    moved = 0
    by_project = {}
    for n in expired:
        by_project.setdefault(Path(n["rel"]).parts[1], []).append(n)
    for slug, notes in by_project.items():
        dest = ROOT / "archive" / "stm" / f"{slug}-{TODAY:%Y-%m}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        chunks = [
            "---",
            f"name: {slug}-{TODAY:%Y-%m}-digest",
            "type: reference",
            f"scope: project:{slug}",
            f"created: {TODAY}",
            f"last_used: {TODAY}",
            # Inherits the tags of what it compacts: without them the digest is
            # born invisible to `search --tag`, and the archived material becomes
            # unreachable by exactly the route meant to find it again.
            "tags: [" + ", ".join(sorted({str(x) for n in notes for x in (n["meta"].get("tags") or [])})) + "]",
            "---",
            "",
            f"# STM digest · {slug} · {TODAY:%Y-%m}",
            "",
            f"Compaction of {len(notes)} expired notes. Originals live in git history.",
            "",
        ]
        if dest.exists():
            chunks = [dest.read_text(encoding="utf-8").rstrip(), ""]
        for n in sorted(notes, key=lambda x: x["rel"]):
            chunks.append(f"## {n['title'] or n['path'].stem}")
            chunks.append(f"_{n['meta'].get('created', '?')} · `{n['rel']}`_")
            chunks.append("")
            chunks.append(condense(n["body"]))
            chunks.append("")
        write(dest, "\n".join(chunks))
        for n in notes:
            n["path"].unlink()
            moved += 1

    for n in evictable:
        dest = ROOT / "archive" / "ltm" / n["path"].name
        dest.parent.mkdir(parents=True, exist_ok=True)
        write(dest, n["path"].read_text(encoding="utf-8"))
        n["path"].unlink()
        moved += 1

    for d in (ROOT / "stm").rglob("*"):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    build_index(verbose=False)
    print(f"\n{moved} notes archived. Index rebuilt.")


def condense(body):
    """Drops the title, neutralises the wikilinks and squeezes blanks.

    Wikilinks become plain text: archived notes point at archived notes, and
    reproducing them would leave the digest full of dead references -- `mem
    doctor` would report a broken link per citation, on every run, forever.
    The name stays readable; the promise that it is reachable does not.
    """
    body = WIKILINK.sub(lambda m: f"`{m.group(1).strip()}`", body)
    lines = [l for l in body.splitlines() if not l.startswith("# ")]
    out, blank = [], False
    for l in lines:
        if not l.strip():
            if blank:
                continue
            blank = True
        else:
            blank = False
        out.append(l.rstrip())
    return "\n".join(out).strip()


TEMPLATES = {
    "ltm": "---\nname: {name}\ntype: {type}\nscope: {scope}\ncreated: {today}\nlast_used: {today}\nuses: 0\nconfidence: high\npin: false\ntags: [{tags}]\n---\n\n# {title}\n\n\n\nSee also [[MEMORY]]\n",
    "stm": "---\nname: {name}\ntype: stm\nscope: {scope}\ncreated: {today}\ncreated_work_day: {tick}\nttl_work_days: {ttl}\nconfidence: low\npin: false\ntags: [{tags}]\n---\n\n# {title}\n\n\n",
    "project": "---\nname: {name}\ntype: project\nscope: project:{name}\nfs_path: \nrepo: \nparent: \nstatus: active\nlang: \ncreated: {today}\nlast_used: {today}\n---\n\n# {title}\n\n## Purpose\n\n## Status\n\n## Notes\n\nSee also [[_graph]] · [[MEMORY]]\n",
}


def cmd_new(args):
    kind = args.kind
    name = args.name
    # The vocabulary is enforced at creation, not only after the fact in
    # `doctor`: a wrong tag written here survives until someone runs doctor
    # again, and meanwhile the note is already unreachable by tag.
    tags = sorted({t.strip().lower() for t in (args.tag or []) if t.strip()})
    vocab = {str(v) for v in (policy_for_slug(slug_of_scope(args.scope)).get("memory") or {}).get("tags", [])}
    for t in tags:
        if vocab and t not in vocab:
            near = difflib.get_close_matches(t, sorted(vocab), n=1, cutoff=0.4)
            hint = f", nearest is `{near[0]}`" if near else ""
            sys.exit(f"tag `{t}` is outside the vocabulary in `global.md`{hint}.")
    tags = ", ".join(tags)
    title = args.title or name.replace("-", " ").capitalize()
    if kind == "project":
        d = ROOT / "projects" / name
        d.mkdir(parents=True, exist_ok=True)
        write(d / "project.md", TEMPLATES["project"].format(name=name, title=title, today=TODAY))
        write(
            d / "policy.md",
            f"---\nname: {name}-policy\ntype: policy\nscope: project:{name}\ncreated: {TODAY}\n---\n\n"
            f"# Policy · {title}\n\nLocal overrides. Inherits from [[global]].\n\n"
            "```yaml policy\n\n```\n",
        )
        write(
            d / "links.md",
            f"---\nname: {name}-links\ntype: reference\nscope: project:{name}\ncreated: {TODAY}\n---\n\n"
            f"# Links · {title}\n\n"
            "Format: `- <kind> :: <slug>` · kind: depends-on, shares-lib, forked-from, deploys-to, docs-for\n\n"
            "See also [[_graph]]\n",
        )
        print(f"created projects/{name}/ (project.md, policy.md, links.md)")
        return

    if kind == "stm":
        slug = slug_of_scope(args.scope)
        tick = work_days_of(slug)
        if tick is None:
            sys.exit(
                f"project `{slug}` is not registered: without a counter the note would never expire.\n"
                f"Register it with `{cli()} new project {slug}`, or use the global scope."
            )
        pol = policy_for_slug(slug).get("memory") or {}
        ttl = args.ttl or int(pol.get("stm_work_ttl") or DEFAULT_WORK_TTL)
        d = ROOT / "stm" / (slug or "global")
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{TODAY}-{name}.md"
        write(
            p,
            TEMPLATES["stm"].format(
                tags=tags,
                name=name,
                title=title,
                scope=f"project:{slug}" if slug else "global",
                today=TODAY,
                tick=tick,
                ttl=ttl,
            ),
        )
        print(f"expires after {ttl} work days on {slug or 'any project'} (current tick: {tick})")
    else:
        d = ROOT / "ltm" / kind
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{name}.md"
        write(
            p,
            TEMPLATES["ltm"].format(tags=tags, name=name, title=title, type=kind.rstrip("s"), scope=args.scope or "global", today=TODAY),
        )
    print(f"created {p.relative_to(ROOT).as_posix()}")


def cmd_promote(args):
    src = Path(args.file)
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        sys.exit(f"not found: {src}")
    n = parse_note(src)
    kind = args.type
    dest = ROOT / "ltm" / kind / f"{n['meta'].get('name', src.stem)}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(n["meta"])
    meta.update({"type": kind.rstrip("s"), "confidence": "high", "last_used": str(TODAY), "uses": 1})
    for k in ("ttl_days", "ttl_work_days", "created_work_day", "confirmations"):
        meta.pop(k, None)  # a promoted note no longer expires: counter fields are noise
    # Bools must be rewritten lowercase: `str(False)` would give `False`, which
    # our parser tolerates but which clashes with every other file in the repo.
    def fm(v):
        return "true" if v is True else "false" if v is False else v

    head = "\n".join(f"{k}: {fm(v)}" for k, v in meta.items() if v not in (None, ""))
    write(dest, f"---\n{head}\n---\n\n{n['body']}")
    src.unlink()
    print(f"promoted -> {dest.relative_to(ROOT).as_posix()}")


def cmd_confirm(args):
    """Records a confirmation on an STM note.

    A confirmation is a declared act, not an inference: the fact that `load`
    injects a note does not mean the fact still holds. The count can therefore
    only go through here, and without this command `promote_after` would stay a
    rule living only in the head of whoever is working.
    """
    src = Path(args.file)
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        sys.exit(f"not found: {src}")
    n = parse_note(src)
    got = int(n["meta"].get("confirmations") or 0) + 1
    if not set_front_field(src, "confirmations", got):
        sys.exit(f"{src.name} has no frontmatter: confirmation not recordable")
    set_front_field(src, "last_used", TODAY)
    pol = policy_for_slug(slug_of_scope(n["meta"].get("scope"))).get("memory") or {}
    threshold = int(pol.get("promote_after") or 2)
    rel = src.relative_to(ROOT).as_posix()
    print(f"{rel}: {got} confirmations out of {threshold}")
    if got >= threshold:
        print(f"threshold reached, promote with `{cli()} promote {rel} --type <type>`")


def hook_problems(settings=None):
    """Check the hook commands in ~/.claude/settings.json.

    Hooks run under bash and are non-blocking: a path with backslashes fails
    with exit 127 and **nobody reports it**, so the session starts with no live
    memory. It has happened twice, the second time caused by `setup.py` itself.
    Here the failure becomes loud. See ltm/feedback/windows-hook-quoting.md
    """
    out = []
    # The path is a parameter because a check you can only exercise by damaging
    # the real file is a check you cannot trust: `doctor --settings <copy>`
    # exercises it without touching anything.
    settings = Path(expand(settings)) if settings else Path.home() / ".claude" / "settings.json"
    if not settings.exists():
        return out
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except ValueError:
        # Say what was NOT inspected: without it, the absence of further findings
        # reads as a green light, and the backslash branch looks like it passed
        # when in fact it was never reached.
        return [
            f"hook: {settings.name} is not valid JSON: the hook commands were not "
            "checked, so the absence of further findings means nothing"
        ]
    for event, groups in (data.get("hooks") or {}).items():
        for g in groups or []:
            for h in g.get("hooks") or []:
                cmd = h.get("command", "")
                if "mem.py" not in cmd:
                    continue
                if "\\" in cmd:
                    out.append(
                        f"hook {event}: the command contains backslashes; under bash it "
                        f"becomes `command not found` (exit 127) and dies silently"
                    )
                if "~/" in cmd and '"~/' in cmd:
                    out.append(f"hook {event}: `~` inside quotes does not expand, use `$HOME`")
    return out


def load_size_problems(policy):
    """Measures the `mem load` output for every registered project.

    The hook that injects it has a cap: beyond it the output is **silently
    truncated**, and what falls off is the tail -- the long-term facts. No error,
    no signal: the session starts with less memory and nobody knows. It is the
    same check that already exists for AUTOLOAD.md against `autoload_budget_kb`,
    applied to the layer that actually overflows.

    It is measured per project because the size depends on the cwd: from a
    generic directory the output is a third of what it is inside a big project.
    """
    budget = int((policy.get("memory") or {}).get("load_budget_kb") or 0)
    if not budget:
        return []
    out, con = [], db()
    targets = [("global", None)] + [
        (s, f) for s, f in con.execute("SELECT slug, fs_path FROM projects WHERE fs_path != ''")
    ]
    for label, path in targets:
        if path and not Path(path).exists():
            continue
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                cmd_load(argparse.Namespace(path=path, no_tick=True))
        except Exception:
            continue
        s = buf.getvalue()
        # On Windows the hook emits CRLF: one byte more per line than len()
        # measures here. The cap applies to what actually goes out.
        size = len(s.encode("utf-8")) + (s.count("\n") if os.name == "nt" else 0)
        if size / 1024 > budget:
            out.append(
                f"load: from `{label}` the output is {size / 1024:.1f} KB, over the {budget} KB "
                f"cap -- it gets truncated at the tail, where the LTM facts are"
            )
    return out


def cmd_doctor(args):
    con = build_index(verbose=False)
    names = {r[0] for r in con.execute("SELECT name FROM notes")}
    names |= {Path(r[0]).stem for r in con.execute("SELECT rel FROM notes")}
    problems = []
    for src, dst in con.execute("SELECT src, dst FROM links"):
        if dst not in names:
            problems.append(f"broken link: {src} -> [[{dst}]]")
    for rel, name, ntype, created in con.execute("SELECT rel, name, type, created FROM notes"):
        if not created:
            problems.append(f"frontmatter: {rel} without `created`")
        if ntype == "note":
            problems.append(f"frontmatter: {rel} without `type`")
    slugs = {r[0] for r in con.execute("SELECT slug FROM projects")}
    for slug, fs_path, parent in con.execute("SELECT slug, fs_path, parent FROM projects"):
        if fs_path and not Path(fs_path).exists():
            problems.append(f"project {slug}: path does not exist {fs_path}")
        if not fs_path:
            problems.append(f"project {slug}: `fs_path` not set")
        if parent and parent not in slugs:
            problems.append(f"project {slug}: parent `{parent}` not registered")
    for (slug,) in con.execute(
        "SELECT slug FROM projects WHERE slug NOT IN (SELECT slug FROM project_aliases)"
    ):
        problems.append(f"project {slug}: no `aliases`, it will never be inferred from a prompt")
    for src, dst, kind in con.execute("SELECT src, dst, kind FROM project_links"):
        if dst not in slugs:
            problems.append(f"link {src} -{kind}-> {dst}: target project not registered")
    # The counter is the only thing keeping an STM note alive: when it does not
    # add up, the note does not expire the way it thinks it does, and nobody
    # notices on their own.
    for rel, scope, born, conf in con.execute(
        "SELECT rel, scope, created_work_day, confirmations FROM notes WHERE rel LIKE 'stm/%'"
    ):
        slug = slug_of_scope(scope)
        pol = policy_for_slug(slug).get("memory") or {}
        if conf >= int(pol.get("promote_after") or 2):
            problems.append(f"STM {rel}: {conf} confirmations, promote it to LTM with `{cli()} promote`")
        if born < 0:
            problems.append(f"STM {rel}: without `created_work_day`, expires on the calendar instead of on work")
            continue
        tick = work_days_of(slug)
        if tick is None:
            problems.append(f"STM {rel}: project `{slug}` not registered, only the calendar cap applies")
        elif born > tick:
            problems.append(
                f"STM {rel}: `created_work_day` {born} is past the project counter ({tick}), "
                "counter reset, or note arrived from another machine"
            )

    policy, _, conflicts = resolve_policy(ROOT)
    for c in set(conflicts):
        problems.append(f"policy: override blocked by !final on `{c}`")

    # Closed vocabulary: without this check the list in `global.md` would be a
    # convention to remember, and the vocabulary would grow back. Suggesting the
    # nearest tag is what separates "I typo'd it" from "I really need a new one".
    vocab = {str(v) for v in ((policy.get("memory") or {}).get("tags") or [])}
    if vocab:
        for (tag,) in con.execute("SELECT DISTINCT tag FROM tags ORDER BY tag"):
            if tag in vocab:
                continue
            near = difflib.get_close_matches(tag, sorted(vocab), n=1, cutoff=0.4)
            hint = f", nearest is `{near[0]}`" if near else ""
            problems.append(f"tag `{tag}` is outside the vocabulary in `global.md`{hint}")

    problems.extend(hook_problems(args.settings))
    problems.extend(load_size_problems(policy))

    def kb(name):
        p = ROOT / name
        return p.stat().st_size / 1024 if p.exists() else 0.0

    # Only AUTOLOAD.md lands in every session's context: MEMORY.md is the wiki
    # index, read on demand. Summing the two overestimated the budget.
    budget = int((policy.get("memory") or {}).get("autoload_budget_kb") or 8)
    autoload = kb("AUTOLOAD.md")
    if autoload > budget:
        problems.append(f"autoload: AUTOLOAD.md is {autoload:.1f} KB, over the {budget} KB budget")

    print(f"# doctor\n\n- autoload: {autoload:.1f} KB / {budget} KB (AUTOLOAD.md)")
    print(f"- index: {kb('MEMORY.md'):.1f} KB (MEMORY.md, not injected)")
    tag_total = con.execute("SELECT COUNT(DISTINCT tag) FROM tags").fetchone()[0]
    tag_once = con.execute(
        "SELECT COUNT(*) FROM (SELECT tag FROM tags GROUP BY tag HAVING COUNT(*) = 1)"
    ).fetchone()[0]
    no_tag = sum(
        1
        for rel, ntype in con.execute("SELECT rel, type FROM notes WHERE rel NOT IN (SELECT rel FROM tags)")
        if not is_scaffold(rel, ntype)
    )
    print(f"- tags: {tag_total} distinct, {tag_once} used once, {no_tag} notes untagged")
    print(f"- problems: {len(problems)}\n")
    for p in sorted(problems):
        print(f"  - {p}")
    if not problems:
        print("  no problems")


def clip_body(body, slug):
    """Clips the project body to the budget, stating where the rest is.

    The hook injecting `load` has a cap beyond which it **truncates silently**,
    and what falls off is the tail: the long-term facts. Better to cut here,
    where we know what is being dropped and can say where to find it, than to
    let the transport cut at an arbitrary byte.
    """
    policy = parse_note(ROOT / "policies" / "global.md")["policy"]
    budget = int((policy.get("memory") or {}).get("load_budget_kb") or 0)
    if not budget:
        return body
    cap = budget * 1024 // 2
    if len(body.encode("utf-8")) <= cap:
        return body
    kept, size = [], 0
    for line in body.splitlines():
        size += len(line.encode("utf-8")) + 1
        if size > cap:
            break
        kept.append(line)
    tail = "_…clipped to budget · the rest in `projects/" + slug + "/project.md`_"
    return NL.join(kept).rstrip() + NL + NL + tail


def cmd_load(args):
    """Context to inject at session start. Markdown on stdout."""
    target = args.path or os.getcwd()
    con = db()
    policy, chain, _ = resolve_policy(target)
    tpath = Path(expand(target)).resolve()

    print("# Persistent memory\n")
    print(f"Scope: `{tpath}` · repo `{contract(str(ROOT))}`\n")

    print("## Effective policy\n\n```yaml")
    print("\n".join(render_yaml(policy)))
    print("```\n")

    active = None
    for slug, fs_path in con.execute("SELECT slug, fs_path FROM projects WHERE fs_path != ''"):
        p = Path(fs_path)
        if p == tpath or p in tpath.parents:
            if active is None or len(Path(active[1]).parts) < len(p.parts):
                active = (slug, fs_path)

    targets = [("global", ROOT / "MEMORY.md")]
    if active:
        targets.append((active[0], ROOT / "projects" / active[0] / "project.md"))
    ticks = []
    for label, tp in (() if args.no_tick else targets):
        try:
            n = bump_work_days(tp)
            if n is not None:
                ticks.append(f"{label} → {n}")
        except Exception as e:
            # The SessionStart hook must not die over the counter: the error is
            # printed here, where it lands in the session context and stays visible.
            print(f"> ⚠ work-day counter: {e}\n")
    if ticks:
        print(f"_First access today · work days: {' · '.join(ticks)}_\n")

    if active:
        slug = active[0]
        print(f"## Active project: {slug}\n")
        note = ROOT / "projects" / slug / "project.md"
        if note.exists():
            print(clip_body(parse_note(note)["body"].strip(), slug) + "\n")
        rel = con.execute(
            "SELECT dst, kind FROM project_links WHERE src=? UNION SELECT src, kind FROM project_links WHERE dst=?",
            (slug, slug),
        ).fetchall()
        if rel:
            print("### Related\n")
            for dst, kind in rel:
                print(f"- `{kind}` → {dst}")
            print()
        stm_dir = ROOT / "stm" / slug
        if stm_dir.exists():
            files = sorted(stm_dir.glob("*.md"), reverse=True)[:5]
            if files:
                print("### Short-term memory\n")
                for f in files:
                    n = parse_note(f)
                    print(f"- **{n['title'] or f.stem}** ({n['meta'].get('created', '?')}) — `{f.relative_to(ROOT).as_posix()}`")
                print()
    else:
        print("## Active project\n\nNo project registered for this path. Register it with:\n")
        print(f"```bash\n{cli()} new project <slug>\n```\n")

    facts = con.execute(
        "SELECT rel, title, name FROM notes WHERE type IN ('user','feedback','decision') ORDER BY pin DESC, last_used DESC LIMIT 20"
    ).fetchall()
    if facts:
        print("## Long-term facts\n")
        for rel, title, name in facts:
            print(f"- [{title or name}]({rel})")
        print()

    print("---\n")
    # Deliberately minimal footer: this output has a cap, and every byte spent
    # here is a byte taken from the facts. The command list lives in MEMORY.md.
    print(f"_Commands: `{cli()} --help`_")


# --------------------------------------------------------------------------- search


def tag_rows(con):
    """Tag vocabulary: [(tag, n_notes)], most frequent first."""
    return list(con.execute("SELECT tag, COUNT(*) FROM tags GROUP BY tag ORDER BY COUNT(*) DESC, tag"))


def note_tags(con):
    """Map rel -> list of tags, to avoid querying the DB note by note."""
    out = {}
    for rel, tag in con.execute("SELECT rel, tag FROM tags"):
        out.setdefault(rel, []).append(tag)
    for tags in out.values():
        tags.sort()
    return out


# Generated files: their body mirrors the index, so it contains every title and
# matches any search. Looking inside them yields nothing but false positives.
GENERATED = ("MEMORY.md", "projects/_graph.md")

# Scaffolding is not tagged: `policy.md`, `project.md`, `links.md` and the
# generated files exist once per project and group nothing. Counting them among
# the untagged notes cried wolf: 29 reported where only 9 were real.
SCAFFOLD_RELS = ("AUTOLOAD.md", "MEMORY.md", "projects/_graph.md")
SCAFFOLD_NAMES = ("policy.md", "project.md", "links.md")


def is_scaffold(rel, ntype=""):
    return (
        rel in SCAFFOLD_RELS
        or rel.rsplit("/", 1)[-1] in SCAFFOLD_NAMES
        or ntype in ("policy", "project")
    )


def body_hit(path, needle):
    """First body line containing `needle`, as (number, text). None when absent.

    The body is read from the Markdown, not from the index: the DB stays an
    index of metadata, and duplicating the text inside it would make it a
    second source to keep in sync -- exactly what memory-architecture rules out.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for i, line in enumerate(text.splitlines(), 1):
        if needle in line.lower():
            return i, line.strip()
    return None


def cmd_search(args):
    con = db()
    q = (args.query or "").strip().lower()
    want = {t.strip().lower() for t in (args.tag or [])}
    if not q and not want and not args.type and not args.scope:
        sys.exit("a search term is required, or at least one filter: --tag, --type, --scope.")

    tags_of = note_tags(con)
    hits = []
    for rel, name, ntype, scope, title in con.execute(
        "SELECT rel, name, type, scope, title FROM notes"
    ).fetchall():
        tags = [t.lower() for t in tags_of.get(rel, [])]
        if want and not want.issubset(set(tags)):
            continue
        if args.type and ntype != args.type:
            continue
        if args.scope and args.scope not in str(scope or ""):
            continue

        kind, detail, score = "tag", "", 100
        if q:
            if q in tags:
                kind, score = "tag", 100
            elif q in (name or "").lower():
                kind, score = "name", 60
            elif q in (title or "").lower():
                kind, score = "title", 50
            elif any(q in t for t in tags):
                kind, score = "tag~", 40
            elif not args.meta and rel not in GENERATED and (hit := body_hit(ROOT / rel, q)):
                kind, score = "body", 20
                detail = f"l.{hit[0]}  {hit[1][:96]}"
            else:
                continue

        hits.append((-score, rel, kind, title or name, tags_of.get(rel, []), detail))

    hits.sort()
    hits = hits[: args.limit]
    label = q or " + ".join(sorted(want)) or " ".join(
        f"{k}={v}" for k, v in (("type", args.type), ("scope", args.scope)) if v
    )
    print("# search: {label} · {n} notes".format(label=label, n=len(hits)) + "\n")
    if not hits:
        print("  no match.")
        print("  browse the tag vocabulary with `{cli} tags`.".format(cli=cli()))
        return
    for _s, rel, kind, title, tags, detail in hits:
        print(f"  [{kind:6}] {rel}")
        print(f"           {title}" + (f"   · {', '.join(tags)}" if tags else ""))
        if detail:
            print(f"           {detail}")
    print()


def cmd_tags(args):
    con = db()
    rows = tag_rows(con)
    needle = (args.filter or "").strip().lower()
    shown = [(t, n) for t, n in rows if needle in t.lower()] if needle else rows
    notes = con.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    untagged = sum(
        1
        for rel, ntype in con.execute("SELECT rel, type FROM notes WHERE rel NOT IN (SELECT rel FROM tags)")
        if not is_scaffold(rel, ntype)
    )
    singles = sum(1 for _t, n in rows if n == 1)

    if needle:
        print("# tags: {shown} of {tot}".format(shown=len(shown), tot=len(rows)) + "\n")
    else:
        print("# tags: {tot} distinct across {notes} notes".format(tot=len(rows), notes=notes) + "\n")
    for t, n in shown:
        print(f"  {n:3}  {t}")
    if not shown:
        print("  no tag matches.")
    print("\n" + "_{singles} used only once · {untagged} notes with no tag_".format(singles=singles, untagged=untagged))


# ------------------------------------------------------------------ active project

# The state lives in the index, which is git-ignored: which project is active in
# a session is a fact about the machine and the moment, not about the memory. It
# can be lost without consequence, and it is per session because two chats open
# at once work on different projects.
ACTIVE = DB.parent / "active.json"
WORD = "[0-9a-z]"


# Possible names for the field carrying the prompt text in the UserPromptSubmit
# payload. Several variants are accepted because the contract does not guarantee
# it, and a single wrong name makes the hook inert without any error.
# Verified 2026-09-14: the real field is `prompt`. The official docs said
# `user_prompt`, and following them left the hook silent.
PROMPT_KEYS = ("prompt", "user_prompt", "userPrompt", "text", "message")


def read_active():
    try:
        return json.loads(ACTIVE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_active(state):
    ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE.write_text(json.dumps(dict(list(state.items())[-20:]), ensure_ascii=False), encoding="utf-8")


def match_project(con, text):
    """{slug: [aliases that matched]} for aliases present in the text.

    The word boundary is not decoration: a slug can be an ordinary word, and
    without it a passing mention would activate the wrong project. What is
    checked is that the alias is not embedded inside another word.
    """
    low = (text or "").lower()
    hits = {}
    for slug, alias in con.execute("SELECT slug, alias FROM project_aliases"):
        if re.search(f"(?<!{WORD}){re.escape(alias)}(?!{WORD})", low):
            hits.setdefault(slug, []).append(alias)
    return hits


def flatten(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, f"{key}."))
        else:
            out[key] = v
    return out


def project_context(con, slug, why=None):
    """Compact block to inject. Deliberately small: this runs on every project
    change, not once per session the way AUTOLOAD does."""
    note = ROOT / "projects" / slug / "project.md"
    meta = parse_note(note)["meta"] if note.exists() else {}
    head = f"## Memory · project `{slug}`"
    # Saying what triggered the inference makes a false positive recognisable at
    # a glance instead of mysterious: a slug that is also an ordinary word will
    # eventually activate the wrong project.
    if why:
        head += f"  ·  _inferred from: {', '.join(why)}_"
    out = [head, ""]

    fs = contract(expand(str(meta.get("fs_path") or "")))
    bits = [x for x in (fs, str(meta.get("status") or ""), str(meta.get("lang") or "")) if x]
    if bits:
        out.append(" · ".join(bits) + "\n")

    if fs:
        eff = flatten(resolve_policy(meta.get("fs_path"))[0])
        base = flatten(parse_note(ROOT / "policies" / "global.md")["policy"])
        delta = {k: v for k, v in eff.items() if base.get(k) != v}
        if delta:
            out.append("**Policy differing from global:**\n")
            out += [f"- `{k}: {v}`" for k, v in sorted(delta.items())]
            out.append("")

    rel = con.execute(
        "SELECT dst, kind FROM project_links WHERE src=? UNION SELECT src, kind FROM project_links WHERE dst=?",
        (slug, slug),
    ).fetchall()
    if rel:
        out.append("**Related:** " + " · ".join(f"`{k}` → {d}" for d, k in rel) + "\n")

    stm_dir = ROOT / "stm" / slug
    files = sorted(stm_dir.glob("*.md"), reverse=True)[:3] if stm_dir.exists() else []
    if files:
        out.append("**Recent working notes:**\n")
        for f in files:
            n = parse_note(f)
            out.append(f"- **{n['title'] or f.stem}** — `{f.relative_to(ROOT).as_posix()}`")
        out.append("")

    out.append(f"_The rest is searchable: `{cli()} search --scope project:{slug}`_")
    return "\n".join(out)


def _print_ctx(con, slug, why, changed, quiet):
    if changed or not quiet:
        print(project_context(con, slug, why))
    return changed


def activate(con, slug, session, quiet=False, why=None, no_tick=False):
    """Mark the active project, bump the counter, print the context.

    The tick lives here and not only in `load` because otherwise a project worked
    on from a generic directory never increments `work_days`, and its STM notes
    stop expiring on work: only the calendar cap is left, which is exactly the
    mechanism stm-work-counter set out to override.
    
    With `no_tick` it writes nothing -- neither counter nor session state.
    Read-only tasks need this: without it, inspecting the memory modifies it, and
    a "look but do not touch" analysis becomes impossible to carry out.
    """
    state = read_active()
    changed = state.get(session) != slug
    if no_tick:
        return _print_ctx(con, slug, why, changed, quiet)
    state[session] = slug
    write_active(state)
    try:
        bump_work_days(ROOT / "projects" / slug / "project.md")
    except Exception as e:
        print(f"> ⚠ work-day counter: {e}\n")
    if changed or not quiet:
        print(project_context(con, slug, why))
    return changed


def cmd_project(args):
    con = db()
    session = "cli"
    text = args.text or ""

    if args.from_hook:
        raw = sys.stdin.read() or ""
        # The last payload is kept on disk, under .index/ which is git-ignored:
        # the name of the field carrying the prompt text is not guaranteed by the
        # contract, and without this an upstream change silences the hook without
        # a trace -- which has already cost half a day. See
        # ltm/feedback/windows-hook-quoting.md
        try:
            DB.parent.mkdir(parents=True, exist_ok=True)
            (DB.parent / "last-hook.json").write_text(raw[:4000], encoding="utf-8")
        except OSError:
            pass
        try:
            payload = json.loads(raw or "{}")
        except ValueError:
            return  # a hook must never make noise on malformed input
        text = next((str(payload[k]) for k in PROMPT_KEYS if payload.get(k)), "")
        session = str(payload.get("session_id") or payload.get("sessionId") or "cli")
        if not text:
            return  # no text: stay silent, do not print the active-project status

    if args.slug:
        known = {r[0] for r in con.execute("SELECT slug FROM projects")}
        if args.slug not in known:
            sys.exit(f"project `{args.slug}` is not registered. Known: {', '.join(sorted(known))}")
        activate(con, args.slug, session, no_tick=args.no_tick)
        return

    if not text:
        cur = read_active().get(session)
        print(f"active project: {cur}" if cur else "no active project in this session")
        return

    hits = match_project(con, text)
    if not hits:
        return  # silence: this runs on every prompt, it cannot make noise
    if len(hits) > 1:
        # No guessing: two projects named together is a real case (a comparison,
        # a migration), and picking the likelier one would hand the reader the
        # wrong context without telling them.
        names = ", ".join(f"`{s}` ({', '.join(a)})" for s, a in sorted(hits.items()))
        print(f"> Several projects named: {names}. No context injected — "
              f"`{cli()} project <slug>` to pick one.")
        return
    slug = next(iter(hits))
    activate(con, slug, session, quiet=args.from_hook, why=hits[slug], no_tick=args.no_tick)


def main():
    # On Windows stdout is cp1252 unless the terminal is UTF-8: without this,
    # any box-drawing char or accent blows the command up instead of printing.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    ap = argparse.ArgumentParser(prog="mem", description="Claude Code persistent memory")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("index", help="rebuild the SQLite index from Markdown").set_defaults(fn=cmd_index)
    sub.add_parser("graph", help="regenerate the Mermaid diagrams and the MEMORY.md index").set_defaults(fn=cmd_graph)
    p = sub.add_parser("doctor", help="check links, frontmatter and policies")
    p.add_argument("--settings", help="alternative settings.json, to exercise the hook check")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("search", help="search notes by tag, name, title and body")
    p.add_argument("query", nargs="?")
    p.add_argument("--tag", action="append", help="filter by exact tag, repeatable (AND)")
    p.add_argument("--type", help="filter by note type")
    p.add_argument("--scope", help="filter by scope, partial match")
    p.add_argument("--meta", action="store_true", help="do not search note bodies")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("project", help="active project, inferred from the prompt or forced")
    p.add_argument("slug", nargs="?", help="force this project")
    p.add_argument("--text", help="infer from this text instead of stdin")
    p.add_argument("--no-tick", action="store_true", help="write nothing: no counters, no session state")
    p.add_argument("--from-hook", action="store_true", help="read the UserPromptSubmit JSON from stdin")
    p.set_defaults(fn=cmd_project)

    p = sub.add_parser("tags", help="tag vocabulary, with counts")
    p.add_argument("filter", nargs="?", help="show only tags containing this text")
    p.set_defaults(fn=cmd_tags)

    p = sub.add_parser("scope", help="effective policy for a path")
    p.add_argument("path", nargs="?")
    p.set_defaults(fn=cmd_scope)

    p = sub.add_parser("load", help="print the session context")
    p.add_argument("path", nargs="?")
    p.add_argument("--no-tick", action="store_true", help="write nothing: no counters, no session state")
    p.set_defaults(fn=cmd_load)

    p = sub.add_parser("gc", help="garbage collector: sweep, compress, evict")
    p.add_argument("--apply", action="store_true", help="apply instead of simulating")
    p.set_defaults(fn=cmd_gc)

    p = sub.add_parser("new", help="create a note from a template")
    p.add_argument("kind", choices=["user", "feedback", "decisions", "reference", "stm", "project"])
    p.add_argument("name")
    p.add_argument("--title")
    p.add_argument("--scope")
    p.add_argument("--tag", action="append", help="tag to assign, repeatable; must be in the vocabulary")
    p.add_argument("--ttl", type=int, help="STM: expiry in work days on the project")
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("confirm", help="record a confirmation on an STM note")
    p.add_argument("file")
    p.set_defaults(fn=cmd_confirm)

    p = sub.add_parser("promote", help="promote an STM note to long-term memory")
    p.add_argument("file")
    p.add_argument("--type", default="decisions", choices=["user", "feedback", "decisions", "reference"])
    p.set_defaults(fn=cmd_promote)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
