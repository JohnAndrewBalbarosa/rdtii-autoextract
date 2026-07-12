"""Backward-compatible shim — use ``zetarix.pretrain.eval.harness``."""

from zetarix.pretrain.eval import harness as _harness

globals().update({k: v for k, v in vars(_harness).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_harness.main())
