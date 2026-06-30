import pytest
from zetarix.scaffolds.scaffold_registry import ScaffoldRegistry
from zetarix.scaffolds.homeaffairs_gov_au import HomeAffairsScaffold
from zetarix.scaffolds.sso_agc_gov_sg import SSOAgcScaffold
from zetarix.scaffolds.pdpc_gov_sg import PDPCScaffold


def test_scaffold_registry_matches_homeaffairs():
    """Verify registry returns HomeAffairsScaffold for homeaffairs.gov.au domains."""
    registry = ScaffoldRegistry([HomeAffairsScaffold()])
    url = "https://www.homeaffairs.gov.au/cyber-security-subsite/Pages/strategy.aspx"
    scaffold = registry.get_scaffold_for_url(url)

    assert scaffold is not None
    assert isinstance(scaffold, HomeAffairsScaffold)
    assert scaffold.target_domain == "homeaffairs.gov.au"


def test_scaffold_registry_matches_sso_agc():
    """Verify registry returns SSOAgcScaffold for sso.agc.gov.sg domains."""
    registry = ScaffoldRegistry([SSOAgcScaffold()])
    url = "https://sso.agc.gov.sg/Act/CoA1967"
    scaffold = registry.get_scaffold_for_url(url)

    assert scaffold is not None
    assert isinstance(scaffold, SSOAgcScaffold)
    assert scaffold.target_domain == "sso.agc.gov.sg"


def test_scaffold_registry_matches_pdpc():
    """Verify registry returns PDPCScaffold for pdpc.gov.sg domains."""
    registry = ScaffoldRegistry([PDPCScaffold()])
    url = "https://www.pdpc.gov.sg/Guidance-and-Resources/Framework/Personal-Data-Protection-Act"
    scaffold = registry.get_scaffold_for_url(url)

    assert scaffold is not None
    assert isinstance(scaffold, PDPCScaffold)
    assert scaffold.target_domain == "pdpc.gov.sg"


def test_scaffold_registry_default_instantiation():
    """Verify registry default instantiation registers all three scaffolds."""
    registry = ScaffoldRegistry()  # Use defaults

    homeaffairs = registry.get_scaffold_for_url("https://www.homeaffairs.gov.au/test")
    sso_agc = registry.get_scaffold_for_url("https://sso.agc.gov.sg/Act/CoA1967")
    pdpc = registry.get_scaffold_for_url("https://www.pdpc.gov.sg/test")

    assert isinstance(homeaffairs, HomeAffairsScaffold)
    assert isinstance(sso_agc, SSOAgcScaffold)
    assert isinstance(pdpc, PDPCScaffold)


def test_scaffold_registry_no_match():
    """Verify registry returns None for unregistered domains."""
    registry = ScaffoldRegistry([HomeAffairsScaffold()])
    url = "https://example.com/unknown"
    scaffold = registry.get_scaffold_for_url(url)

    assert scaffold is None


if __name__ == "__main__":
    pytest.main([__file__])
