"""Check a review's data file and render the GitHub review with the jinja2 template.

Library for `review.py render`. render() reads reviews/<repo>/<N>/review.toml and writes
reviews/<repo>/<N>/github_review.md, which `review.py post` posts. The template is
reviews/review_template.md.

Checks; any failure stops the render:
  - no skeleton placeholder (<<...>>) from `review.py init` is left in review.toml
  - schema: required fields, no unknown keys, allowed values for type, result, severity
    and kind
  - a claim's result rates the author's evidence (code anyone can download and run); a
    claim that is not Confirmed, and a description that does not match the code, carry a
    request to the author
  - every quote (fact_checks.source, issues.quote) appears word for word in its source:
      pr_description  the PR body
      comment         the comment its url points to: #issuecomment-<id>, #pullrequestreview-<id>,
                      #discussion_r<id>, or with no fragment the issue/PR body
      code            lines start..end of path at ref (default: the reviewed commit)
      commit          the commit message of sha
    Whitespace differences are ignored, and "[...]" in a quote marks an elision.
  - issue locations exist at the reviewed commit, and inline anchors are lines in the PR diff
  - our code: gist/ is in use once it holds a file besides README.md. Then it must be
    safe to share (flat, UTF-8, under 1 MB per file, no local paths, e-mail addresses
    or credentials, a README.md that mentions every file and has no placeholders left),
    every our_code file of a [[checks]] entry must be in it, and once `review.py share --create` has uploaded
    it, the pinned revision in [gist].url must hold exactly the files in gist/. Before
    the upload the review links the placeholder GIST_NOT_UPLOADED_YET, which
    `review.py post` refuses to post.
  - the posted text contains no local file paths
  - the rendered review parses back, through post_review.py, into the same inline comments
  - the directory is reviews/<repo>/<N> for the PR in the data file
  - the "Reviewed commit:" line in overall_review.md, if present, is the commit in the data

The plain style (the plain-style skill's scripts): github_review.md is reflowed to one sentence
per line as it is rendered, and overall_review.md and gist/README.md are reflowed in place. Then
the plain-style checker runs on all three, ignoring quoted text. Any checker error stops the render,
except non-ASCII characters inside a > quote or a double-quoted phrase from the PR. Checker
warnings are printed for a reread.

Warnings (the render still happens): the PR is not open, its head moved past the commit,
or overall_review.md still has skeleton placeholders.
"""

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import jinja2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import post_review  # noqa: E402

# The rendered review is written one sentence per line with the plain-style skill's reflow.
PLAIN_STYLE_SCRIPTS = Path.home() / ".claude" / "skills" / "plain-style" / "scripts"

SEVERITIES = ("must_fix", "suggestion", "nit")
RESULTS = {"claim": ("Confirmed", "Partly Confirmed", "Not Verified"),
           "description": ("Matches", "Partly matches", "Does not match")}
KINDS = ("pr_description", "comment", "code", "commit")
ELISION = "[...]"
LOCAL_PATH_RE = re.compile(r"(?<![\w.:/])(/home/|/mnt/|/tmp/|/Users/|~/)")
PR_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)$")
GIST_URL_RE = re.compile(r"^https://gist\.github\.com/([^/]+)/([0-9a-f]+)/([0-9a-f]{40})$")
SECRET_RE = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                       r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-[A-Za-z0-9-]+)")
# Limited to common top-level domains so that matrix products like m@m.transpose() pass.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\."
                      r"(?:com|org|net|edu|gov|io|dev|ai|co|info|me|us|uk|de|cz|fr|ch|nl|se|"
                      r"fi|no|dk|at|it|es|ca|au|jp|cn|ru|in)\b")
MAX_GIST_FILE_BYTES = 1_000_000
# What `review.py init` leaves in the skeleton files for the agent to replace.
PLACEHOLDER_RE = re.compile(r"<<[A-Za-z][^<>\n]*>>")
GH_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/(?:pull|issues)/(\d+)(?:#(.*))?$")
LANGS = {".hpp": "cpp", ".cpp": "cpp", ".h": "cpp", ".py": "python", ".stan": "stan", ".R": "r"}


class Errors(list):
    def add(self, where, msg):
        self.append(f"{where}: {msg}")


def gh_api(path, accept=None):
    args = ["gh", "api", path]
    if accept:
        args += ["-H", f"Accept: {accept}"]
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0:
        return None, res.stderr.strip() or f"gh api {path} failed"
    return res.stdout, None


def text(d, key, where, errors, required=True):
    val = d.get(key)
    if val is None:
        if required:
            errors.add(where, f"missing '{key}'")
        return ""
    if not isinstance(val, str):
        errors.add(where, f"'{key}' must be a string")
        return ""
    if required and not val.strip():
        errors.add(where, f"'{key}' is empty")
    return val.strip()


def integer(d, key, where, errors, default=None):
    val = d.get(key, default)
    if not isinstance(val, int) or isinstance(val, bool) or val < 1:
        errors.add(where, f"'{key}' must be a positive integer")
        return 1
    return val


def no_unknown(d, allowed, where, errors):
    if not isinstance(d, dict):
        errors.add(where, "expected a table")
        return False
    for k in d:
        if k not in allowed:
            errors.add(where, f"unknown key '{k}' (allowed: {', '.join(allowed)})")
    return True


def table_list(data, key, errors, required):
    val = data.get(key, [])
    if not isinstance(val, list):
        errors.add(key, "must be an array of tables ([[...]])")
        return []
    if required and not val:
        errors.add(key, "needs at least one entry")
    return val


def normalize_source(src, where, pr, errors):
    """Validate a quote's source and fill in its url, label and language."""
    if not no_unknown(src, ("kind", "text", "label", "url", "path", "start", "end", "ref",
                            "lang", "sha"), where, errors):
        return None
    kind = text(src, "kind", where, errors)
    if kind and kind not in KINDS:
        errors.add(where, f"kind '{kind}' is not one of {', '.join(KINDS)}")
    out = {"kind": kind, "text": text(src, "text", where, errors),
           "label": text(src, "label", where, errors, required=False),
           "url": text(src, "url", where, errors, required=False), "lang": ""}
    if kind == "pr_description":
        out["url"] = out["url"] or pr["url"]
        out["label"] = out["label"] or "PR description"
    elif kind == "comment":
        if not GH_URL_RE.match(out["url"]):
            errors.add(where, "a comment source needs the comment's GitHub url")
        if not out["label"]:
            errors.add(where, "a comment source needs a label, e.g. \"comment by @login\"")
    elif kind == "code":
        out["path"] = text(src, "path", where, errors)
        out["start"] = integer(src, "start", where, errors)
        out["end"] = integer(src, "end", where, errors, default=out["start"])
        out["ref"] = text(src, "ref", where, errors, required=False) or pr["commit"]
        span = f"L{out['start']}" + (f"-L{out['end']}" if out["end"] != out["start"] else "")
        out["url"] = f"{pr['repo_url']}/blob/{out['ref']}/{out['path']}#{span}"
        out["label"] = out["label"] or f"{out['path']}:{span}"
        out["lang"] = text(src, "lang", where, errors, required=False) \
            or LANGS.get(Path(out["path"]).suffix, "")
    elif kind == "commit":
        out["sha"] = text(src, "sha", where, errors)
        out["url"] = f"{pr['repo_url']}/commit/{out['sha']}"
        out["label"] = out["label"] or f"commit {out['sha'][:8]}"
    return out


def load(path, errors):
    """Read the data file and return the template context with every optional key present."""
    try:
        data = tomllib.loads(Path(path).read_text())
    except tomllib.TOMLDecodeError as e:
        errors.add(path, f"TOML syntax: {e}")
        return None
    no_unknown(data, ("not_checked", "pr", "summary", "gist", "fact_checks", "checks",
                      "changes", "issues", "questions"), "top level", errors)

    pr = data.get("pr", {})
    no_unknown(pr, ("url", "commit"), "pr", errors)
    url = text(pr, "url", "pr", errors)
    m = PR_URL_RE.match(url)
    if not m:
        errors.add("pr", "url must look like https://github.com/<owner>/<repo>/pull/<N>")
        return None
    commit = text(pr, "commit", "pr", errors)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        errors.add("pr", "commit must be the full 40-character SHA")
    ctx = {"pr": {"url": url, "commit": commit, "owner": m.group(1), "repo": m.group(2),
                  "number": int(m.group(3)),
                  "repo_url": f"https://github.com/{m.group(1)}/{m.group(2)}"}}

    summary = data.get("summary", {})
    keys = ("opening", "what_it_does", "how_checked", "bottom_line")
    no_unknown(summary, keys, "summary", errors)
    ctx["summary"] = {k: text(summary, k, "summary", errors) for k in keys}

    not_checked = data.get("not_checked")
    if not isinstance(not_checked, list) or not not_checked \
            or not all(isinstance(s, str) and s.strip() for s in not_checked):
        errors.add("not_checked", "must be a non-empty array of strings, placed before the "
                                  "first [table] in the file")
        not_checked = []
    ctx["not_checked"] = [s.strip() for s in not_checked]

    ctx["gist_table"] = {"url": "", "description": ""}
    gist = data.get("gist")
    if gist is not None and no_unknown(gist, ("url", "description"), "gist", errors):
        url = text(gist, "url", "gist", errors, required=False)
        if url and not GIST_URL_RE.match(url):
            errors.add("gist", "url must be the pinned link `review.py share --create` writes; "
                               "don't edit it")
        ctx["gist_table"] = {"url": url,
                             "description": text(gist, "description", "gist", errors,
                                                 required=False)}

    ctx["fact_checks"] = []
    for i, fc in enumerate(table_list(data, "fact_checks", errors, required=True), 1):
        where = f"fact_checks[{i}]"
        if not no_unknown(fc, ("type", "claim", "result", "finding", "evidence_note", "evidence_links",
                               "request", "source"), where, errors):
            continue
        fc_type = text(fc, "type", where, errors)
        if fc_type and fc_type not in RESULTS:
            errors.add(where, f"type '{fc_type}' is not one of {', '.join(RESULTS)}")
        result = text(fc, "result", where, errors)
        if fc_type in RESULTS and result and result not in RESULTS[fc_type]:
            errors.add(where, f"result '{result}' is not one of "
                              f"{', '.join(RESULTS[fc_type])} for a {fc_type}")
        request = text(fc, "request", where, errors, required=False)
        note, links = "", []
        if fc_type == "claim":
            note = text(fc, "evidence_note", where, errors)
            links = fc.get("evidence_links", [])
            if not isinstance(links, list):
                errors.add(where, "evidence_links must be an array of {label, url} tables")
                links = []
            for j, link in enumerate(links, 1):
                lw = f"{where}.evidence_links[{j}]"
                if no_unknown(link, ("label", "url"), lw, errors):
                    text(link, "label", lw, errors)
                    if not text(link, "url", lw, errors).startswith("https://"):
                        errors.add(lw, "url must be an https:// link anyone can open")
            if result == "Confirmed" and not links:
                errors.add(where, "result = \"Confirmed\" needs evidence_links to the "
                                  "author's code")
            if result in ("Partly Confirmed", "Not Verified") and not request:
                errors.add(where, "a claim that is not Confirmed needs a request for the code "
                                  "that would let someone verify it")
        elif any(k in fc for k in ("evidence_note", "evidence_links")):
            errors.add(where, "evidence fields are only for type = \"claim\"")
        elif result in ("Partly matches", "Does not match") and not request:
            errors.add(where, "a description that does not match the code needs a request")
        if "source" not in fc:
            errors.add(where, "missing [fact_checks.source]")
        ctx["fact_checks"].append({
            "type": fc_type, "claim": text(fc, "claim", where, errors), "result": result,
            "finding": text(fc, "finding", where, errors),
            "evidence_note": note,
            "evidence_links": [{"label": link["label"].strip(), "url": link["url"].strip()}
                               for link in links if isinstance(link, dict)
                               and isinstance(link.get("label"), str)
                               and isinstance(link.get("url"), str)],
            "request": request,
            "source": normalize_source(fc.get("source", {}), f"{where}.source", ctx["pr"], errors)})

    # Checks you ran yourself. They are kept apart from the fact checks, which only judge
    # the evidence in the PR.
    ctx["checks"] = []
    for i, c in enumerate(table_list(data, "checks", errors, required=False), 1):
        where = f"checks[{i}]"
        if not no_unknown(c, ("title", "finding", "our_code"), where, errors):
            continue
        our_code = c.get("our_code")
        if not isinstance(our_code, list) or not our_code \
                or not all(isinstance(f, str) and f.strip() for f in our_code):
            errors.add(where, "our_code must name the files in gist/ that this check ran")
            our_code = []
        ctx["checks"].append({"title": text(c, "title", where, errors),
                              "finding": text(c, "finding", where, errors),
                              "our_code": our_code})

    ctx["changes"] = []
    for i, ch in enumerate(table_list(data, "changes", errors, required=True), 1):
        where = f"changes[{i}]"
        if not no_unknown(ch, ("summary", "files"), where, errors):
            continue
        files = ch.get("files", [])
        if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
            errors.add(where, "files must be an array of strings")
            files = []
        ctx["changes"].append({"summary": text(ch, "summary", where, errors), "files": files})

    ctx["issues"] = []
    for i, it in enumerate(table_list(data, "issues", errors, required=False), 1):
        where = f"issues[{i}]"
        if not no_unknown(it, ("severity", "title", "inline", "problem", "fix", "location",
                               "quote", "raised_by"), where, errors):
            continue
        severity = text(it, "severity", where, errors)
        if severity and severity not in SEVERITIES:
            errors.add(where, f"severity '{severity}' is not one of {', '.join(SEVERITIES)}")
        inline = it.get("inline", False)
        if not isinstance(inline, bool):
            errors.add(where, "inline must be true or false")
        loc = it.get("location")
        if loc is not None and no_unknown(loc, ("path", "start", "end", "side"),
                                          f"{where}.location", errors):
            start = integer(loc, "start", f"{where}.location", errors)
            loc = {"path": text(loc, "path", f"{where}.location", errors), "start": start,
                   "end": integer(loc, "end", f"{where}.location", errors, default=start),
                   "side": loc.get("side", "RIGHT")}
            if loc["side"] not in ("RIGHT", "LEFT"):
                errors.add(f"{where}.location", "side must be RIGHT or LEFT")
            if loc["end"] < loc["start"]:
                errors.add(f"{where}.location", "end is before start")
        if inline and loc is None:
            errors.add(where, "an inline issue needs a [issues.location]")
        quote = it.get("quote")
        if quote is not None:
            quote = normalize_source(quote, f"{where}.quote", ctx["pr"], errors)
        raised = it.get("raised_by")
        if raised is not None and no_unknown(raised, ("login", "url"), f"{where}.raised_by",
                                             errors):
            raised = {"login": text(raised, "login", f"{where}.raised_by", errors).lstrip("@"),
                      "url": text(raised, "url", f"{where}.raised_by", errors)}
        ctx["issues"].append({
            "severity": severity, "title": text(it, "title", where, errors), "inline": inline,
            "problem": text(it, "problem", where, errors), "fix": text(it, "fix", where, errors),
            "location": loc, "quote": quote, "raised_by": raised})

    ctx["questions"] = []
    for i, q in enumerate(table_list(data, "questions", errors, required=False), 1):
        where = f"questions[{i}]"
        if no_unknown(q, ("question", "would_settle"), where, errors):
            ctx["questions"].append({
                "question": text(q, "question", where, errors),
                "would_settle": text(q, "would_settle", where, errors, required=False)})
    return ctx


class Sources:
    """Fetch and cache the texts that quotes are checked against."""

    def __init__(self, pr):
        self.pr = pr
        self.cache = {}

    def get(self, key, path, field=None, accept=None):
        if key not in self.cache:
            out, err = gh_api(path, accept)
            if err is None and field:
                obj = json.loads(out)
                for f in field.split("."):
                    obj = obj.get(f) if isinstance(obj, dict) else None
                out = obj or ""
            self.cache[key] = (out, err)
        return self.cache[key]

    def file_lines(self, path, ref):
        out, err = self.get(("file", path, ref),
                            f"repos/{self.pr['owner']}/{self.pr['repo']}/contents/{path}?ref={ref}",
                            accept="application/vnd.github.raw+json")
        return (None, err) if err else (out.splitlines(), None)

    def text_for(self, src):
        """The text a quote must come from, or (None, reason)."""
        repo = f"repos/{self.pr['owner']}/{self.pr['repo']}"
        if src["kind"] == "pr_description":
            return self.get("body", f"{repo}/pulls/{self.pr['number']}", "body")
        if src["kind"] == "commit":
            return self.get(("commit", src["sha"]), f"{repo}/commits/{src['sha']}",
                            "commit.message")
        if src["kind"] == "code":
            lines, err = self.file_lines(src["path"], src["ref"])
            if err:
                return None, err
            if src["end"] > len(lines):
                return None, f"{src['path']} has {len(lines)} lines at {src['ref'][:10]}"
            return "\n".join(lines[src["start"] - 1:src["end"]]), None
        m = GH_URL_RE.match(src["url"])
        owner, name, number, frag = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        repo = f"repos/{owner}/{name}"
        for pattern, api in ((r"issuecomment-(\d+)", "issues/comments/{}"),
                             (r"discussion_r(\d+)", "pulls/comments/{}"),
                             (r"pullrequestreview-(\d+)", f"pulls/{number}/reviews/{{}}")):
            fm = re.fullmatch(pattern, frag)
            if fm:
                return self.get(("comment", src["url"]), f"{repo}/{api.format(fm.group(1))}",
                                "body")
        if frag:
            return None, f"cannot tell which comment '#{frag}' is"
        return self.get(("issue", src["url"]), f"{repo}/issues/{number}", "body")


def squash(s):
    return " ".join(s.split())


def check_quote(src, where, sources, errors):
    source_text, err = sources.text_for(src)
    if err:
        errors.add(where, f"cannot fetch the source: {err}")
        return
    hay, pos = squash(source_text), 0
    for frag in src["text"].split(ELISION):
        frag = squash(frag)
        if not frag:
            continue
        found = hay.find(frag, pos)
        if found < 0:
            shown = frag if len(frag) <= 120 else frag[:117] + "..."
            errors.add(where, f"quote is not word for word in its source ({src['label']}); "
                              f"this part was not found: \"{shown}\"")
            return
        pos = found + len(frag)


def check_locations(ctx, sources, errors):
    pr = ctx["pr"]
    anchors = None
    for i, it in enumerate(ctx["issues"], 1):
        loc, where = it["location"], f"issues[{i}].location"
        if loc is None:
            continue
        if loc["side"] == "RIGHT":
            lines, err = sources.file_lines(loc["path"], pr["commit"])
            if err:
                errors.add(where, f"cannot read {loc['path']} at the reviewed commit: {err}")
                continue
            if loc["end"] > len(lines):
                errors.add(where, f"{loc['path']} has only {len(lines)} lines")
        if not it["inline"]:
            continue
        if anchors is None:
            anchors = post_review.diff_lines(pr["owner"], pr["repo"], pr["number"])
        side_lines = anchors.get(loc["path"], {}).get(loc["side"], {})
        if loc["path"] not in anchors:
            errors.add(where, "file is not in the PR diff; set inline = false")
        elif loc["start"] not in side_lines or loc["end"] not in side_lines:
            errors.add(where, f"lines are not in the diff on the {loc['side']} side; "
                              "set inline = false or move the anchor")
        elif side_lines[loc["start"]] != side_lines[loc["end"]]:
            errors.add(where, "range spans two diff hunks")


def read_gist_dir(gist_dir, errors):
    """{file name: text} for the files in gist/, after the checks that make them safe to share."""
    contents = {}
    for path in sorted(gist_dir.iterdir()):
        where = f"gist/{path.name}"
        if path.is_dir():
            errors.add(where, "a gist has no directories; keep gist/ flat")
            continue
        if path.name.startswith("."):
            errors.add(where, "hidden file; remove it so it is not uploaded")
            continue
        raw = path.read_bytes()
        if len(raw) > MAX_GIST_FILE_BYTES:
            errors.add(where, f"{len(raw)} bytes; keep each file under {MAX_GIST_FILE_BYTES}")
            continue
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            errors.add(where, "not UTF-8 text")
            continue
        for n, line in enumerate(content.splitlines(), 1):
            for what, pattern in (("a local file path", LOCAL_PATH_RE),
                                  ("an e-mail address", EMAIL_RE),
                                  ("something that looks like a credential", SECRET_RE)):
                if pattern.search(line):
                    errors.add(f"{where}:{n}", f"{what}: {line.strip()[:100]}")
        contents[path.name] = content
    if not gist_in_use(contents):
        return contents
    readme = contents.get("README.md")
    if readme is None:
        errors.add("gist/", "needs a README.md: what each file checks, how to run it, and "
                            "what output to expect")
        return contents
    for name in contents:
        if name != "README.md" and name not in readme:
            errors.add("gist/README.md", f"does not mention {name}")
    for n, line in enumerate(readme.splitlines(), 1):
        if PLACEHOLDER_RE.search(line):
            errors.add(f"gist/README.md:{n}", f"skeleton placeholder left: {line.strip()[:100]}")
    return contents


def gist_in_use(contents):
    """gist/ counts once it holds code; the README skeleton from `init` alone does not."""
    return bool(contents) and any(name != "README.md" for name in contents)


def check_uploaded_gist(url, contents, errors):
    """The pinned gist revision in [gist].url must hold exactly the files in gist/."""
    m = GIST_URL_RE.match(url)
    out, err = gh_api(f"gists/{m.group(2)}/{m.group(3)}")
    if err:
        errors.add("gist", f"cannot read {url}: {err}")
        return
    remote = json.loads(out).get("files", {})
    differ = sorted(set(remote) ^ set(contents)) + sorted(
        name for name in set(remote) & set(contents)
        if remote[name].get("truncated") or remote[name].get("content") != contents[name])
    if differ:
        errors.add("gist", f"gist/ no longer matches the uploaded revision ({', '.join(differ)}); "
                           "run `review.py share <review> --create` again")


def plain_style():
    """The plain-style skill's checker and reflow modules."""
    sys.path.insert(0, str(PLAIN_STYLE_SCRIPTS))
    try:
        import check_style
        import reflow_md
    except ImportError:
        sys.exit(f"cannot apply the plain style: check_style.py and reflow_md.py are not in "
                 f"{PLAIN_STYLE_SCRIPTS}")
    return check_style, reflow_md


def reflow(text):
    """Put each sentence on its own line (plain-style's reflow_md.py)."""
    return plain_style()[1].reflow_text(text, "sentence")


def quoted_only(line):
    """True when every non-ASCII character on the line is inside a > quote or a "..." phrase."""
    if re.match(r"^ {0,3}>", line):
        return True
    return all(ord(ch) <= 127 for ch in re.sub(r'"[^"\n]*"', "", line))


def style_check(label, text, errors, warnings):
    """Run plain-style's checker: errors block the render, warnings call for a reread.

    Text in quotes is skipped (the checker's --skip-quoted), and non-ASCII characters are
    allowed inside a > quote or a double-quoted phrase, since those are the PR's own words.
    """
    lines = text.split("\n")
    for f in plain_style()[0].check_text(label, lines, skip_quoted=True):
        if f.rule == "non-ascii" and quoted_only(lines[f.line - 1]):
            continue
        msg = f"style [{f.rule}, {f.guide}] {f.message} | {f.snippet}"
        if f.severity == "error":
            errors.add(f"{label}:{f.line}", msg)
        else:
            warnings.append(f"{label}:{f.line}: {msg}")


def reflow_in_place(path):
    """Reflow a markdown file to one sentence per line and return its new text."""
    text = path.read_text()
    new = reflow(text)
    if new != text:
        path.write_text(new)
    return new


def check_rendered(section, ctx, errors):
    for n, line in enumerate(section.splitlines(), 1):
        if LOCAL_PATH_RE.search(line):
            errors.add(f"rendered line {n}", f"local file path in posted text: {line.strip()[:100]}")
    try:
        body, comments, _ = post_review.parse_review(section)
    except SystemExit as e:
        errors.add("rendered section", f"post_review.py cannot parse it: {e}")
        return
    if not body:
        errors.add("rendered section", "review body is empty")
    want = [(it["location"]["path"], it["location"]["start"], it["location"]["end"],
             it["location"]["side"]) for it in ctx["issues"] if it["inline"]]
    got = [(c["path"], c["start"], c["end"], c["side"]) for c in comments]
    if want != got:
        errors.add("rendered section", f"inline comments parse back as {got}, expected {want}; "
                                       "does some text start a line with '####' or "
                                       "'### Inline comments'?")


def pr_warnings(ctx):
    pr, warnings = ctx["pr"], []
    out, err = gh_api(f"repos/{pr['owner']}/{pr['repo']}/pulls/{pr['number']}")
    if err:
        warnings.append(f"cannot read the PR state: {err}")
    else:
        info = json.loads(out)
        state = "merged" if info.get("merged") else info.get("state")
        if state != "open":
            warnings.append(f"PR is {state}; `review.py post` will refuse to post")
        if info["head"]["sha"] != pr["commit"]:
            warnings.append(f"PR head moved to {info['head']['sha'][:10]}; re-check the findings "
                            "before posting")
    return warnings


def render(pr_dir, template=None, to_stdout=False):
    """Check reviews/<repo>/<N>/review.toml and write github_review.md (or print it)."""
    pr_dir = Path(pr_dir).resolve()
    data_path = pr_dir / "review.toml"
    if not data_path.exists():
        sys.exit(f"no review.toml in {pr_dir}; run `review.py init` first")
    out_path = pr_dir / "github_review.md"
    notes_path = pr_dir / "overall_review.md"
    template = Path(template) if template else pr_dir.parent.parent / "review_template.md"
    notes_text = notes_path.read_text() if notes_path.exists() else ""

    errors = Errors()
    for n, line in enumerate(data_path.read_text().splitlines(), 1):
        if not line.lstrip().startswith("#") and PLACEHOLDER_RE.search(line):
            errors.add(f"review.toml:{n}", f"skeleton placeholder left: {line.strip()[:100]}")
    if errors:
        sys.exit("cannot render; fill in or delete these skeleton entries:\n  "
                 + "\n  ".join(errors))
    ctx = load(data_path, errors)
    if ctx is None or errors:
        sys.exit("cannot render:\n  " + "\n  ".join(errors))

    # The plain-style workflow (reflow, then check) for each markdown file of the review.
    style_warnings = []
    if notes_path.exists():
        notes_text = reflow_in_place(notes_path)
        style_check(notes_path.name, notes_text, errors, style_warnings)

    pr = ctx["pr"]
    if (pr_dir.parent.name, pr_dir.name) != (pr["repo"], str(pr["number"])):
        errors.add(str(pr_dir), f"the directory for {pr['url']} is "
                                f"reviews/{pr['repo']}/{pr['number']}")
    reviewed = re.search(r"Reviewed commit:\s*`?([0-9a-f]{7,40})`?", notes_text)
    if reviewed and not pr["commit"].startswith(reviewed.group(1)):
        errors.add(notes_path.name, f"Reviewed commit {reviewed.group(1)[:10]} differs from "
                                    f"pr.commit {pr['commit'][:10]}")

    gist_dir = pr_dir / "gist"
    if (gist_dir / "README.md").exists():
        reflow_in_place(gist_dir / "README.md")
    gist_files = read_gist_dir(gist_dir, errors) if gist_dir.is_dir() else None
    if gist_files is not None and not gist_in_use(gist_files):
        gist_files = None
    gist_url = ctx["gist_table"]["url"]
    if gist_files is None:
        ctx["gist"] = None
        if gist_url:
            errors.add("gist", "[gist].url is set, but gist/ holds no code")
    else:
        ctx["gist"] = {"url": gist_url or post_review.GIST_PENDING}
        if "README.md" in gist_files:
            style_check("gist/README.md", gist_files["README.md"], errors, style_warnings)
    for i, c in enumerate(ctx["checks"], 1):
        for name in c["our_code"]:
            if gist_files is None:
                errors.add(f"checks[{i}]", "our_code names files, but gist/ holds no code")
                break
            if name not in gist_files:
                errors.add(f"checks[{i}]", f"our_code '{name}' is not in gist/")
    sources = Sources(ctx["pr"])
    for i, fc in enumerate(ctx["fact_checks"], 1):
        check_quote(fc["source"], f"fact_checks[{i}].source", sources, errors)
    for i, it in enumerate(ctx["issues"], 1):
        if it["quote"]:
            check_quote(it["quote"], f"issues[{i}].quote", sources, errors)
    check_locations(ctx, sources, errors)
    if gist_url and gist_files:
        check_uploaded_gist(gist_url, gist_files, errors)

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(template.parent)),
                             undefined=jinja2.StrictUndefined, trim_blocks=True,
                             lstrip_blocks=True, keep_trailing_newline=True)
    review = env.get_template(template.name).render(**ctx).strip() + "\n"
    review = reflow(review)
    check_rendered(review, ctx, errors)
    style_check(out_path.name, review, errors, style_warnings)
    if errors:
        sys.exit(f"cannot render ({len(errors)} problem(s)):\n  " + "\n  ".join(errors))

    for w in pr_warnings(ctx):
        print(f"warning: {w}")
    for w in style_warnings:
        print(f"style warning (reread it, and change it if it breaks the rule): {w}")
    if not notes_text:
        print(f"warning: {notes_path} does not exist yet")
    left = sorted({m.group(0) for m in PLACEHOLDER_RE.finditer(notes_text)})
    if left:
        print(f"warning: overall_review.md still has {len(left)} skeleton placeholder(s), "
              f"e.g. {left[0]}")
    if gist_files is not None and not gist_url:
        print(f"note: gist/ is not uploaded yet, so the review links {post_review.GIST_PENDING}; "
              "`review.py share --create` uploads it in Step 6, right before posting")
    if to_stdout:
        print(review, end="")
        return
    out_path.write_text(review)
    n_inline = sum(1 for it in ctx["issues"] if it["inline"])
    print(f"wrote {out_path}: {len(ctx['fact_checks'])} fact checks, "
          f"{len(ctx['issues'])} issues ({n_inline} inline), {len(ctx['questions'])} questions")
