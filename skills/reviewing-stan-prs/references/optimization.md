# Code-optimization PRs

The contract of an optimization PR is "same results, less time or memory". Review
both halves. Are the results really the same (or the same within a stated
rounding)? Is the speed-up real, general, and measured fairly?

## Same results

- **Equivalence.** Is the new computation mathematically identical to the old one?
  Check algebraic rewrites with sympy (see `numerics.md`). Check that the
  preconditions the rewrite relies on actually hold, for example symmetry of `H`,
  `s'y > 0`, or non-aliasing inputs.
- **Rounding.** The optimization changes rounding. In iterative algorithms a
  different last bit can change the trajectory. The iterates, the stopping point,
  and the return code can then differ. The PR should say how results differ
  (bitwise? within 1e-15? same iterations at defaults?) and show it on more than
  one problem. Changed results for a fixed seed are a side effect users will
  notice.
- **Special values.** Do NaN, inf, and size-zero inputs follow the same path as
  before?

## Faster, really

- Apply the table checks of SKILL.md, Step 1 (a). The sizes and scalar
  types matter most here:
  - small, medium, and large inputs
  - `double`, `var`, `fvar<double>`, `fvar<var>`, and varmat
    (`var_value<Eigen::Matrix>`) where it exists
  - value only versus value plus gradient

  A change that speeds up `var` can slow down `fvar` or the small-size case, for
  example through extra setup or a worse constant factor. Ask for the missing cells.
- A complexity claim ("O(n²) instead of O(n³)") should match the code. Count the
  matrix products, solves, and allocations per call.
- Was the comparison fair? Look for the following:
  - the same machine, compiler, and flags
  - interleaved runs
  - the same commit except for the change
  - the spread reported
- The stan-buildbot end-to-end table rarely exercises the changed code. It is a
  sanity check for regressions. Do not treat it as evidence of a speed-up.
- Stan Math's `benchmarks/benchmark.py` can generate a size-by-overload sweep for a
  function signature. It is a reasonable request when the PR does not provide a
  harness.

## Code patterns that cost or save time (Eigen and Stan Math)

- **Allocations in hot paths:** a temporary from `a * b` without `.noalias()`, a
  `.eval()` that isn't needed, a `std::vector` built per call, copying a `var`
  matrix where a `Map` or reference would do. Eigen's `rankUpdate` and some other
  APIs copy plain vector arguments, so pass a `Map`.
- **Expression templates:** repeated use of an unevaluated expression recomputes it,
  so `to_ref` it once. An expression returned past the lifetime of its operands
  dangles.
- **Symmetric structure:** `selfadjointView<Lower>()` with `rankUpdate` instead of a
  full outer product. The result is then exactly symmetric, which helps
  correctness too.
- **Reverse mode:** check `arena_t` versus heap, how much a `reverse_pass_callback`
  captures, and whether adjoints are accumulated vectorized or element by element.
  Reducing the number of `vari` nodes usually saves more time than reducing flops.
- **Strided views:** `.val()`/`.d()` on `fvar` matrices and `.adj()` on non-arena
  matrices are strided views. Copy them once if they are used repeatedly.
- **Branch-heavy scalar code in vectorized loops:** check that the common case stays
  branch-light.

## Findings to expect

- Missing benchmark cells for types, sizes, or gradient versus value.
- A speed-up shown on one machine only, without a harness.
- Results that differ beyond rounding without an explanation.
- An unexplained slowdown for one size or type.
- A simpler or faster formulation. When you have one, sketch it concretely, as a
  reviewer did by pushing the lower-triangle `rankUpdate` version of the BFGS update.
