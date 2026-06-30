from __future__ import annotations

import pytest

from run_adaptive_crawl import _parse_args


def test_cli_defaults_and_limits():
    args = _parse_args(["https://example.gov"])
    assert args.max_pages == 30
    assert args.max_depth == 2
    assert args.max_revisions == 2


@pytest.mark.parametrize(
    "arguments",
    [
        ["https://example.gov", "--max-pages", "0"],
        ["https://example.gov", "--max-depth", "-1"],
        ["https://example.gov", "--max-revisions", "3"],
    ],
)
def test_cli_rejects_unsafe_limits(arguments):
    with pytest.raises(SystemExit):
        _parse_args(arguments)
