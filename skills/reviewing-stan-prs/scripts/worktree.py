"""Python ports of the gototree and gotoremote shell functions from the user's dotfiles.

Library for `review.py gototree` and `review.py gotoremote`. The logic follows the shell
functions step by step. The one difference: a Python process cannot change its caller's
directory, so instead of `cd`-ing into the worktree, each command prints the worktree's
absolute path as its only line on stdout. Progress messages and git's own output go to
stderr, so `WT=$(review.py gototree ...)` captures just the path.

gototree [-d <dir>] [<user>:]<branch>
  Make (or reuse) the worktree <main clone>/.worktree/<branch>. A plain branch name uses a
  local branch, else a remote-tracking branch, else fetches it from origin, else creates it
  from HEAD. <user>:<branch> or a https://host/<user>/<repo>/tree/<branch> URL goes through
  gotoremote with that same worktree path. It also adds ".worktree/" to the repository's
  info/exclude file.

gotoremote [-w | --worktree=<path>] [-d <dir>] <user>:<branch>   (or <user> <branch>, or a URL)
  Add <user>'s fork of the origin repository as a remote named <user>, fetch <branch>, and
  then either make a worktree (-w: next to the main clone as <repo>-<user>-<branch>, or at
  <path>) or, without -w, check the branch out in the current repository.
"""

import subprocess
import sys
from pathlib import Path

# The user's local clones, by repository name.
CLONES = {
    "math": "/home/sbronder/open_source/stan/origin/math",
    "stan": "/home/sbronder/open_source/stan/origin/stan",
    "cmdstan": "/home/sbronder/open_source/stan/origin/cmdstan",
    "stanc3": "/home/sbronder/open_source/stan/origin/stanc3",
    "docs": "/home/sbronder/open_source/stan/origin/docs",
    "cmdstanr": "/home/sbronder/open_source/stan/origin/cmdstanr",
}


class GitError(Exception):
    pass


def say(tool, msg):
    print(f"{tool}: {msg}", file=sys.stderr)


def git(cwd, *args, capture=True, check=True, quiet=False):
    """Run git in cwd. With capture, return its stdout; otherwise send it to stderr."""
    res = subprocess.run(["git", *args], cwd=cwd, text=True,
                         stdout=subprocess.PIPE if capture else sys.stderr,
                         stderr=subprocess.DEVNULL if quiet else (
                             subprocess.PIPE if capture else None))
    if check and res.returncode != 0:
        detail = (res.stderr or "").strip() if capture and not quiet else ""
        raise GitError(f"git {' '.join(args)} failed" + (f": {detail}" if detail else ""))
    return res.stdout if capture else res.returncode


def ok(cwd, *args):
    """True when the git command succeeds; its output is discarded."""
    return subprocess.run(["git", *args], cwd=cwd, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def require_repo(tool, cwd):
    if not ok(cwd, "rev-parse", "--is-inside-work-tree"):
        raise GitError(f"{tool}: not inside a Git repository")


def has_local_branch(cwd, branch):
    return ok(cwd, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")


def main_root(cwd):
    """The main clone of the repository that cwd belongs to (the first worktree git lists)."""
    return next(line[len("worktree "):] for line in
                git(cwd, "worktree", "list", "--porcelain").splitlines()
                if line.startswith("worktree "))


def gototree(spec, cwd="."):
    """Make or reuse <main clone>/.worktree/<branch> and return its absolute path."""
    tool = "gototree"
    cwd = str(Path(cwd).resolve())
    usage = "usage: gototree [-d <dir>] [<user>:]<branch>"
    if not spec:
        raise GitError(f"{tool}: {usage}")
    fork, branch = False, spec
    if spec.startswith(("http://", "https://", "ssh://")):
        fork = True
        trimmed = spec[:-1] if spec.endswith("/") else spec
        if "/tree/" not in trimmed:
            raise GitError(f"{tool}: cannot parse <user>/<repo>/tree/<branch> out of: {spec}")
        branch = trimmed.split("/tree/", 1)[1]
    elif ":" in spec:
        fork = True
        branch = spec.split(":", 1)[1]
    if not branch:
        raise GitError(f"{tool}: {usage}")

    require_repo(tool, cwd)
    wt_path = Path(main_root(cwd)) / ".worktree" / branch

    exclude = Path(git(cwd, "rev-parse", "--git-common-dir").strip())
    if not exclude.is_absolute():
        exclude = Path(cwd) / exclude
    exclude = exclude / "info" / "exclude"
    text = exclude.read_text() if exclude.exists() else ""
    if ".worktree/" not in text.splitlines():
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a") as f:
            f.write(("\n" if text and not text.endswith("\n") else "") + ".worktree/\n")

    if fork:
        return gotoremote([spec], worktree=str(wt_path), cwd=cwd)

    if wt_path.exists():
        say(tool, f"{wt_path} already exists, entering it")
    elif has_local_branch(cwd, branch):
        git(cwd, "worktree", "add", str(wt_path), branch, capture=False)
    else:
        remote_ref = next(iter(git(cwd, "for-each-ref", "--format=%(refname:short)",
                                   f"refs/remotes/*/{branch}").split()), "")
        if not remote_ref and "origin" in git(cwd, "remote").split() and ok(
                cwd, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}"):
            remote_ref = f"origin/{branch}"
        if remote_ref:
            git(cwd, "worktree", "add", "--track", "-b", branch, str(wt_path), remote_ref,
                capture=False)
        else:
            say(tool, f"no local or remote branch '{branch}', creating it from HEAD")
            git(cwd, "worktree", "add", "-b", branch, str(wt_path), capture=False)
    wt_path = wt_path.resolve()
    say(tool, f"worktree {wt_path} on '{branch}'")
    return str(wt_path)


def gotoremote(args, worktree=None, cwd="."):
    """Add <user>'s fork as a remote, fetch <branch>, and make a worktree or check it out.

    worktree is None (check out in place), True (worktree at the default path), or a path.
    Returns the absolute path of the worktree, or of the repository after a checkout.
    """
    tool = "gotoremote"
    cwd = str(Path(cwd).resolve())
    usage = "usage: gotoremote [-w] [-d <dir>] <user>:<branch>"
    spec = args[0] if args else ""
    if not spec:
        raise GitError(f"{tool}: {usage}")
    if spec.startswith(("http://", "https://", "ssh://")):
        rest = spec[:-1] if spec.endswith("/") else spec
        rest = rest.split("://", 1)[1]
        rest = rest.split("/", 1)[1] if "/" in rest else rest
        user = rest.split("/", 1)[0]
        branch = rest.split("/tree/", 1)[1] if "/tree/" in rest else rest
        if not user or branch == rest:
            raise GitError(f"{tool}: cannot parse <user>/<repo>/tree/<branch> out of: {spec}")
    elif ":" in spec:
        user, branch = spec.split(":", 1)
    else:
        user, branch = spec, (args[1] if len(args) > 1 else "")
    if not user or not branch:
        raise GitError(f"{tool}: usage: gotoremote <user>:<branch>")

    require_repo(tool, cwd)
    origin_url = git(cwd, "config", "--get", "remote.origin.url", check=False).strip()
    if not origin_url:
        remotes = git(cwd, "remote").split()
        if remotes:
            origin_url = git(cwd, "config", "--get", f"remote.{remotes[0]}.url",
                             check=False).strip()
    if not origin_url:
        raise GitError(f"{tool}: no remotes configured, cannot infer the repository URL")
    base = origin_url[:-1] if origin_url.endswith("/") else origin_url
    base = base[:-len(".git")] if base.endswith(".git") else base
    repo = base.rsplit("/", 1)[-1]
    rest = base.rsplit("/", 1)[0] if "/" in base else base
    if not repo or rest == base:
        raise GitError(f"{tool}: cannot infer <owner>/<repo> from origin URL: {origin_url}")
    # scp-style git@host:owner keeps "git@host:"; https://host/owner keeps "https://host/".
    proto = rest.split(":", 1)[0] + ":" if "/" not in rest else rest.rsplit("/", 1)[0] + "/"
    new_url = f"{proto}{user}/{repo}.git"

    remote_url = git(cwd, "config", "--get", f"remote.{user}.url", check=False).strip()
    if remote_url:
        if remote_url.removesuffix(".git") != new_url.removesuffix(".git"):
            say(tool, f"remote '{user}' already points at {remote_url} (leaving as-is)")
    else:
        git(cwd, "remote", "add", user, new_url)
        remote_url = new_url
        say(tool, f"added remote {user} -> {new_url}")
    git(cwd, "fetch", user, f"+refs/heads/{branch}:refs/remotes/{user}/{branch}", capture=False)

    if worktree is not None:
        if worktree is True:
            wt_root = Path(git(cwd, "rev-parse", "--show-toplevel").strip())
            wt_path = wt_root.parent / f"{repo}-{user}-{branch.replace('/', '-')}"
        else:
            wt_path = Path(cwd) / worktree
        if wt_path.exists():
            say(tool, f"{wt_path} already exists, entering it without touching it")
        elif has_local_branch(cwd, branch):
            git(cwd, "worktree", "add", str(wt_path), branch, capture=False)
        else:
            git(cwd, "worktree", "add", "--track", "-b", branch, str(wt_path),
                f"{user}/{branch}", capture=False)
        wt_path = wt_path.resolve()
        say(tool, f"worktree {wt_path} on '{branch}' from {user} ({remote_url})")
        return str(wt_path)

    if has_local_branch(cwd, branch):
        git(cwd, "checkout", branch, capture=False)
        upstream = git(cwd, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}",
                       check=False).strip()
        if upstream == f"{user}/{branch}":
            if git(cwd, "merge", "--ff-only", f"{user}/{branch}", capture=False, check=False):
                raise GitError(f"{tool}: local '{branch}' has diverged from {user}/{branch}; "
                               "left untouched")
        else:
            raise GitError(f"{tool}: local branch '{branch}' already exists (upstream: "
                           f"{upstream or 'none'})\n{tool}: leaving it untouched; to take "
                           f"theirs: git reset --hard {user}/{branch}")
    else:
        git(cwd, "checkout", "-b", branch, "--track", f"{user}/{branch}", capture=False)
    say(tool, f"on '{branch}' from {user} ({remote_url})")
    return git(cwd, "rev-parse", "--show-toplevel").strip()
