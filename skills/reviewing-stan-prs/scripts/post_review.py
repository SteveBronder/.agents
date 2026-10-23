"""Post the GitHub review section of a review markdown file as a PR review.

Library for `review.py post`. post() reads reviews/<repo>/<N>/github_review.md, rendered
by render_review.py, and does a dry run (validate and print the payload) unless
do_post=True, which is only for after the user said yes. The PR comes from the file's
"- PR: <url>" header.

The section to post sits between these markers in the review file:

  <!-- BEGIN GITHUB REVIEW -->
  ### Review body
  ...markdown...
  ### Inline comments
  #### stan/math/prim/fun/foo.hpp:L120
  ...comment...
  #### stan/math/prim/fun/foo.hpp:L120-L131
  ...comment on a range...
  #### stan/math/prim/fun/foo.hpp:L57 (LEFT)
  ...comment on a deleted line (old-file line number)...
  <!-- END GITHUB REVIEW -->

The review is always event=COMMENT unless another event is given (only when the user
asks for APPROVE or REQUEST_CHANGES). It is pinned to the head SHA recorded in the file
("Reviewed commit: `<sha>`"); if the PR head has moved, posting is refused unless
allow_moved_head is set, because line numbers may no longer match. Posting is also
refused while the review still links the GIST_NOT_UPLOADED_YET placeholder.

Inline comments whose line is not part of the diff cannot be anchored on GitHub. They
are reported; with fold_invalid they are moved into the review body instead.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

BEGIN = "<!-- BEGIN GITHUB REVIEW -->"
END = "<!-- END GITHUB REVIEW -->"
# render_review.py puts this in place of the gist link until `review.py share` uploads gist/.
GIST_PENDING = "GIST_NOT_UPLOADED_YET"
ANCHOR_RE = re.compile(r"^####\s+`?([^`\s:]+):L(\d+)(?:-L(\d+))?`?\s*(\((LEFT|RIGHT)\))?\s*$")


def gh(args, input_text=None):
    res = subprocess.run(["gh"] + args, capture_output=True, text=True, input=input_text)
    if res.returncode != 0:
        sys.exit(f"gh {' '.join(args)} failed:\n{res.stderr.strip()}")
    return res.stdout


def parse_pr_ref(ref):
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", ref)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    m = re.match(r"(?:([\w.-]+)/)?([\w.-]+)#(\d+)$", ref)
    if m:
        return m.group(1) or "stan-dev", m.group(2), int(m.group(3))
    sys.exit(f"cannot parse PR reference: {ref!r}")


def parse_review(md):
    if BEGIN not in md or END not in md:
        sys.exit(f"review file has no {BEGIN} ... {END} section")
    section = md.split(BEGIN, 1)[1].split(END, 1)[0]
    parts = re.split(r"^###\s+Inline comments\s*$", section, maxsplit=1, flags=re.M)
    body = re.sub(r"^###\s+Review body\s*$", "", parts[0], count=1, flags=re.M).strip()
    comments = []
    if len(parts) > 1:
        cur = None
        for line in parts[1].splitlines():
            m = ANCHOR_RE.match(line.strip())
            if m:
                if cur:
                    comments.append(cur)
                start, end = int(m.group(2)), int(m.group(3) or m.group(2))
                cur = {"path": m.group(1), "start": start, "end": end,
                       "side": m.group(5) or "RIGHT", "lines": []}
            elif line.startswith("####"):
                sys.exit(f"cannot parse inline-comment anchor: {line!r} "
                         "(expected '#### path/to/file:L12' or ':L12-L20' with optional '(LEFT)')")
            elif cur is not None:
                cur["lines"].append(line)
        if cur:
            comments.append(cur)
    for c in comments:
        c["body"] = "\n".join(c.pop("lines")).strip()
    reviewed = re.search(r"Reviewed commit:\s*`?([0-9a-f]{7,40})`?", md)
    return body, comments, reviewed.group(1) if reviewed else None


def diff_lines(owner, repo, number):
    """{path: {"RIGHT": {line: hunk_id}, "LEFT": {line: hunk_id}}} for lines GitHub can anchor."""
    files = json.loads(gh(["api", f"repos/{owner}/{repo}/pulls/{number}/files", "--paginate",
                           "--slurp"]))
    files = [f for page in files for f in page]
    valid = {}
    for f in files:
        sides = {"RIGHT": {}, "LEFT": {}}
        patch = f.get("patch")
        if patch:
            old = new = 0
            hunk = -1
            for ln in patch.splitlines():
                h = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", ln)
                if h:
                    old, new, hunk = int(h.group(1)), int(h.group(2)), hunk + 1
                    continue
                if ln.startswith("+"):
                    sides["RIGHT"][new] = hunk
                    new += 1
                elif ln.startswith("-"):
                    sides["LEFT"][old] = hunk
                    old += 1
                elif ln.startswith("\\"):
                    continue
                else:
                    sides["RIGHT"][new] = hunk
                    sides["LEFT"][old] = hunk
                    old += 1
                    new += 1
        valid[f["filename"]] = sides
    return valid


def post(pr_dir, do_post=False, event="COMMENT", allow_moved_head=False, fold_invalid=False):
    """Validate reviews/<repo>/<N>/github_review.md and post it (dry run unless do_post)."""
    review_md = Path(pr_dir) / "github_review.md"
    if not review_md.exists():
        sys.exit(f"no {review_md}; run `review.py render` first")
    text = review_md.read_text()
    pr_line = re.search(r"^- PR:\s*(\S+)", text, re.M)
    if not pr_line:
        sys.exit(f"{review_md} has no '- PR: <url>' header; render it again")
    owner, repo, number = parse_pr_ref(pr_line.group(1))
    body, comments, reviewed_sha = parse_review(text)
    head = json.loads(gh(["pr", "view", str(number), "-R", f"{owner}/{repo}", "--json",
                          "headRefOid,state,url"]))
    problems = []
    if GIST_PENDING in body or any(GIST_PENDING in c["body"] for c in comments):
        problems.append("the gist is not uploaded yet: run `review.py share <review> --create`, "
                        "then `review.py render <review>` again")
    if head["state"] != "OPEN":
        problems.append(f"PR is {head['state']}")
    if not reviewed_sha:
        problems.append("review file has no 'Reviewed commit: `<sha>`' line")
    elif not head["headRefOid"].startswith(reviewed_sha):
        msg = f"PR head moved: reviewed {reviewed_sha[:10]}, now {head['headRefOid'][:10]}"
        if allow_moved_head:
            print(f"warning: {msg} (posting anyway, pinned to the reviewed commit)")
        else:
            problems.append(msg + " (re-check line numbers, or pass --allow-moved-head)")
    commit_id = reviewed_sha if reviewed_sha and len(reviewed_sha) == 40 else head["headRefOid"]

    valid = diff_lines(owner, repo, number)
    good, bad = [], []
    for c in comments:
        side_lines = valid.get(c["path"], {}).get(c["side"], {})
        if c["path"] not in valid:
            why = "file is not in the PR diff"
        elif c["start"] not in side_lines or c["end"] not in side_lines:
            why = f"line(s) not in the diff on the {c['side']} side"
        elif side_lines[c["start"]] != side_lines[c["end"]]:
            why = "range spans two diff hunks"
        elif not c["body"]:
            why = "empty comment"
        else:
            why = None
        (bad if why else good).append((c, why))

    print(f"PR: {head['url']}  event={event}  commit={commit_id[:10]}")
    print(f"body: {len(body)} chars; inline comments: {len(good)} anchorable, {len(bad)} not")
    for c, why in bad:
        print(f"  cannot anchor {c['path']}:L{c['start']}-L{c['end']} ({c['side']}): {why}")

    if bad and fold_invalid:
        extra = "\n\n**Comments on lines outside the diff**\n"
        for c, _ in bad:
            rng = f"L{c['start']}" + (f"-L{c['end']}" if c["end"] != c["start"] else "")
            link = f"https://github.com/{owner}/{repo}/blob/{commit_id}/{c['path']}#{rng}"
            extra += f"\n- [`{c['path']}:{rng}`]({link}): {c['body']}\n"
        body += extra
        bad = []
    if bad:
        problems.append(f"{len(bad)} inline comment(s) cannot be anchored (fix them or pass --fold-invalid)")

    payload = {"commit_id": commit_id, "body": body, "event": event, "comments": []}
    for c, _ in good:
        item = {"path": c["path"], "body": c["body"], "line": c["end"], "side": c["side"]}
        if c["start"] != c["end"]:
            item.update(start_line=c["start"], start_side=c["side"])
        payload["comments"].append(item)

    if not do_post:
        print("\n--- dry run; payload that would be posted ---")
        print(json.dumps(payload, indent=2))
        if problems:
            print("\nproblems that would block --post:\n  " + "\n  ".join(problems))
        return
    if problems:
        sys.exit("refusing to post:\n  " + "\n  ".join(problems))
    out = json.loads(gh(["api", "-X", "POST", f"repos/{owner}/{repo}/pulls/{number}/reviews",
                         "--input", "-"], input_text=json.dumps(payload)))
    print(f"posted review {out.get('id')}: {out.get('html_url')}")
