"""Gather everything a reviewer needs to know about a Stan PR into one markdown file.

Library for `review.py init` and `review.py context`, which write the result to
reviews/<repo>/<N>/context.md. <pr> may be a URL (https://github.com/stan-dev/math/pull/3437),
"math#3437" or "stan-dev/math#3437".

What it collects (read-only, via the gh CLI):
  * PR metadata (base/head, head SHA, size, draft state, CI checks)
  * a stack analysis: is this PR built on top of another unmerged PR?
  * the description, human comments, review threads (with resolution state);
    stan-buildbot comments are condensed to their benchmark table
  * every commit, classified (test-only / src-only / mixed / merge / bot-format)
    and a red/green (test-first) assessment
  * changed files, classified as src / test / doc / build
  * the links of comments, reviews and review-thread comments, so a review can cite them

gather() returns the markdown together with the stack verdict (STOP, CHECK or
PROCEED), the open PRs this one is blocked on, and the PR metadata.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import worktree

DEFAULT_OWNER = "stan-dev"
TRUNK_BRANCHES = {"develop", "master", "main"}
BOT_LOGINS = {"stan-buildbot", "github-actions", "dependabot", "codecov"}

# Phrases that say THIS PR needs another one to land first.
DEPENDS_RE = re.compile(
    r"(based on|depends on|dependent on|stacked on|on top of|builds? on|built on|"
    r"requires|must be merged after|merged? after|go (in )?after|"
    r"after .{0,30}(is|are|gets?) merged|needs? .{0,30}merged|branched (off|from)|"
    r"retarget)",
    re.I,
)
# Phrases that say ANOTHER PR builds on this one (a follow-up), or is merely related.
FOLLOWUP_RE = re.compile(
    r"(follow[- ]?up|repairs? (that|these|this)|later PR|separate PR|will (fix|address)|"
    r"after this one|on top of this|based on this|independent|alternative to|related)",
    re.I,
)
SOFT_ORDER_RE = re.compile(r"(preferabl|ideally|probably|touch(es)? (the )?same)", re.I)


def run(cmd, check=True):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{res.stderr.strip()}")
    return res.stdout


def gh_json(args, check=True):
    out = run(["gh"] + args, check=check)
    return json.loads(out) if out.strip() else None


def gh_api(path, paginate=False, check=True):
    args = ["api", path]
    if paginate:
        args.append("--paginate")
        # --paginate concatenates JSON arrays; --slurp wraps pages in one array
        args.append("--slurp")
    data = gh_json(args, check=check)
    if paginate and isinstance(data, list):
        flat = []
        for page in data:
            flat.extend(page if isinstance(page, list) else [page])
        return flat
    return data


def parse_pr_ref(ref, second=None):
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", ref)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    m = re.match(r"(?:([\w.-]+)/)?([\w.-]+)#(\d+)$", ref)
    if m:
        return m.group(1) or DEFAULT_OWNER, m.group(2), int(m.group(3))
    if second and second.isdigit():
        owner, _, repo = ref.rpartition("/")
        return owner or DEFAULT_OWNER, repo, int(second)
    sys.exit(f"cannot parse PR reference: {ref!r}")


def classify_path(path):
    p = path.lower()
    if re.search(r"(^|/)(src/)?test/|_test\.(cpp|hpp|py|r)$|(^|/)tests?/", p):
        return "test"
    if p.endswith((".md", ".rst", ".txt")) or p.startswith(("doc/", "docs/", "doxygen/")):
        return "doc"
    if re.search(r"(^|/)(makefile|make/|jenkinsfile|\.github/|cmakelists|runtests\.py)", p):
        return "build"
    return "src"


def classify_commit(c, files):
    headline = c["commit"]["message"].splitlines()[0]
    author = (c.get("author") or {}).get("login") or c["commit"]["author"]["name"]
    if len(c.get("parents", [])) > 1:
        return "merge"
    if "[jenkins] auto-formatting" in headline.lower() or author in BOT_LOGINS:
        return "bot-format"
    kinds = {classify_path(f["filename"]) for f in files}
    code = kinds & {"src", "test"}
    if code == {"test"}:
        return "test-only"
    if code == {"src"}:
        return "src-only"
    if code == {"src", "test"}:
        return "mixed"
    return "+".join(sorted(kinds)) or "empty"


def condense_buildbot(body):
    """Keep the benchmark table, mean result and commit hash; drop machine info."""
    body = re.sub(r"<details>.*?</details>", "", body, flags=re.S)
    keep = [
        ln
        for ln in body.splitlines()
        if ln.startswith("|") or ln.startswith("Mean result") or ln.startswith("Commit hash")
    ]
    return "\n".join(keep)


def find_refs(text, owner, repo):
    """Return {(owner, repo, n): [context snippets]} for PR/issue references in text."""
    refs = {}
    patterns = [
        (re.compile(r"https?://github\.com/([\w.-]+)/([\w.-]+)/(?:pull|issues)/(\d+)"), None),
        (re.compile(r"(?<![\w/.-])([\w.-]+)/([\w.-]+)#(\d+)"), None),
        (re.compile(r"(?<![\w/#&])#(\d+)\b"), (owner, repo)),
    ]
    for rx, default in patterns:
        for m in rx.finditer(text):
            if default:
                key = (default[0], default[1], int(m.group(1)))
            else:
                key = (m.group(1), m.group(2), int(m.group(3)))
            refs.setdefault(key, []).append(sentence_around(text, m.start(), m.end()))
    return refs


def sentence_around(text, start, end, limit=300):
    """The sentence (or list item / line) containing text[start:end]."""
    lo = max(0, start - limit)
    hi = min(len(text), end + limit)
    left = text[lo:start]
    right = text[end:hi]
    cut = max((left.rfind(d) for d in (". ", ".\n", "\n\n", "\n- ", "\n* ")), default=-1)
    left = left[cut + 1:] if cut >= 0 else left
    m = re.search(r"\.(\s|$)|\n\n|\n- |\n\* ", right)
    right = right[: m.start() + 1] if m else right
    return " ".join((left + text[start:end] + right).split())


def describe_ref(o, r, n):
    issue = gh_api(f"repos/{o}/{r}/issues/{n}", check=False)
    if not issue or "number" not in issue:
        return None
    info = {
        "owner": o,
        "repo": r,
        "number": n,
        "title": issue.get("title", ""),
        "state": issue.get("state", "").upper(),
        "is_pr": "pull_request" in issue,
        "merged": False,
        "url": issue.get("html_url", ""),
    }
    if info["is_pr"]:
        pr = gh_api(f"repos/{o}/{r}/pulls/{n}", check=False) or {}
        info["merged"] = bool(pr.get("merged_at"))
        info["head_sha"] = (pr.get("head") or {}).get("sha")
        info["head_ref"] = (pr.get("head") or {}).get("ref")
        info["base_ref"] = (pr.get("base") or {}).get("ref")
        if info["merged"]:
            info["state"] = "MERGED"
    return info


def ancestry(o, r, base_sha, head_sha):
    """'ahead' / 'identical' means base_sha is an ancestor of head_sha."""
    cmp = gh_api(f"repos/{o}/{r}/compare/{base_sha}...{head_sha}", check=False)
    return (cmp or {}).get("status")


def review_threads(owner, repo, number):
    query = """
    query($owner:String!,$name:String!,$number:Int!){
      repository(owner:$owner,name:$name){ pullRequest(number:$number){
        reviewThreads(first:100){ nodes{ isResolved isOutdated path line originalLine
          comments(first:50){ nodes{ author{login} body createdAt url } } } } } } }"""
    data = gh_json(
        ["api", "graphql", "-f", f"query={query}", "-F", f"owner={owner}",
         "-F", f"name={repo}", "-F", f"number={number}"],
        check=False,
    )
    try:
        return data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    except (TypeError, KeyError):
        return []


def gather(pr_ref):
    """Collect the PR's context.

    Returns a dict with "doc" (the markdown for context.md), "summary" (three lines
    starting "STACK: <verdict>"), "verdict", "blockers" (the open PRs this one waits on,
    each {"repo", "number", "state", "reason"}) and "meta" (PR fields used by the
    skeleton files).
    """
    owner, repo, number = parse_pr_ref(pr_ref)
    full = f"{owner}/{repo}"
    fields = (
        "number,title,url,author,state,isDraft,baseRefName,headRefName,headRefOid,"
        "headRepositoryOwner,isCrossRepository,body,comments,reviews,files,additions,"
        "deletions,closingIssuesReferences,labels,statusCheckRollup,createdAt,updatedAt"
    )
    pr = gh_json(["pr", "view", str(number), "-R", full, "--json", fields])
    head_owner = pr["headRepositoryOwner"]["login"]
    head_sha = pr["headRefOid"]

    # ---- commits (REST gives parents; per-commit files need one call each) ----
    commits = gh_api(f"repos/{full}/pulls/{number}/commits", paginate=True) or []
    commit_rows = []
    for c in commits[:80]:
        files = [] if len(c.get("parents", [])) > 1 else (
            (gh_api(f"repos/{full}/commits/{c['sha']}", check=False) or {}).get("files", [])
        )
        commit_rows.append({
            "sha": c["sha"],
            "headline": c["commit"]["message"].splitlines()[0],
            "author": (c.get("author") or {}).get("login") or c["commit"]["author"]["name"],
            "date": c["commit"]["committer"]["date"],
            "kind": classify_commit(c, files),
            "files": [f["filename"] for f in files],
        })

    # ---- red/green assessment ----
    substantive = [c for c in commit_rows if c["kind"] not in ("merge", "bot-format")]
    first_src = next((i for i, c in enumerate(substantive) if c["kind"] in ("src-only", "mixed")), None)
    test_first = [c for c in substantive[: first_src or 0] if c["kind"] == "test-only"]
    if first_src is None:
        tdd = "no source changes found in commits"
    elif test_first:
        tdd = (f"YES: test-only commit(s) {', '.join(c['sha'][:8] for c in test_first)} "
               f"precede the first source commit {substantive[first_src]['sha'][:8]}")
    elif substantive[first_src]["kind"] == "mixed":
        tdd = (f"NO: tests and fix land together in {substantive[first_src]['sha'][:8]}; "
               "red can only be checked by putting the base-branch source back under the new tests")
    else:
        tdd = (f"NO: source commit {substantive[first_src]['sha'][:8]} comes before any test-only commit")
    dates = sorted(c["date"] for c in substantive)
    reconstructed = len(dates) >= 3 and dates[0][:16] == dates[-1][:16]

    # ---- stack analysis ----
    stack_reasons, stack_checks, stack_notes, blockers = [], [], [], []
    base = pr["baseRefName"]
    if base not in TRUNK_BRANCHES:
        parents = gh_json(["pr", "list", "-R", full, "--head", base, "--state", "all",
                           "--json", "number,state,title,url"]) or []
        if parents:
            for p in parents:
                msg = f"base branch `{base}` is the head of {full}#{p['number']} ({p['state']}): {p['title']}"
                (stack_reasons if p["state"] == "OPEN" else stack_notes).append(msg)
                if p["state"] == "OPEN":
                    blockers.append({"repo": repo, "number": p["number"], "state": p["state"],
                                     "reason": f"the base branch `{base}` is the head of "
                                               f"{repo}#{p['number']}"})
        else:
            stack_checks.append(f"base branch `{base}` is not a trunk branch and no PR has it as head; ask the user")

    human_comments = [c for c in pr["comments"] if c["author"]["login"] not in BOT_LOGINS]
    text = pr["body"] + "\n" + "\n".join(c["body"] for c in human_comments)
    refs = find_refs(text, owner, repo)
    ref_rows = []
    for (o, r, n), snippets in list(refs.items())[:30]:
        if (o, r, n) == (owner, repo, number):
            continue
        info = describe_ref(o, r, n)
        if not info:
            continue
        depends = any(DEPENDS_RE.search(s) for s in snippets)
        followup = any(FOLLOWUP_RE.search(s) for s in snippets)
        soft = any(SOFT_ORDER_RE.search(s) for s in snippets)
        anc = None
        if info["is_pr"] and info.get("head_sha") and (o, r) == (owner, repo):
            # does this PR contain the other PR's head?  (other is our ancestor)
            if ancestry(o, r, info["head_sha"], head_sha) in ("ahead", "identical"):
                anc = "this PR's branch CONTAINS that PR's head commit"
            elif ancestry(o, r, head_sha, info["head_sha"]) in ("ahead", "identical"):
                anc = "that PR's branch contains this PR's head (it is stacked on this one)"
        info.update(snippets=snippets, depends_phrase=depends, followup_phrase=followup,
                    soft_order=soft, ancestry=anc)
        ref_rows.append(info)
        if not info["is_pr"] or info["state"] in ("MERGED", "CLOSED"):
            continue
        if anc and anc.startswith("this PR's branch CONTAINS"):
            stack_reasons.append(f"{o}/{r}#{n} is open and {anc}")
            blockers.append({"repo": r, "number": n, "state": info["state"],
                             "reason": f"this branch contains {r}#{n}'s head commit"})
        elif depends or soft:
            stack_checks.append(f"{o}/{r}#{n} is open and a sentence mentioning it has ordering "
                                "language; read it and decide which PR depends on which")

    verdict = "STOP" if stack_reasons else ("CHECK" if stack_checks else "PROCEED")

    # ---- render ----
    L = []
    L.append(f"# {full}#{number}: {pr['title']}")
    L.append("")
    L.append(f"- URL: {pr['url']}")
    L.append(f"- Author: {pr['author']['login']}  | state: {pr['state']}{' (DRAFT)' if pr['isDraft'] else ''}")
    L.append(f"- Base: `{base}`  | head: `{head_owner}:{pr['headRefName']}`  | cross-repo: {pr['isCrossRepository']}")
    L.append(f"- Head SHA: `{head_sha}`")
    L.append(f"- Size: +{pr['additions']}/-{pr['deletions']} in {len(pr['files'])} files, {len(commit_rows)} commits")
    clone = worktree.CLONES.get(repo)
    wt = (f"WT=$(python3 {Path(__file__).resolve().parent / 'review.py'} worktree {repo}#{number}"
          + ("" if clone else " --clone <the local clone>") + ")")
    L.append(f"- Worktree command: `{wt}`")
    issues = ", ".join(f"#{i['number']}" for i in pr.get("closingIssuesReferences", [])) or "none"
    L.append(f"- Closing issues (GitHub-linked): {issues}")
    checks = pr.get("statusCheckRollup") or []
    if checks:
        summ = {}
        for ch in checks:
            st = ch.get("conclusion") or ch.get("state") or ch.get("status") or "?"
            summ[st] = summ.get(st, 0) + 1
        L.append(f"- CI checks: {', '.join(f'{k}={v}' for k, v in sorted(summ.items()))}")
    L.append("")
    L.append(f"## Stack analysis: {verdict}")
    for s in stack_reasons:
        L.append(f"- STOP reason: {s}")
    for s in stack_checks:
        L.append(f"- CHECK: {s}")
    for s in stack_notes:
        L.append(f"- note: {s}")
    if not stack_reasons and not stack_checks and not stack_notes:
        L.append("- no dependency on another open PR detected")
    L.append("")
    if ref_rows:
        L.append("### Referenced PRs and issues")
        for i in ref_rows:
            kind = "PR" if i["is_pr"] else "issue"
            flags = [f for f, on in (("depends-phrase", i["depends_phrase"]),
                                     ("followup/related-phrase", i["followup_phrase"]),
                                     ("soft-order", i["soft_order"])) if on]
            L.append(f"- {i['owner']}/{i['repo']}#{i['number']} [{kind}, {i['state']}] {i['title']}"
                     + (f" (flags: {', '.join(flags)})" if flags else "")
                     + (f" (ancestry: {i['ancestry']})" if i.get("ancestry") else ""))
            for s in i["snippets"][:2]:
                L.append(f"    > ...{s}...")
        L.append("")
    L.append("## Description")
    L.append("")
    L.append(pr["body"] or "(empty)")
    L.append("")
    L.append("## Commits (oldest first)")
    L.append("")
    L.append(f"Red/green (test-first) structure: {tdd}")
    if reconstructed:
        L.append("Note: all substantive commits share one committer minute, so the history was "
                 "probably rewritten; commit order says little about how the work was done.")
    L.append("")
    L.append("| sha | kind | author | headline | files |")
    L.append("|---|---|---|---|---|")
    for c in commit_rows:
        files = ", ".join(f"`{f}`" for f in c["files"][:6]) + (" ..." if len(c["files"]) > 6 else "")
        L.append(f"| {c['sha'][:8]} | {c['kind']} | {c['author']} | {c['headline'].replace('|', '/')} | {files} |")
    L.append("")
    L.append("## Changed files")
    L.append("")
    for f in pr["files"]:
        L.append(f"- [{classify_path(f['path'])}] `{f['path']}` +{f['additions']}/-{f['deletions']}")
    L.append("")
    L.append("## Conversation (humans)")
    L.append("")
    for c in human_comments:
        L.append(f"### {c['author']['login']} ({c['createdAt'][:10]}) {c.get('url', '')}".rstrip())
        L.append(c["body"])
        L.append("")
    # The REST endpoint gives each review's html_url, which gh pr view does not.
    for rv in gh_api(f"repos/{full}/pulls/{number}/reviews", paginate=True, check=False) or []:
        if (rv.get("body") or "").strip() or rv["state"] in ("APPROVED", "CHANGES_REQUESTED"):
            L.append(f"### review by {(rv.get('user') or {}).get('login')}: {rv['state']} "
                     f"{rv.get('html_url', '')}".rstrip())
            L.append(rv.get("body") or "")
            L.append("")
    threads = review_threads(owner, repo, number)
    if threads:
        L.append("## Inline review threads")
        L.append("")
        for t in threads:
            status = "resolved" if t["isResolved"] else "UNRESOLVED"
            if t["isOutdated"]:
                status += ", outdated"
            L.append(f"### `{t['path']}:{t.get('line') or t.get('originalLine')}` ({status})")
            for cm in t["comments"]["nodes"]:
                L.append(f"- **{(cm.get('author') or {}).get('login')}** ({cm.get('url', '')}): "
                         f"{cm['body'].strip()}")
            L.append("")
    bots = [c for c in pr["comments"] if c["author"]["login"] == "stan-buildbot"]
    if bots:
        L.append("## stan-buildbot end-to-end benchmarks (latest; ratio = old/new, >1 is faster)")
        L.append("")
        L.append(condense_buildbot(bots[-1]["body"]))
        L.append("")

    summary = (f"STACK: {verdict}"
               + (f" ({'; '.join(stack_reasons or stack_checks)})" if stack_reasons or stack_checks else "")
               + f"\nPR: {full}#{number} head={head_sha} base={base} worktree: {wt}\nTDD: {tdd}")
    meta = {"owner": owner, "repo": repo, "number": number, "title": pr["title"],
            "url": pr["url"], "author": pr["author"]["login"], "state": pr["state"],
            "draft": pr["isDraft"], "base": base, "head_owner": head_owner,
            "head_ref": pr["headRefName"], "head_sha": head_sha, "worktree_cmd": wt}
    return {"doc": "\n".join(L) + "\n", "summary": summary, "verdict": verdict,
            "blockers": blockers, "meta": meta}
