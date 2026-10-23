# Numerics PRs: what to look for and how to verify

Numerics PRs change how a value or a gradient is computed so that it stays accurate
in some regime. The usual failure modes:

- the new form is right in the range the author tested and wrong just outside that
  range
- the value is fixed but the gradient is not, or the reverse
- one autodiff path is fixed and the others are not
- the new regime switch creates a seam

## Checklist

**Cancellation and range.**
- Differences of nearly equal quantities, such as `1 - p`, `lgamma(x + k) - lgamma(x)`,
  `digamma(x + d) - digamma(x)`, `log(1 - exp(a))`, and `a - b` with `a ≈ b`.
- Products and quotients of quantities that underflow or overflow separately
  although the ratio is fine, such as `pow(t, n) * pow(1 - t, m) / beta(...)`,
  `x / exp(logp)`, and `tgamma(a)` for `a > 171.6`.
- `exp` of an argument beyond ±708. `0 * inf`, `inf / inf`, and `inf - inf` give NaN.
- For each changed expression, ask at which inputs the terms stop being
  representable or stop having correct digits.

**Branches and thresholds.**
- Every new `if` on a magnitude is a seam. Is the threshold justified by an error
  bound or a measured switch point? Are the value and the derivative continuous
  across it, within the rounding of the two forms?
- Are both sides tested near the seam as well as far from it?

**Gradients.**
- Each branch needs its own correct derivative.
- Derivatives formed as a ratio (`dQ/da / Q`) need the same log-space care as the
  value.
- Autodiff through a rewritten expression can reintroduce the cancellation that the
  value avoided. Check `rev`, `fwd`, and the `mix` instantiation (`fvar<var>`)
  separately when they have separate code.
- Are the partials at ±inf boundaries 0 or NaN?

**Reference values in tests.**
- Where do the expected values come from, and with what precision?
- Two independent routes (for example two integral representations, or a series and
  a quadrature) agreeing to many digits is the gold standard. Values produced by the
  new code itself are circular.

**Probe past the claimed range.**
- Pick 3–6 inputs beyond the author's grid, such as deeper tails (log P < -708),
  larger shapes (1e10–1e18), tiny ones (1e-300), integer versus non-integer
  parameters, `n = 0`, `y` at the boundary, or `x → 1`. Evaluate the new formula in
  Python floats and in mpmath, and compare the results.
- A sketch of the new code path in Python is often enough to find the next failure
  region.

**Vectorization.** Check a scalar argument mixed with a vector argument, a vector
where one element is extreme or infinite, and the size-zero case.

**Cost.** An accuracy fix that costs speed on the common path should say how much.
Look for added `lgamma`/`digamma`/`exp`/`log` calls in hot loops.

## Verification snippets

Use the project venv. Save each script that produces a number quoted in the review in
`reviews/<repo>/<N>/gist/`, and write it so it can be shared (SKILL.md, Step 4.3).
Run each script with `-I`. This stops files in the current directory from shadowing
modules.

```bash
PY=/home/sbronder/open_source/stan/origin/.venv/bin/python
$PY -I reviews/math/3443/gist/ref_values.py
```

**mpmath reference value**, here for a log cdf deep in the tail:

```python
import mpmath as mp
mp.mp.dps = 50
def skew_normal_lcdf(y, xi, omega, alpha):
    z = (mp.mpf(y) - xi) / omega
    # CDF = Phi(z) - 2 T(z, alpha), with Owen's T done by quadrature
    T = mp.quad(lambda t: mp.exp(-z**2 * (1 + t**2) / 2) / (1 + t**2), [0, alpha]) / (2 * mp.pi)
    return mp.log(mp.ncdf(z) - 2 * T)
ref = skew_normal_lcdf(-1, 0, 1, 10)
test_value = -58.59  # copied from the test file
print(mp.nstr(ref, 20), "rel err", mp.nstr(abs((test_value - ref) / ref), 3))
```

Get a gradient reference with `mp.diff(f, x)` at high `dps`. It is reliable far
past where double-precision finite differences fail.

**Old versus new formula in IEEE double.** Python floats are C++ `double`, without
FMA contraction:

```python
import math
c1, c2, c3 = -1.0, 5.0, -5.551115123125783e-14   # inputs traced from the test
t = math.sqrt(c2*c2 - 2*c1*c3)
old = -(c2 - t) / c3                   # develop
q = c2 + math.copysign(t, c2)
new = -2*c1 / q                        # PR
print(old, new, "exact ~", -c1/c2)
```

**sympy identity** (an algebraic rewrite equals the original):

```python
import sympy as sp
n = 3
H = sp.Matrix(n, n, lambda i, j: sp.Symbol(f"h{min(i,j)}{max(i,j)}"))  # symmetric
s = sp.Matrix(sp.symbols(f"s0:{n}")); y = sp.Matrix(sp.symbols(f"y0:{n}"))
rho = 1 / (s.T * y)[0]
I = sp.eye(n)
orig = (I - rho * s * y.T) * H * (I - rho * y * s.T) + rho * s * s.T
u = H * y; c = rho**2 * (y.T * u)[0] + rho
new = H + (c * s - rho * u) * s.T - rho * s * u.T
print(sp.simplify(orig - new) == sp.zeros(n, n))
```

**Mathematica**, for special functions where mpmath is slow or of uncertain accuracy.
Load the module in the same shell call as the command. Piping `module load` loses
the environment.

```bash
module load mathematica && wolframscript -code 'N[Log[CDF[SkewNormalDistribution[0, 1, 10], -1]], 30]'
module load mathematica && wolframscript -code 'N[D[Log[BetaRegularized[x, a, b]], a] /. {x -> 9/10, a -> 50, b -> 50}, 30]'
```

Report each check in the summary with what was checked, the inputs, the reference
value, the precision of the reference, the PR's value (from the test or your Python
port), the error, and the script path.
