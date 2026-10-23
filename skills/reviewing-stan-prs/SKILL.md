---
name: reviewing-stan-prs
description: Investigative review of Stan ecosystem pull requests (stan-dev/math, stan-dev/stan, cmdstan, stanc3) covering numerics/accuracy fixes, code optimizations, and algorithm changes. It checks the description and benchmark tables, makes a worktree with gototree, checks that the tests prove the PR's claims (red/green), reviews the implementation, verifies math with sympy/mpmath/Mathematica, writes private notes and a rendered GitHub review to /home/sbronder/open_source/stan/origin/reviews/<repo>/<PR#>/, and then asks whether to post it as a GitHub review. Use this whenever the user pastes a github.com/stan-dev/.../pull/N link or asks to review, look over, vet, sanity-check or prepare a review of a Stan, Stan Math or CmdStan PR, even if they only give the link.
argument-hint: <github-pull-request-url>
---

# Reviewing Stan ecosystem pull requests

The argument is a GitHub pull request link: **$ARGUMENTS**

If it is empty or not a PR link, ask the user for the link before doing anything else.
Accept `https://github.com/stan-dev/<repo>/pull/<N>`, where `<repo>` is the repository name (such as `math` or `stan`) and `<N>` is the PR number.

You produce two documents: private notes the user can read and act on in a few minutes, and a review to post on the PR.
Each point you make should rest on something you checked, such as a line of code, a computed value, or a traced test input.

## Ground rules

- **Read-only verification.**
  Do not run `make`, `runTests.py`, or the test binaries.
- **Do not send anything to GitHub without an explicit yes** from the user in this conversation.
  Don't comment, approve, push, or edit the PR branch.
  Uploading the secret gist with your check code (Step 4) is part of posting.
- **Use the `code-review` skill.
  Do not use `code-review:code-review`.**
- **Pin the review to one commit.**
  `init` records the PR's head SHA as the reviewed commit.
  Review the code at that commit, and give every line number relative to it.
- **Write everything in the user's plain style.**

## Files

Each reviewed PR gets its own directory, named by the PR number: `/home/sbronder/open_source/stan/origin/reviews/<repo>/<N>/` (for example `reviews/math/3432/`).

| File | What |
|---|---|
| `overall_review.md` | The private notes (Step 5a) |
| `review.toml` | The GitHub review as data (Step 5b) |
| `github_review.md` | The GitHub review rendered from `review.toml`. This is the file that gets posted (Step 5c) |
| `context.md` | Everything about the PR that `review.py init` collects (Step 0) |
| `gist/` | Exactly what the gist will contain: the code behind every number you computed, its output, and a README.md. Uploaded in Step 6, right before posting |
| `checks/` | Other scratch work you keep but don't share |

Bundled with this skill (paths relative to this file):
- `scripts/review.py`: the command-line tool for the steps that touch files or GitHub.
  Run it as `python3 <skill-dir>/scripts/review.py <command> <pr>`, where `<skill-dir>` is the directory that holds this file and `<pr>` is the PR link, `math#3432`, or the directory `reviews/<repo>/<N>`.

## Step 0: Gather context and check whether the PR is stacked

```bash
python3 <skill-dir>/scripts/review.py init "<PR link>"
```

The first line `init` prints is the stack verdict, its conclusion from the stack analysis: `STACK: STOP`, `STACK: CHECK`, or `STACK: PROCEED`, explained below.
Then read the whole context file.

**Stacked PRs are not reviewed.**
If the PR you are reviewing depends on another unmerged PR, stop and exit.

- `STACK: STOP`: the PR's base branch is the branch of another open PR, or the PR's branch contains another open PR's head.
- `STACK: CHECK`: a sentence that mentions another open PR also says which one should merge first.
  Read the quoted sentences in the stack analysis and decide the direction (below, #M is the other PR):
  - **This PR depends on the other**: stop, and write the deferred note with `review.py defer <pr> --on <repo>#<M> --because "<the quoted sentence>"`.
    Examples: "based on #M", "depends on #M", "must be merged after #M", "should go after #M", "should go in after #M", "requires #M".
  - **The other PR depends on this one, or is only related**: proceed, and note it on the `Stack:` line in the header of `overall_review.md`.
  - **Still ambiguous**: ask the user.
- `STACK: PROCEED`: continue.
  Still skim the comments, because the author may declare a dependency in wording the stack analysis missed.

`init` refuses a closed or merged PR.
Ask the user, and if they want the review, run `init` again with `--allow-closed`.

**Classify the PR.**
It may be **numerics** (accuracy, stability, special functions, distributions), **code optimization** (same results, faster or less memory), or **algorithmic** (optimizers, samplers, Laplace, Pathfinder, PSIS, services).

## Step 1: Review the description

The checks below produce fact checks.
A fact check is an entry in the GitHub review that quotes one statement from the PR, such as a sentence of the description or a row of a table, and says whether the PR itself supports it.
It judges the claim from the PR's own evidence, such as its tests, scripts, tables, and comments, by reading and tracing them.
Checks you run yourself go in a separate section of the review (Step 5b).
A **claim** fact check is about speed, accuracy, or correctness.
A **description** fact check compares a statement of what the PR changes with the code at the reviewed commit.
When the statement needs work from the author, the fact check carries a **request**: what you ask the author to do, such as share the code behind a table.

- (a) Each table or figure is a **claim**.
  A claim fact check's status rates the code the author provided for rerunning the claim, as `Confirmed`, `Partly Confirmed`, or `Not Verified` (defined in Step 5b).
  For performance results, also check the sizes (small, medium, large), the scalar types (`double`, `var`, `fvar<double>`, `fvar<var>` for Stan Math), and that the table states what is measured, the ratio direction, the hardware, compiler, flags, and repetitions.
- (b) The defect on the base branch is a **claim**.
- (c) Each statement of what the PR changes is a **description** fact check, compared with the code at the reviewed commit.
  An unexplained file, a stale statement, or bundled independent changes go in its request.
- (d) Each `Fixes #N` is a **claim** that the PR fixes what #N reports, including the examples in the issue's comments (`gh issue view N -R stan-dev/<repo>`).

Write these fact checks into `review.toml` before going to Step 2.

## Step 2: Make the worktree

```bash
WT=$(python3 <skill-dir>/scripts/review.py worktree <pr>)
```

`worktree` makes a git worktree of the PR's branch inside the local clone of the repo, and prints only its path, so `WT` holds the path.
The local clones are:

| repo | local clone |
|---|---|
| stan-dev/math | `/home/sbronder/open_source/stan/origin/math` |
| stan-dev/stan | `/home/sbronder/open_source/stan/origin/stan` |
| stan-dev/cmdstan | `/home/sbronder/open_source/stan/origin/cmdstan` |
| stan-dev/stanc3 | `/home/sbronder/open_source/stan/origin/stanc3` |
| stan-dev/docs | `/home/sbronder/open_source/stan/origin/docs` |
| stan-dev/cmdstanr | `/home/sbronder/open_source/stan/origin/cmdstanr` |

For any other repo, ask the user where the clone is, and pass it with `--clone <path>`.

Then check what you have:

```bash
git -C "$WT" rev-parse HEAD        # must equal the reviewed commit in the context file
git -C "$WT" status --porcelain    # must be empty before you update anything
```

- **HEAD is behind and the tree is clean**: run `git -C "$WT" pull --ff-only`.
- **HEAD diverged, the tree is dirty, the checkout is wrong, or `worktree` failed because the branch is checked out in another worktree**: leave it alone.
  Make a detached worktree of the reviewed commit, `<clone>/.worktree/pr-<N>`, instead:

```bash
WT=$(python3 <skill-dir>/scripts/review.py worktree <pr> --detached)
```

Then get the base branch, where `<baseRefName>` is its name as shown in `context.md`:

```bash
git -C "$WT" fetch origin <baseRefName>
BASE=$(git -C "$WT" merge-base origin/<baseRefName> HEAD)
git -C "$WT" diff --stat "$BASE" HEAD
```

Use absolute paths from here on (`git -C "$WT"`, `$WT/...`).

## Step 3: Check the tests against the claims

1. **Claims ledger.**
   Turn the description into a list of concrete claims, and find the test that pins each one.
2. **Red/green.**
   Check red yourself.
   Trace the test inputs through `git show $BASE:<file>`, or port the old and new formula to Python floats and evaluate both.
3. **Right assertions.**
   Check that the reference values in the tests come from somewhere other than the code under test, and recompute a few with mpmath.
   Check that the tolerances are stated and portable, and that every relevant autodiff type is covered.
   `expect_ad`, the Stan Math test helper that compares autodiff types with each other, cannot detect accuracy bugs at extreme inputs.
   Check that edges and branch seams are tested (a branch seam is an input where the code switches from one formula to another), and that every change to an existing expected value is justified.

## Step 4: Review the implementation

Read the checklist for the PR's category (Step 0):

| Category | Reference |
|---|---|
| numerics | `references/numerics.md` |
| code optimization | `references/optimization.md` |
| algorithmic | `references/algorithmic.md` |
| any Stan Math C++ | `references/stan-conventions.md` |

1. **Run the generic bug pass**, a general bug search that does not depend on the PR's category.
   Invoke the built-in `code-review` skill from inside the worktree, with the PR number and an effort level, e.g. `<N> high`.
   Never add `--comment` or `--fix`.
   Keep a finding only after you have re-read the code at the reviewed commit and confirmed it.
2. **Run the domain pass**: review the change against the checklist for its category, from the table above.
   Read each changed function in full, including the parts outside the hunk.
   Most numerics and algorithm bugs are found in the interaction between the new code and the unchanged code around it, such as callers, other branches, and the `rev`/`fwd` siblings (the reverse-mode and forward-mode versions of the same function).
3. **Verify the math.**
   Wherever the PR rewrites a formula, claims an identity, or picks a threshold, check it:
   - sympy for algebraic identities, in `/home/sbronder/open_source/stan/origin/.venv`
   - mpmath for high-precision reference values, in the same venv
   - Mathematica: `module load mathematica && wolframscript -code '...'`

   Any script behind a benchmark or accuracy number in the review goes in `reviews/<repo>/<N>/gist/`, which is shared with the author as a gist when the review is posted.
   Name the dependencies at the top, and save the output next to the script (for example `ref_values.out`).
   Keep `gist/README.md` up to date.
   For each file it should describe the check, the run command, and the expected output.
   Each check you run this way also gets a `[[checks]]` entry in `review.toml` (Step 5b).
4. **Run the static checks on the changed files.**
   - `clang-format --dry-run -Werror <files>`, run in the worktree so `.clang-format` applies
   - cpplint: `make cpplint` in math and stan.
     It is a Python lint and does not compile anything.

   Report only problems the PR introduced.

A finding is a real defect, a claim that the code or tests do not support, a missing test for a stated claim, a regression risk, or a clear maintainability problem in the changed code.
The following are not findings:
- issues that exist on the base branch and that the PR doesn't touch (mention them separately only if they undercut the PR's claims)
- anything already raised in the PR conversation.
  Cite it, and say whether it was addressed.

Severity labels: **blocking** (wrong results, crash, broken API, or a claim that is false), **should-fix**, **suggestion**, **nit**, and **question** (you could not decide).

## Step 5: Write the private notes and the GitHub review

Before you write anything in this step, load the `plain-style` skill and read its full guide at `~/.claude/skills/plain-style/references/style_guide.md`, including the before-and-after examples.
Follow it in everything you write here, and do not hard-wrap lines.

`init` wrote skeletons of two files in `reviews/<repo>/<N>/`, with the PR's details filled in and a `<<...>>` placeholder for everything you write.

### 5a. Private notes

Fill in `/home/sbronder/open_source/stan/origin/reviews/<repo>/<N>/overall_review.md`, replacing every `<<...>>` placeholder.

### 5b. The GitHub review data

Fill in `/home/sbronder/open_source/stan/origin/reviews/<repo>/<N>/review.toml`.
`init` copied it from `templates/review.toml.j2`, which is also the schema.
`render` refuses to run while a `<<...>>` placeholder is left.

The fact checks are the most important part of the review:
- **Claims and Evidence** (`type = "claim"`): every claim the author makes about speed, accuracy, or correctness.
  Does it hold up, and did the author provide evidence in the form of code anyone can download and run to reproduce it?
- **Description vs Code** (`type = "description"`): does the description say what the code at the reviewed commit actually does?

Put whatever you ask the author about the description or about evidence in that fact check's `request`.
Do not put it in Issues, which are for problems in the code and the tests.

Rules:
- **Fact checks quote their source.**

Each fact check quotes one claim from the PR description, a comment or review, a linked issue, the code, or a commit message.
It will render the following sections which you need to fill in

```md
### FACT: {The Fact You are Checking}

Quote:

> {The Fact verbatim}

#### STATUS: {One of Confirmed, Partly Confirmed, or Not Verified}

#### Evidence:

{Show Evidence Here}

```
  `review.py render` checks every quote against GitHub itself and refuses any it cannot find.
- **Every claim needs evidence.**
  Rate only the author's evidence:
  - `Confirmed`: code anyone can download and run reproduces the claim, such as a test in the PR, a linked script or gist, or a benchmark file.
    Link it in `evidence_links`.
  - `Partly Confirmed`: some code, but not enough to rerun the claim as stated, for example a command with a placeholder, a script without inputs, or a harness for one table but not another.
  - `Not Verified`: numbers without code.

  Anything short of `Confirmed` needs a `request` that says what code would let someone verify the claim.
- **Cover the description and the claims ledger.**
  Every Step 1 check that has something to quote, and every claim in your Step 3 ledger, becomes a fact check.
  `not_checked` lists what you did not run (C++ build, devices, benchmark reruns).
- **Severity mapping for issues.** blocking and should-fix become `must_fix`, suggestion becomes `suggestion`, nit becomes `nit`, and a question becomes a `[[questions]]` entry.
- **Inline or body.**
  An issue with `inline = true` is posted as an inline comment on the lines in its `location`, and the review body (the main text of the GitHub review) links to it.
  Set `inline = true` only when those lines are in the PR diff at the reviewed commit.
  A point about an unchanged line keeps `inline = false`, and the review body links to the line with a permalink.
- When someone already raised an issue in the conversation, set `raised_by` so the review credits their comment instead of presenting the point as new.
- Address the author directly, in a collegial and specific tone.
  Keep private judgment out of the review.
- **Share your code.**
  Every number you computed (a benchmark, an mpmath or sympy check, a port of old and new code, a model) has to be rerunnable by the author.
  Write a `[[checks]]` entry for each check you ran, giving what you checked, what it showed, and the gist files it used (`our_code`).
  Don't write a `[gist]` table.

### 5c. Render

```bash
python3 <skill-dir>/scripts/review.py render <repo>#<N>
```

`render` also runs the mechanical part of the plain-style workflow, using the plain-style skill's scripts:
- it reflows `overall_review.md` and `gist/README.md` in place to one sentence per line, and writes `github_review.md` the same way
- it prints each checker warning, which you reread and change if the sentence breaks the rule

Fix everything it reports and run it again.
Fix an error in `github_review.md` in the matching field of `review.toml`.

Warnings (the PR is closed or merged, or its head moved) do not stop the render.
Pass them on to the user in Step 6.

### 5d. Edit the prose

The checker in `render` finds only the patterns a script can match.
The rest of the guide needs a reader, so have the `plain-style-editor` agent copy-edit what you wrote for each file. Use the agent in edit mode.


1. `overall_review.md`, in edit mode.
   Keep as written: numbers, SHAs, `path:line` references, code and identifiers, severity labels, the stack verdict, and anything quoted from the PR.
2. `github_review.md`, in review mode, because `render` overwrites it.
   Keep every `>` block quote as written, since each one is quoted word for word from the PR and `render` checks it against GitHub.
   Also keep code and identifiers, links, numbers, the headings, and the labels (FACT, Quote, STATUS, Evidence, Request, the result values, Must Fix, Suggestions, and Nit).
   Apply the changes it suggests to the matching fields of `review.toml`, never to the `text` of a quote.
3. `gist/README.md`, in edit mode, if `gist/` holds code.
   Keep as written: file names, commands, versions, and expected output.

Then run `review.py render` again, which reflows and checks the three files a second time, as the plain-style workflow asks after a reread.

## Step 6: Ask before posting

Tell the user where the review directory is, give the verdict and the top issues in a few lines, then ask (AskUserQuestion) whether to post.
Offer three options:
- post `github_review.md`, including the inline comments, as a COMMENT review, one that neither approves nor requests changes
- wait while they edit `review.toml`, then render again
- don't post

If they say post, first upload `gist/` (`share` says when there is nothing to share), then render again so the real link replaces the placeholder, then post:

```bash
python3 <skill-dir>/scripts/review.py share <repo>#<N> --create   # upload gist/
python3 <skill-dir>/scripts/review.py render <repo>#<N>           # link the gist
python3 <skill-dir>/scripts/review.py post <repo>#<N>             # dry run
python3 <skill-dir>/scripts/review.py post <repo>#<N> --post      # after a clean dry run
```

The dry run reports anchors that are not in the diff.
Fix them, or pass `--fold-invalid` to move them into the body as permalinks.
Posting is refused if the PR head moved past the reviewed commit.
In that case, tell the user and check whether the new commits change your findings before you pass `--allow-moved-head`.
The event is always `COMMENT` unless the user explicitly asks to approve or request changes.
Report the posted review's URL.

The worktree stays after the review, for follow-up questions and later commits.
When the user no longer needs it, `review.py cleanup <pr>` removes the worktrees this review created.

## Reviewing several PRs

To review several PRs, start one `stan-pr-reviewer` agent per PR, at most 3 at a time, and give each only the PR link.
Then do Step 6 with the user for each PR you reviewed.
