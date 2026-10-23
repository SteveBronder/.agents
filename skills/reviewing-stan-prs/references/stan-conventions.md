# Stan Math and Stan C++ conventions to check

Most of these are things CI does not catch, or catches late. Flag a deviation only
when it is in the changed code.

## Layout and layering (Stan Math)

- `stan/math/{prim,rev,fwd,mix,opencl}/{core,err,fun,functor,meta,prob,constraint}/`.
  `prim` must not include `rev` or `fwd` headers. `make test-math-dependencies`
  enforces this in CI, but a review can catch it from the includes.
- A new public header must be added to the matching umbrella header, for example
  `stan/math/prim/fun.hpp` or `prim/prob.hpp`. Internal helpers belong in
  `namespace internal`.
- Tests mirror the source layout under
  `test/unit/math/{prim,rev,fwd,mix,opencl}/...` and are named `<name>_test.cpp`.
  Don't add non-test `.cpp` files or `*_test.hpp` files under `test/unit/math/`.
  Reverse-mode tests use the `AgradRev` fixture (`test/unit/math/rev/util.hpp`) so
  the autodiff stack is cleaned between tests.
- C++17 at most (`make/compiler_flags`).

## Templates and autodiff idioms

- Overloads are constrained with `require_*` traits (`require_eigen_t`,
  `require_all_stan_scalar_t`, `require_vt_same`, ...). They do not name concrete
  types. Check that a relaxed `require_*` doesn't silently expose a new signature,
  for example matrix input to a function documented for vectors. That is a
  user-visible side effect.
- Distributions follow one pattern:
  - argument checks first (`check_finite`, `check_positive_finite`,
    `check_consistent_sizes`)
  - an early return for size zero
  - `include_summand<propto, ...>` to skip terms
  - `scalar_seq_view` / `VectorBuilder` for vectorization
  - partials through `make_partials_propagator`, returned with `ops_partials.build(logp)`

  A change that moves a constant inside a `propto`-skipped term can change the
  `propto=true` value. Check `full - propto` still equals the dropped constants.
- Reverse mode:
  - Use `arena_t<>` for anything a `reverse_pass_callback` captures.
  - Capture by value into arena. Never capture references to stack locals.
  - Use `make_callback_var`/`make_callback_vari` for custom gradients.
  - Use `value_of`/`.val()`/`.adj()` on arena matrices.
- Expressions:
  - Returning an Eigen expression that refers to a local is a dangling reference.
    Use `make_holder` or evaluate.
  - `to_ref` and `.eval()` evaluate. Calling them where the input is used once
    wastes an allocation. Not calling them where it is used many times recomputes
    the expression each time.
  - `.val()`/`.d()` of an `fvar` matrix is a strided view. Copy it once if it is
    used repeatedly.
- Constants (`NEGATIVE_INFTY`, `INFTY`, `NOT_A_NUMBER`, `EPSILON`, `LOG_EPSILON`,
  `LOG_TWO`, ...) come from `prim/fun/constants.hpp`. Stable building blocks
  already exist and should be reused rather than re-derived: `log1p`, `expm1`,
  `log1m`, `log1p_exp`, `log1m_exp`, `log_diff_exp`, `log_sum_exp`, `log_inv_logit`,
  `log1m_inv_logit`, `lgamma_stirling_diff`, `lbeta`, `log_inc_beta`, ... Search
  `prim/fun/` before accepting a new helper. A new helper is fine when it is
  genuinely new. It is better if it is reused.

## Documentation and errors

- Doxygen on every new or changed function: `@tparam` for each template parameter,
  `@param`, `@return`, and `@throw` naming the exception and condition.
- Errors use the `check_*` helpers or `throw_domain_error` with the function name.
  `std::domain_error` is for bad argument values, `std::invalid_argument` for
  inconsistent sizes.
- Silent fallbacks (catching and returning a default, clamping without a comment)
  are an anti-pattern in this repo. Ask why.

## Stan (stan-dev/stan)

- Source in `src/stan/...`, tests in `src/test/unit/...`.
- Services signatures (`stan::services::*`) are an API used by downstream projects
  such as CmdStan and RStan. A changed signature or a changed default needs a note
  and usually a coordinated PR.
- Changes to output (CSV columns, logger messages, return codes such as
  `error_codes::*` or `TERM_*`) are user-visible and belong in Side Effects.

## Static checks on the changed files only

From inside the worktree:

```bash
# formatting (the bots auto-format, so report only if something looks deliberately unformatted)
clang-format --dry-run -Werror <changed .hpp/.cpp files>

# cpplint with the repo's own filters (math: --root=stan; stan: --root=src)
python3 lib/cpplint_2.0.2/cpplint.py --output=vs7 --root=stan --extension=hpp,cpp \
  --filter=-runtime/indentation_namespace,-build/c++11,-readability/namespace,-legal/copyright,-whitespace/indent,-build/header_guard,-build/include_order,-build/include_what_you_use,-runtime/string,-build/namespaces \
  <changed files>
# in stan the script lives at lib/stan_math/lib/cpplint_2.0.2/cpplint.py
```

clang-tidy is optional and slow, since it parses the heavy templates. Use it only
when you suspect a specific issue it detects, such as a use-after-move or a
narrowing conversion. In math, run `module load llvm`, then
`make clang-tidy files=<test-name-glob>`. That runs over test `.cpp` files with
header filter `./stan/*`. The target only parses the code and does not build
anything.
