import pytest
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry
from adapters.botting.scaffolds.homeaffairs_gov_au import HomeAffairsScaffold
from adapters.botting.scaffolds.sso_agc_gov_sg import SSOAgcScaffold
from adapters.botting.scaffolds.pdpc_gov_sg import PDPCScaffold
from adapters.botting.scaffolds.pdp_gov_my import PDPMyScaffold


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
    """Verify registry default instantiation registers all known scaffolds."""
    registry = ScaffoldRegistry()  # Use defaults

    homeaffairs = registry.get_scaffold_for_url("https://www.homeaffairs.gov.au/test")
    sso_agc = registry.get_scaffold_for_url("https://sso.agc.gov.sg/Act/CoA1967")
    pdpc = registry.get_scaffold_for_url("https://www.pdpc.gov.sg/test")
    pdp_my = registry.get_scaffold_for_url("https://www.pdp.gov.my/jpdpv2/laws")

    assert isinstance(homeaffairs, HomeAffairsScaffold)
    assert isinstance(sso_agc, SSOAgcScaffold)
    assert isinstance(pdpc, PDPCScaffold)
    assert isinstance(pdp_my, PDPMyScaffold)


def test_hardened_scaffolds_have_content_area_and_boilerplate_selectors():
    for scaffold in (HomeAffairsScaffold(), SSOAgcScaffold(), PDPCScaffold(), PDPMyScaffold()):
        selectors = scaffold.get_custom_selectors()
        assert selectors.get("content_area")
        assert scaffold.get_boilerplate_selectors()


def test_sso_base_act_url_fetches_official_pdf_endpoint():
    scaffold = SSOAgcScaffold()

    assert scaffold.get_fetch_url("https://sso.agc.gov.sg/Act/PDPA2012") == (
        "https://sso.agc.gov.sg/Act/PDPA2012?ViewType=Pdf"
    )
    assert scaffold.get_fetch_url("https://sso.agc.gov.sg/Act/PDPA2012?ProvIds=pr26-") == (
        "https://sso.agc.gov.sg/Act/PDPA2012?ProvIds=pr26-"
    )


def test_scaffold_registry_no_match():
    """Verify registry returns None for unregistered domains."""
    registry = ScaffoldRegistry([HomeAffairsScaffold()])
    url = "https://example.com/unknown"
    scaffold = registry.get_scaffold_for_url(url)

    assert scaffold is None


if __name__ == "__main__":
    pytest.main([__file__])
