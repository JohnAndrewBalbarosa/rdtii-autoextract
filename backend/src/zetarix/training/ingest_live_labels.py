"""Backward-compatible shim — use ``zetarix.pretrain.labeling.ingest``."""

from zetarix.pretrain.labeling.ingest import *  # noqa: F403

if __name__ == "__main__":
    from zetarix.pretrain.labeling import ingest

    ingest.main()
