# Step 3: Do the tests check what the PR claims?

The user chose **read-only verification**. Do not compile or run the C++ tests
(`make`, `runTests.py`, test binaries). Verify by reading code and history, and by
running small Python, sympy, mpmath, or Mathematica scripts. Those scripts do not
build the project.

## Build a claims ledger first

List every behavioral claim in the description, for example: "returns X at inputs
Y", "no longer NaN at large shapes", "fails on develop", "gradients within 1e-12",
"same iterates as develop", or "allocates nothing". For each claim, find the test
that pins it, in the form `file:TEST(Suite, Name)`. Claims without a test are
gaps. Measured improvements that are not pinned by any test are a common gap, for
example evaluation counts in optimizer PRs. Say whether a cheap test could pin the
claim.

## Red/green

TDD on a PR means the new test fails on the base code (red) and passes with the fix
(green). The cleanest history commits the failing test first, then the fix. In
practice:

- The context file reports the commit structure ("Red/green structure: YES/NO").
  Ignore merge commits and `[Jenkins] auto-formatting` commits.
- A test-first history is a plus. It is rare in these repos. Treat a mixed commit
  as a note and do not block on it. The main check is whether red is
  **demonstrated or demonstrable**. Accept, in order of strength:
  1. a test-only commit that precedes the fix
  2. a stated swap procedure ("with the develop headers swapped in, these N cases
     fail") with counts
  3. a bare claim "fails on develop"
- "Does not compile on develop" is weak red evidence. It shows that an API was
  added. It does not show that a behavior was fixed. Ask for a test that exercises
  the behavior through an existing API, or accept it explicitly and say why.
- If all substantive commits share one timestamp minute, the history was rewritten.
  The commit order then does not show how the work was done.

**Check red yourself by reading.** For each new test, run
`git show $BASE:<source file>`, trace the test's inputs through the old code path,
and decide whether it would fail. When the changed code is a small scalar formula,
port the old and the new formula to Python floats (IEEE double, like C++ `double`)
and evaluate both at the test inputs. This can often verify a "fails on develop"
claim. Note two caveats. C++ may contract `a*b+c` into an FMA, which Python never
does. Libm functions can also differ by an ulp.

## Are the tests testing the right thing?

- **The assertion matches the claim.** A test that checks only the diagonal cannot
  verify a symmetric Hessian. A 1-D test cannot detect off-diagonal or
  symmetrization bugs. A test at a point where develop already returns the right
  answer by luck (for example exactly 0 inside the tolerance) cannot detect the
  defect.
- **References are independent.** Expected values should come from high-precision
  computation (mpmath, Mathematica, exact rational or finite sums). They should not
  come from the new implementation's own output. Recompute 2–5 of them yourself.
  See `numerics.md` for snippets.
- **Tolerances are stated and portable.** Relative or absolute? Is 1e-12 safe across
  compilers and FMA? A test that depends on a rounding-noise value (for example a
  coefficient of about -5e-14 that FMA can change) is fragile. Ask for an exact case
  as well. `EXPECT_DOUBLE_EQ` on values computed through libm is fragile too.
- **Coverage of scalar types (Stan Math).** `test/unit/math/mix/` tests with
  `stan::test::expect_ad` cover `double`, `var`, `fvar<double>`, `fvar<var>`,
  `fvar<fvar<double>>`, and `fvar<fvar<var>>`. `expect_ad` compares against finite
  differences, so it **cannot** detect accuracy defects deep in tails, where the
  finite difference is itself wrong or NaN. Accuracy PRs need fixed high-precision
  references, usually in `rev/` tests, as well as `expect_ad` for wiring. A fix to
  one AD path (`rev`) should be checked for the other paths (`fwd`, `mix`). When a
  change affects a branch taken only for autodiff types (for example
  `T_partials_return`), a second-order test (`fvar<var>`, `stan::math::hessian`) is
  needed for functions used in Hessian-based code (Laplace, `grad_hess_log_prob`).
- **Edges.** Both sides of every new branch or threshold, and the seam itself
  (value and derivative continuity). Also ±inf, NaN, zero-size inputs, integer
  versus non-integer parameters, vectorized calls where only one element is
  extreme, and error throws (`EXPECT_THROW` with the right exception type).
- **Changed existing tests.** Every changed expected value or loosened tolerance in
  an existing test needs a justification in the description. Treat unexplained
  loosening as a red flag.
- **Generated distribution tests** (`test/prob/`) catch boundary throws that
  fixed-point tests miss. For distribution changes, check that the PR says they were
  run. You cannot run them here.
- **Algorithms (stan-dev/stan).** Do the tests pin trajectories (number of iterates,
  final point, return code), or only "it ran"? Are there tests for adversarial
  inputs (stiff, two-scale, kinks, ascent directions) as well as nice models?

## Output

Fill the "Claims vs tests" table of the summary. For each row, give the claim, the
test(s), red status (verified / plausible / unverified / not red), and a verdict.
List the gaps below the table in order of importance, and give each one a concrete
test you would ask for.
