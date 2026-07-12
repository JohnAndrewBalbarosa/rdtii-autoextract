"""Backward-compatible shim — use ``zetarix.pretrain.eval.submission``."""

from zetarix.pretrain.eval import submission as _submission

globals().update({k: v for k, v in vars(_submission).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_submission.main())
