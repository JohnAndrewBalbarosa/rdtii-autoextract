"""Backward-compatible shim — use ``zetarix.pretrain.train.finetune``."""

from zetarix.pretrain.train import finetune as _finetune

globals().update({k: v for k, v in vars(_finetune).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_finetune.main())
