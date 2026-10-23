"""Upload a review's gist/ folder as a secret GitHub gist, right before posting the review.

Library for `review.py share`. reviews/<repo>/<N>/gist/ holds exactly what the gist will
contain: the code behind every benchmark or accuracy number in the review, its output,
and a README.md. Before anything is uploaded, gist/ must pass the same checks
render_review.py runs on every render: flat, each file UTF-8 text under 1 MB with no
local file paths, e-mail addresses or credentials, and a README.md that mentions every
other file and has no skeleton placeholders left. The README is reflowed to one sentence
per line and must pass the plain-style checker.

The gist is secret: unlisted, but anyone with the link can read it, which is what the
review needs. share(create=True) creates the gist, or updates it if [gist].url is
already set, and writes the link, pinned to the new gist revision, into [gist].url in
review.toml (adding the table if needed). Render the review again afterwards so the
link replaces the GIST_NOT_UPLOADED_YET placeholder, then post it.
"""

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_review import (GIST_URL_RE, PR_URL_RE, Errors, gist_in_use,  # noqa: E402
                           read_gist_dir, reflow_in_place, style_check)


def gh_api(args, payload=None):
    res = subprocess.run(["gh", "api"] + args, capture_output=True, text=True,
                         input=json.dumps(payload) if payload is not None else None)
    if res.returncode != 0:
        sys.exit(f"gh api {' '.join(args)} failed:\n{res.stderr.strip()}")
    return json.loads(res.stdout)


def set_gist_url(toml_text, url):
    """Write url into the [gist] table, replacing an existing url line or adding the table."""
    lines = toml_text.splitlines(keepends=True)
    new = f'url = "{url}"\n'
    start = next((i for i, ln in enumerate(lines) if re.match(r"^\s*\[gist\]\s*(#.*)?$", ln)),
                 None)
    if start is None:
        return toml_text.rstrip("\n") + f"\n\n[gist]\n{new}"
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^\s*\[", lines[i])),
               len(lines))
    for i in range(start + 1, end):
        if re.match(r"^\s*url\s*=", lines[i]):
            lines[i] = new
            break
    else:
        lines.insert(start + 1, new)
    return "".join(lines)


def share(pr_dir, create=False):
    """Check gist/ and show what would go up; with create=True, upload it."""
    pr_dir = Path(pr_dir).resolve()
    toml_path, gist_dir = pr_dir / "review.toml", pr_dir / "gist"
    if not toml_path.exists():
        sys.exit(f"no review.toml in {pr_dir}")
    toml_text = toml_path.read_text()
    data = tomllib.loads(toml_text)
    pr = data.get("pr", {})
    m = PR_URL_RE.match(pr.get("url", ""))
    if not m:
        sys.exit("review.toml needs [pr].url to describe the gist")
    gist = data.get("gist", {})

    errors = Errors()
    if (gist_dir / "README.md").exists():
        reflow_in_place(gist_dir / "README.md")
    contents = read_gist_dir(gist_dir, errors) if gist_dir.is_dir() else {}
    if not gist_in_use(contents) and not errors:
        print(f"{gist_dir} holds no code besides the README; nothing to share")
        return
    warnings = []
    if "README.md" in contents:
        style_check("gist/README.md", contents["README.md"], errors, warnings)
    if errors:
        sys.exit("cannot share gist/:\n  " + "\n  ".join(errors))
    for w in warnings:
        print(f"style warning (reread it, and change it if it breaks the rule): {w}")
    description = gist.get("description") or (
        f"Checks from the review of {m.group(1)}/{m.group(2)}#{m.group(3)} at "
        f"{pr.get('commit', '')[:10]}: {pr['url']}")
    existing = GIST_URL_RE.match(gist.get("url", ""))

    print(f"{'update' if existing else 'create'} secret gist: {description}")
    for name, content in contents.items():
        print(f"  {name}: {len(content.encode())} bytes")
    if not create:
        print("dry run; pass --create to upload")
        return

    files = {name: {"content": content} for name, content in contents.items()}
    if existing:
        current = gh_api([f"gists/{existing.group(2)}"])
        for name in current.get("files", {}):
            if name not in files:
                files[name] = None
        out = gh_api(["-X", "PATCH", f"gists/{existing.group(2)}", "--input", "-"],
                     {"description": description, "files": files})
    else:
        out = gh_api(["-X", "POST", "gists", "--input", "-"],
                     {"description": description, "public": False, "files": files})
    url = f"{out['html_url']}/{out['history'][0]['version']}"
    toml_path.write_text(set_gist_url(toml_text, url))
    if tomllib.loads(toml_path.read_text()).get("gist", {}).get("url") != url:
        sys.exit(f"uploaded the gist, but could not record its url in {toml_path}: {url}")
    print(f"{'updated' if existing else 'created'} {url}\n"
          f"recorded it as [gist].url in {toml_path}; render the review again before posting")
