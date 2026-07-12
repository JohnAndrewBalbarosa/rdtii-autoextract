"""Backward-compatible shim — use ``zetarix.pretrain.labeling.seed``."""

from zetarix.pretrain.labeling.seed import *  # noqa: F403

if __name__ == "__main__":
    from zetarix.pretrain.labeling import seed

    seed.main()
