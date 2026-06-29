import pytest
from adapters.botting.scaffolds.scaffold_registry import ScaffoldRegistry
from adapters.botting.scaffolds.homeaffairs_gov_au import HomeAffairsScaffold
from adapters.botting.scaffolds.sso_agc_gov_sg import SSOAgcScaffold
from adapters.botting.scaffolds.pdpc_gov_sg import PDPCScaffold


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


def test_scaffold_registry_learn_and_save():
    """Verify that learn_and_save calls the LLM, updates scaffolds_db.json, and returns selectors."""
    import json
    import tempfile
    import os
    from unittest.mock import MagicMock
    
    # Mock LLM provider
    mock_llm = MagicMock()
    mock_llm.complete.return_value = {
        "content_area": ".test-content",
        "sections": "p, h1",
        "pdf_links": "a.pdf",
        "title": "h1",
        "keywords": ["test", "law"]
    }
    
    # Initialize registry
    registry = ScaffoldRegistry([])
    
    # Use a temporary file for the database during test to avoid changing scaffolds_db.json
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        temp_db_path = tmp.name
        
    registry._db_path = temp_db_path
    
    try:
        # Act
        selectors = registry.learn_and_save(
            url="https://example.com/law",
            html_content="<html><body><main>Test content</main></body></html>",
            llm=mock_llm
        )
        
        # Assert
        assert selectors is not None
        assert selectors["content_area"] == ".test-content"
        assert selectors["sections"] == "p, h1"
        
        # Verify it was saved to the temp database
        with open(temp_db_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "example.com" in data
            assert data["example.com"]["content_area"] == ".test-content"
            
        # Verify registry returns the newly learned scaffold
        scaffold = registry.get_scaffold_for_url("https://example.com/other-page")
        assert scaffold is not None
        assert scaffold.target_domain == "example.com"
        assert scaffold.get_custom_selectors() == selectors
    finally:
        if os.path.exists(temp_db_path):
            os.unlink(temp_db_path)


if __name__ == "__main__":
    pytest.main([__file__])
