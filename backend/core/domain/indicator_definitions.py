"""RDTII indicator tag-definitions + the controlled concept vocabulary.

The single source of truth shared by the section tagger and the tag-match extractor
(see ``adapters/extraction/section_tagger.py`` and
``adapters/extraction/tagmatch_provision_extractor.py``). Framework-agnostic, no I/O.

Two tables:

* ``CONCEPT_VOCAB`` maps each **concept tag** to the lower-cased trigger phrases that, when
  present in a section's text, mark that section with the tag. This is the deterministic,
  model-free tagging vocabulary (no embeddings, no LLM).
* ``INDICATOR_TAGS`` maps each canonical RDTII indicator (``P6-I1`` ... ``P7-I5``) to the
  **set of concept tags that define it**. An indicator applies to a section only when all of
  its defining tags are present in the section's tags — i.e. the indicator tag-set is a
  *subset* of the section tag-set. This is exactly the ``SetTrieIndex.query_subsets`` model.

Design note (precision): every Pillar-6 indicator requires the ``cross-border`` tag in
addition to its mechanism tag. That co-requirement is what stops a bare "transfer" in a
non-cross-border clause from firing P6 — it directly addresses the keyword extractor's
semantics-blind weakness. The definitions seed from the ``Indicator Reference`` sheet of
``docs/OUTPUT_TEMPLATE_31MAY.xlsx`` and cover all 10 mandatory indicators.
"""

from __future__ import annotations

# --- Controlled concept vocabulary: tag -> trigger phrases (lower-cased substrings) -------
#
# Detection is a case-insensitive substring scan (see section_tagger.detect_concept_tags).
# Phrases are deliberately specific to keep precision high; add synonyms here, never in the
# extractor, so tagging stays consistent across the pipeline.
CONCEPT_VOCAB: dict[str, tuple[str, ...]] = {
    "cross-border": (
        "cross-border", "cross border", "outside singapore", "outside australia",
        "outside malaysia", "outside the country", "another country", "third country",
        "overseas", "abroad", "beyond the territory", "to a country or territory outside",
    ),
    "restriction": (
        "shall not transfer", "must not transfer", "may not transfer", "prohibited",
        "shall not be transferred", "restrict", "is prohibited", "shall not disclose",
    ),
    "adequacy": (
        "adequate level", "adequacy", "comparable protection", "deemed adequate",
        "equivalent protection", "adequate protection",
    ),
    "contractual-safeguards": (
        "standard contractual clauses", "binding corporate rules", "contractual clauses",
        "model clauses", "contractual safeguards", "legally binding instrument",
    ),
    "consent": ("consent", "with the agreement of the individual"),
    "other-exception": (
        "vital interest", "public interest", "legitimate interest",
        "necessary for the performance", "necessary for the conclusion",
    ),
    "legal-basis": (
        "lawful basis", "legal basis", "grounds for processing", "basis for processing",
        "consent of the individual", "shall not collect", "before collecting",
    ),
    "purpose-limitation": (
        "purpose for which", "compatible purpose", "purpose limitation",
        "only for the purpose", "specified purpose", "purposes that a reasonable person",
    ),
    "data-subject-rights": (
        "right to access", "right to correct", "right to correction", "right to erasure",
        "right to be informed", "access and correction", "data subject", "rectification",
    ),
    "breach-notification": (
        "data breach", "notifiable data breach", "notify the commissioner", "breach notification",
        "notify the affected", "must notify",
    ),
    "enforcement": (
        "penalty", "financial penalty", "offence", "fine not exceeding", "commissioner",
        "supervisory authority", "enforcement", "guilty of an offence",
    ),
    # Broad context tags — not indicator-defining on their own, but useful for clustering.
    "personal-data": ("personal data", "personal information"),
    "processing": ("processing", "process personal data", "use or disclosure"),
}


# --- Indicator definitions: canonical code -> required concept tag-set --------------------
#
# An indicator matches a section iff INDICATOR_TAGS[code] is a subset of the section's tags.
INDICATOR_TAGS: dict[str, frozenset[str]] = {
    # Pillar 6 — Cross-border data flows (every entry co-requires `cross-border`).
    "P6-I1": frozenset({"cross-border", "restriction"}),          # general prohibition
    "P6-I2": frozenset({"cross-border", "adequacy"}),             # adequacy standard
    "P6-I3": frozenset({"cross-border", "contractual-safeguards"}),  # contractual safeguards
    "P6-I4": frozenset({"cross-border", "consent"}),             # consent exception
    "P6-I5": frozenset({"cross-border", "other-exception"}),     # other exceptions
    # Pillar 7 — Domestic data protection.
    "P7-I1": frozenset({"legal-basis"}),                         # legal basis for processing
    "P7-I2": frozenset({"purpose-limitation"}),                  # purpose limitation
    "P7-I3": frozenset({"data-subject-rights"}),                 # data subject rights
    "P7-I4": frozenset({"breach-notification"}),                 # breach notification
    "P7-I5": frozenset({"enforcement"}),                         # enforcement & penalties
}


def indicators_for_pillar(pillar: int) -> dict[str, frozenset[str]]:
    """Return the ``{canonical_code: tag_set}`` definitions for one pillar (6 or 7)."""
    prefix = f"P{pillar}-"
    return {code: tags for code, tags in INDICATOR_TAGS.items() if code.startswith(prefix)}
