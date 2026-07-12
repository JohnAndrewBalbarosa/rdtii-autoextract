"""Backward-compatible shim — use ``zetarix.pretrain.dataset.build``."""

from zetarix.pretrain.dataset import build as _build

globals().update({k: v for k, v in vars(_build).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_build.main())
