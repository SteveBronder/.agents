# Algorithmic PRs (optimizers, samplers, Laplace, Pathfinder, PSIS, services)

Algorithm changes rarely break the author's test models. Failures show up on problems
that were not tested. When the reviewers of these PRs found defects, they found them
with adversarial or randomized problem families. A robustness fix can turn one failure
mode into a worse one, for example a reported failure into a silently wrong optimum.

## Checklist

**Correctness against the source.**
- Is the method or condition cited (paper, equation, standard such as the strong
  Wolfe conditions or Moré–Thuente)? Does the code implement exactly that?
- Check sign conventions, which iterate a condition uses (the current trial step
  versus the initial one), off-by-one in iteration counts, and the units of
  tolerances (relative or absolute).
- Do invariants such as symmetry and positive definiteness of a Hessian
  approximation, monotone decrease, and a valid bracket still hold after the change?

**Behavior users see.**
- What changes at CmdStan defaults versus at tight tolerances?
- Which return codes and messages change (`TERM_*`, `error_codes`, logger text)?
- Does a previously successful run now end in an error?
- Changed iterates or draws for a fixed seed are a side effect. If the PR's Side
  Effects section does not mention them, ask for it in a description fact check.

**Evaluation of the claim.**
- How many models, seeds, and settings? Is the harness shared?
- Are outcome transitions counted as well as averages? For each, count:
  - success → failure
  - failure → success
  - failure → wrong answer reported as success

  The last one is the worst case. Averages do not show it.
- Ask for (or sketch) adversarial families when the change affects step sizes, line
  searches, or convergence tests. Examples include stiff or badly scaled problems
  (two-scale, condition number 1e8–1e24), kinks and non-smooth points, ascent
  directions, a tiny or huge initial gradient, and flat plateaus.

**Tests.**
- Do the tests pin the behavior (iterates, final point, evaluation counts, return
  code), or only that the code runs?
- Matrix-valued outputs (Hessians, inverse Hessians) need multi-dimensional tests.
  A 1-D test cannot detect off-diagonal or symmetrization bugs.
- A test that "does not compile on develop" only proves that an API was added. It
  does not show that the behavior is right.

**Interaction with other PRs.** Sibling PRs often touch the same functions, such as
the BFGS line search and `WolfLSZoom`. Check the PRs referenced in the context file
for overlaps. Also check whether this PR's behavior assumes or conflicts with the
behavior of those PRs. Note merge-order concerns. If this PR depends on an unmerged
one, Step 0 should already have stopped the review.

**Statistical methods (PSIS, Pathfinder, Laplace).**
- Compare with the reference implementation the PR names, for example the
  `posterior` or `loo` R packages.
- Check NaN handling. NaN passes many tests silently. For example, `!isinf(k)` is
  true for NaN, and `select(x < 0, x, 0)` maps NaN to 0.
- A fix that turns a NaN into a finite value can expose a wrong value downstream.
  Ask what the samplers or optimizers now do with the finite value.

## Verifying without running C++

- Port the changed decision logic (a line search step, a convergence test, a root
  formula) to a small Python script. Run it on the PR's own test inputs and on 2–3
  adversarial inputs, with the old and the new logic side by side.
- Check identities and derivations in the description with sympy.
- Report what you found as counts or concrete trajectories. Keep the script in
  `reviews/<repo>/<N>/gist/` for the review to share.
