from adapters.botting.l6_presentation.dom_cleaner import DomCleaner


def test_extract_sections_strips_boilerplate_and_keeps_legal_content():
    html = """
    <html><body>
      <nav>JUNK NAV</nav>
      <main id="content">
        <h1 id="s26">Section 26</h1>
        <p>An organisation shall not transfer personal data overseas.</p>
      </main>
      <footer>JUNK FOOTER</footer>
    </body></html>
    """

    sections = DomCleaner().extract_sections(html, {"content_area": "#content"})

    assert len(sections) == 1
    assert sections[0].heading == "Section 26"
    assert sections[0].anchor == "s26"
    assert "transfer personal data" in sections[0].text
    assert "JUNK" not in sections[0].text


def test_extract_sections_uses_nearest_ancestor_anchor():
    html = """
    <article>
      <section id="part-iv">
        <h2>Part IV</h2>
        <p>Rules about overseas transfer.</p>
      </section>
    </article>
    """

    sections = DomCleaner().extract_sections(html, {"content_area": "article"})

    assert sections[0].anchor == "part-iv"


def test_extract_sections_prefers_descendant_provision_anchor():
    html = """
    <div id="legisContent">
      <div class="prov1">
        <table><tr><td id="pr26-">Transfer of personal data outside Singapore</td></tr></table>
        26. —(1) An organisation must not transfer personal data overseas.
      </div>
    </div>
    """

    sections = DomCleaner().extract_sections(
        html,
        {"content_area": "#legisContent", "sections": ".prov1"},
    )

    assert sections[0].anchor == "pr26-"


def test_extract_sections_tracks_nested_heading_path():
    html = """
    <main>
      <h2>Part IV</h2>
      <p>General rules.</p>
      <h3 id="s26">Section 26</h3>
      <p>An organisation shall not transfer personal data overseas.</p>
    </main>
    """

    sections = DomCleaner().extract_sections(html, {"content_area": "main"})

    assert sections[1].path == ("Part IV", "Section 26")
    assert sections[1].anchor == "s26"


def test_clean_html_regression_with_content_area():
    html = """
    <body>
      <aside>JUNK</aside>
      <main id="content">
        <h1>Law Title</h1>
        <p>Legal body.</p>
      </main>
    </body>
    """

    cleaned = DomCleaner().clean_html(html, {"content_area": "#content"})

    assert cleaned == "Law Title\nLegal body."
