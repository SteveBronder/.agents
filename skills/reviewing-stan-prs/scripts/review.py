#!/usr/bin/env python3
"""Command-line tool for the reviewing-stan-prs skill.

Each reviewed PR gets a directory reviews/<repo>/<N>/ (N is the PR number):

  overall_review.md   private notes for the user (Step 5a)
  review.toml         the GitHub review as data (Step 5b)
  github_review.md    rendered from review.toml; what gets posted (Step 5c)
  context.md          the PR context dump (Step 0)
  gist/               the code behind the review's numbers, uploaded as a gist (Step 6)
  checks/             scratch work that is not shared

Commands, in the order a review uses them:
  init <pr>       Step 0: create the directory, write context.md and print the stack
                  verdict. On STACK: STOP it writes the deferred note and stops; otherwise
                  it writes skeletons of overall_review.md, review.toml and gist/README.md,
                  never overwriting a file you have started.
  context <pr>    write context.md again, e.g. after the PR head moved
  worktree <pr> [--detached] [--clone <path>]
                  Step 2: make or reuse the PR's worktree in the local clone with gototree
                  (or, with --detached, <clone>/.worktree/pr-<N> at the PR head), record in
                  .worktree.json whether this review created it, and print only its path
  cleanup <pr> [--force]
                  remove the worktrees .worktree.json says this review created, refusing
                  any with uncommitted or untracked changes unless --force
  gototree [-d <dir>] [<user>:]<branch>
                  make or reuse the worktree <clone>/.worktree/<branch>, adding the fork as
                  a remote first for <user>:<branch>. Prints only the worktree's path.
  gotoremote [-w | --worktree=<path>] [-d <dir>] <user>:<branch>
                  add <user>'s fork as a remote and fetch <branch>; with -w make a
                  worktree, without it check the branch out in the current repository
  defer <pr> --on <repo#M> --because <reason>
                  write the deferred note for a PR stacked on another one, and remove
                  the skeleton files that were never edited
  render <pr>     Step 5c: check review.toml and gist/, write github_review.md
  share <pr>      Step 6: check gist/ and show what would be uploaded; --create uploads
                  it as a secret gist and records the link in review.toml
  post <pr>       Step 6: dry run of the GitHub review; --post posts it

<pr> is a PR link, "math#3432", "stan-dev/math#3432", or the directory reviews/<repo>/<N>.
The reviews root is /home/sbronder/open_source/stan/origin/reviews unless --root or
$STAN_REVIEWS_ROOT says otherwise.
"""

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import jinja2

sys.dont_write_bytecode = True  # keep __pycache__ out of the skill directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
import post_review  # noqa: E402
import pr_context  # noqa: E402
import render_review  # noqa: E402
import share_checks  # noqa: E402
import worktree  # noqa: E402

DEFAULT_ROOT = Path("/home/sbronder/open_source/stan/origin/reviews")
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
# Hashes of the skeleton files as `init` wrote them, so `defer` knows which are untouched.
SKELETON_RECORD = ".skeleton.json"
# The worktrees `worktree` made or reused for this PR, so `cleanup` removes only its own.
WORKTREE_RECORD = ".worktree.json"
SKELETONS = {"overall_review.md": "overall_review.md.j2", "review.toml": "review.toml.j2",
             "gist/README.md": "gist_README.md.j2"}


def locate(ref, root):
    """(directory, owner, repo, number) for a PR link, "repo#N", or a review directory."""
    path = Path(ref)
    if path.is_dir() and path.resolve().name.isdigit():
        path = path.resolve()
        return path, pr_context.DEFAULT_OWNER, path.parent.name, int(path.name)
    owner, repo, number = pr_context.parse_pr_ref(ref)
    return root / repo / str(number), owner, repo, number


def fill(template_name, **values):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES)),
                             undefined=jinja2.StrictUndefined, trim_blocks=True,
                             lstrip_blocks=True, keep_trailing_newline=True)
    return env.get_template(template_name).render(**values)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_record(pr_dir):
    path = pr_dir / SKELETON_RECORD
    return json.loads(path.read_text()) if path.exists() else {}


def untouched(pr_dir, rel, record):
    path = pr_dir / rel
    return path.exists() and record.get(rel) == sha256(path)


def is_deferred_note(path):
    return path.exists() and " deferred, stacked on " in path.read_text().splitlines()[0]


def write_context(pr_dir, owner, repo, number):
    ctx = pr_context.gather(f"{owner}/{repo}#{number}")
    pr_dir.mkdir(parents=True, exist_ok=True)
    (pr_dir / "context.md").write_text(ctx["doc"])
    print(ctx["summary"])
    print(f"context written to {pr_dir / 'context.md'}")
    return ctx


def write_deferred(pr_dir, meta, dep_repo, dep_number, dep_state, reason):
    """Replace untouched skeletons with the deferred note; refuse if notes were started."""
    record = read_record(pr_dir)
    notes = pr_dir / "overall_review.md"
    if notes.exists() and not untouched(pr_dir, "overall_review.md", record) \
            and not is_deferred_note(notes):
        sys.exit(f"{notes} has been edited; move your notes aside before deferring")
    for rel in SKELETONS:
        if rel != "overall_review.md" and untouched(pr_dir, rel, record):
            (pr_dir / rel).unlink()
    for sub in ("gist", "checks"):
        if (pr_dir / sub).is_dir() and not any((pr_dir / sub).iterdir()):
            (pr_dir / sub).rmdir()
    (pr_dir / SKELETON_RECORD).unlink(missing_ok=True)
    notes.write_text(fill("deferred.md.j2", repo=meta["repo"], number=meta["number"],
                          url=meta["url"], dep_repo=dep_repo, dep_number=dep_number,
                          dep_state=dep_state, reason=reason))
    print(f"deferred: wrote {notes}. The review stops here until {dep_repo}#{dep_number} merges.")


def cmd_init(args, root):
    pr_dir, owner, repo, number = locate(args.pr, root)
    ctx = write_context(pr_dir, owner, repo, number)
    meta = ctx["meta"]
    if meta["state"] != "OPEN" and not args.allow_closed:
        sys.exit(f"{repo}#{number} is {meta['state']}. Ask the user whether to review it, and "
                 "if so run init again with --allow-closed.")
    if ctx["verdict"] == "STOP" and ctx["blockers"]:
        b = ctx["blockers"][0]
        write_deferred(pr_dir, meta, b["repo"], b["number"], b["state"], b["reason"])
        return

    stack = {"PROCEED": "independent (STACK: PROCEED)",
             "CHECK": "<<proceeds; related: #M, or a merge-order note>> (STACK: CHECK)",
             "STOP": "<<STACK: STOP without a blocking PR; ask the user>>"}[ctx["verdict"]]
    values = dict(meta, stack=stack, today=datetime.date.today().isoformat())
    record = read_record(pr_dir)
    for sub in ("gist", "checks"):
        (pr_dir / sub).mkdir(exist_ok=True)
    for rel, template in SKELETONS.items():
        path = pr_dir / rel
        if path.exists() and not (rel == "overall_review.md" and is_deferred_note(path)):
            print(f"kept {path}")
            continue
        path.write_text(fill(template, **values))
        record[rel] = sha256(path)
        print(f"wrote skeleton {path}")
    (pr_dir / SKELETON_RECORD).write_text(json.dumps(record, indent=2) + "\n")
    if ctx["verdict"] == "CHECK":
        print("STACK: CHECK. Read the stack analysis in context.md. If this PR depends on the "
              "other one, run `review.py defer`; otherwise carry on.")


def cmd_context(args, root):
    pr_dir, owner, repo, number = locate(args.pr, root)
    write_context(pr_dir, owner, repo, number)


def cmd_defer(args, root):
    pr_dir, owner, repo, number = locate(args.pr, root)
    _, dep_repo, dep_number = pr_context.parse_pr_ref(args.on)
    res = subprocess.run(["gh", "pr", "view", str(dep_number), "-R", f"{owner}/{dep_repo}",
                          "--json", "state"], capture_output=True, text=True)
    dep_state = json.loads(res.stdout)["state"] if res.returncode == 0 else "unknown state"
    res = subprocess.run(["gh", "pr", "view", str(number), "-R", f"{owner}/{repo}", "--json",
                          "url"], capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"cannot read {owner}/{repo}#{number}: {res.stderr.strip()}")
    meta = {"repo": repo, "number": number, "url": json.loads(res.stdout)["url"]}
    pr_dir.mkdir(parents=True, exist_ok=True)
    write_deferred(pr_dir, meta, dep_repo, dep_number, dep_state, args.because)


def read_worktrees(pr_dir):
    path = pr_dir / WORKTREE_RECORD
    return json.loads(path.read_text()).get("worktrees", []) if path.exists() else []


def write_worktrees(pr_dir, entries):
    path = pr_dir / WORKTREE_RECORD
    if entries:
        path.write_text(json.dumps({"worktrees": entries}, indent=2) + "\n")
    else:
        path.unlink(missing_ok=True)


def cmd_worktree(args, root):
    pr_dir, owner, repo, number = locate(args.pr, root)
    clone = args.clone or worktree.CLONES.get(repo)
    if not clone:
        sys.exit(f"no local clone is known for {repo}; ask the user where it is and pass --clone")
    res = subprocess.run(["gh", "pr", "view", str(number), "-R", f"{owner}/{repo}", "--json",
                          "headRefName,headRepositoryOwner,isCrossRepository,headRefOid"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"cannot read {owner}/{repo}#{number}: {res.stderr.strip()}")
    pr = json.loads(res.stdout)
    try:
        base = Path(worktree.main_root(clone)) / ".worktree"
        path = base / (f"pr-{number}" if args.detached else pr["headRefName"])
        existed = path.exists()
        if args.detached:
            if existed:
                worktree.say("worktree", f"{path} already exists, using it as it is")
            else:
                worktree.git(clone, "fetch", "origin", f"pull/{number}/head", capture=False)
                worktree.git(clone, "worktree", "add", "--detach", str(path), pr["headRefOid"],
                             capture=False)
        else:
            spec = (f"{pr['headRepositoryOwner']['login']}:{pr['headRefName']}"
                    if pr["isCrossRepository"] else pr["headRefName"])
            path = Path(worktree.gototree(spec, cwd=clone))
    except worktree.GitError as e:
        sys.exit(f"{e}\nIf the branch is checked out somewhere else, or the checkout is wrong, run "
                 f"`review.py worktree {repo}#{number} --detached` instead.")
    path = path.resolve()

    entries = read_worktrees(pr_dir)
    old = next((e for e in entries if e["path"] == str(path)), None)
    created = (old or {}).get("created", False) or not existed
    entries = [e for e in entries if e["path"] != str(path)]
    entries.append({"path": str(path), "clone": str(Path(clone).resolve()),
                    "created": created, "detached": args.detached})
    pr_dir.mkdir(parents=True, exist_ok=True)
    write_worktrees(pr_dir, entries)
    head = worktree.git(str(path), "rev-parse", "HEAD").strip()
    if head != pr["headRefOid"]:
        worktree.say("worktree", f"HEAD is {head[:10]}, but the PR head is "
                                 f"{pr['headRefOid'][:10]}; see Step 2")
    if not created:
        worktree.say("worktree", "this worktree existed before the review, so `cleanup` will "
                                 "leave it in place")
    print(path)


def cmd_cleanup(args, root):
    pr_dir = locate(args.pr, root)[0]
    entries = read_worktrees(pr_dir)
    if not entries:
        print(f"nothing to clean up: no worktree is recorded in {pr_dir / WORKTREE_RECORD}")
        return
    keep, refused = [], False
    for e in entries:
        path, clone = Path(e["path"]), e["clone"]
        if not e["created"]:
            print(f"left {path}: it existed before this review")
            continue
        if not path.exists():
            print(f"{path} is already gone")
            continue
        listed = [str(Path(line[len("worktree "):]).resolve()) for line in
                  worktree.git(clone, "worktree", "list", "--porcelain").splitlines()
                  if line.startswith("worktree ")]
        if str(path) not in listed or str(path) == listed[0]:
            print(f"refusing {path}: it is not a linked worktree of {clone}")
            keep.append(e)
            refused = True
            continue
        changes = worktree.git(str(path), "status", "--porcelain").splitlines()
        if changes and not args.force:
            shown = "; ".join(changes[:5]) + (" ..." if len(changes) > 5 else "")
            print(f"refusing {path}: {len(changes)} uncommitted or untracked change(s): {shown}")
            keep.append(e)
            refused = True
            continue
        # The status check above is the safety check. --force here only lets git remove a
        # clean worktree that holds ignored files or a submodule.
        worktree.git(clone, "worktree", "remove", "--force", *(["--force"] if args.force else []),
                     str(path), capture=False)
        top = Path(listed[0]) / ".worktree"
        parent = path.parent
        while parent != top and top in parent.parents and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
        print(f"removed {path}")
    write_worktrees(pr_dir, keep)
    if refused:
        sys.exit(1)


def run_worktree_tool(fn, *fn_args, **fn_kwargs):
    """Run gototree or gotoremote and print only the resulting path on stdout."""
    try:
        print(fn(*fn_args, **fn_kwargs))
    except worktree.GitError as e:
        sys.exit(str(e))


def cmd_gototree(args, root):
    run_worktree_tool(worktree.gototree, args.spec, cwd=args.dir or ".")


def cmd_gotoremote(args, root):
    target = args.worktree_path or (True if args.worktree else None)
    run_worktree_tool(worktree.gotoremote, args.spec, worktree=target, cwd=args.dir or ".")


def cmd_render(args, root):
    render_review.render(locate(args.pr, root)[0], template=args.template, to_stdout=args.stdout)


def cmd_share(args, root):
    share_checks.share(locate(args.pr, root)[0], create=args.create)


def cmd_post(args, root):
    post_review.post(locate(args.pr, root)[0], do_post=args.post, event=args.event,
                     allow_moved_head=args.allow_moved_head, fold_invalid=args.fold_invalid)


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="reviews root (default: $STAN_REVIEWS_ROOT or "
                                       f"{DEFAULT_ROOT})")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("init", parents=[common], help="Step 0: directory, context, skeletons")
    p.add_argument("pr")
    p.add_argument("--allow-closed", action="store_true",
                   help="review a closed or merged PR (only after the user said so)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("context", parents=[common], help="write context.md again")
    p.add_argument("pr")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("worktree", parents=[common], help="Step 2: make the PR's worktree")
    p.add_argument("pr")
    p.add_argument("--detached", action="store_true",
                   help="make <clone>/.worktree/pr-<N> at the PR head, detached from any branch")
    p.add_argument("--clone", help="the local clone, for a repository not in the known list")
    p.set_defaults(func=cmd_worktree)

    p = sub.add_parser("cleanup", parents=[common],
                       help="remove the worktrees this review created")
    p.add_argument("pr")
    p.add_argument("--force", action="store_true",
                   help="remove them even with uncommitted or untracked changes")
    p.set_defaults(func=cmd_cleanup)

    p = sub.add_parser("gototree", help="make or reuse a worktree of a branch")
    p.add_argument("-d", "--dir", help="run in this repository (default: the current directory)")
    p.add_argument("spec", help="<branch>, <user>:<branch>, or https://host/<user>/<repo>/tree/<branch>")
    p.set_defaults(func=cmd_gototree)

    p = sub.add_parser("gotoremote", help="add a fork as a remote and check out its branch")
    p.add_argument("-w", "--worktree", action="store_true",
                   help="make a worktree next to the main clone instead of checking out in place")
    p.add_argument("--worktree-path", metavar="PATH",
                   help="make the worktree at PATH (also accepted as --worktree=PATH)")
    p.add_argument("-d", "--dir", help="run in this repository (default: the current directory)")
    p.add_argument("spec", nargs="+",
                   help="<user>:<branch>, <user> <branch>, or https://host/<user>/<repo>/tree/<branch>")
    p.set_defaults(func=cmd_gotoremote)

    p = sub.add_parser("defer", parents=[common], help="defer a PR stacked on another one")
    p.add_argument("pr")
    p.add_argument("--on", required=True, help='the PR it waits for, e.g. "math#3438"')
    p.add_argument("--because", required=True,
                   help="why: the base branch, the ancestry, or the quoted sentence")
    p.set_defaults(func=cmd_defer)

    p = sub.add_parser("render", parents=[common], help="Step 5c: check and render the review")
    p.add_argument("pr")
    p.add_argument("--template", help="default: review_template.md in the reviews root")
    p.add_argument("--stdout", action="store_true", help="print the review instead of writing")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("share", parents=[common], help="Step 6: upload gist/ as a secret gist")
    p.add_argument("pr")
    p.add_argument("--create", action="store_true", help="upload (default is a dry run)")
    p.set_defaults(func=cmd_share)

    p = sub.add_parser("post", parents=[common], help="Step 6: post the review")
    p.add_argument("pr")
    p.add_argument("--post", action="store_true",
                   help="really post (default is a dry run); only after the user said yes")
    p.add_argument("--event", default="COMMENT", choices=["COMMENT", "APPROVE", "REQUEST_CHANGES"])
    p.add_argument("--allow-moved-head", action="store_true")
    p.add_argument("--fold-invalid", action="store_true",
                   help="move comments that cannot be anchored into the review body")
    p.set_defaults(func=cmd_post)

    # --worktree=PATH (as gotoremote spells it) cannot share a name with the -w flag in
    # argparse without swallowing the branch spec, so map it to --worktree-path PATH.
    argv = []
    for a in sys.argv[1:]:
        argv += ["--worktree-path", a.split("=", 1)[1]] if a.startswith("--worktree=") else [a]
    args = ap.parse_args(argv)
    root = Path(getattr(args, "root", None) or os.environ.get("STAN_REVIEWS_ROOT")
                or DEFAULT_ROOT)
    args.func(args, root)


if __name__ == "__main__":
    main()
