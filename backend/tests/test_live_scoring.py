"""Live extraction accuracy wiring (#7) + FastAPI pipeline routes (#14)."""

from core.pipeline.scoring import MatchItem, match_items_from_json_objects, score

ENVELOPE = [
    {
        "economy": "Singapore",
        "law_name": "Personal Data Protection Act 2012",
        "provisions": [
            {"indicator_id": "P6-I1", "source_url": "https://sso.agc.gov.sg/Act/PDPA2012"},
            {"indicator_id": "6.2", "source_url": ""},  # dotted form -> pillar 6
        ],
    }
]


def test_envelope_converts_to_match_items_with_pillar():
    items = match_items_from_json_objects(ENVELOPE)
    assert len(items) == 2
    assert items[0].country == "Singapore"
    assert items[0].pillar_id == 6
    assert items[0].indicator_id == "P6-I1"
    assert items[1].pillar_id == 6  # parsed from "6.2"


def test_score_live_predictions_against_gold_tp_fp_fn():
    gold = [
        MatchItem("Singapore", 6, "P6-I1", "Personal Data Protection Act 2012",
                  ("https://sso.agc.gov.sg/Act/PDPA2012",)),
        MatchItem("Singapore", 7, "P7-I1", "Some Other Act", ("https://x/other",)),  # never predicted -> FN
    ]
    preds = match_items_from_json_objects(ENVELOPE)  # P6-I1 matches gold; 6.2 does not
    report = score(preds, gold)
    assert report.true_positives == 1
    assert report.false_positives == 1   # the 6.2 row matches no gold
    assert report.false_negatives == 1   # the P7 gold row missed
    assert 0.0 < report.f1 < 1.0
    assert report.per_pillar[6].true_positives == 1


def test_empty_predictions_score_zero():
    report = score(match_items_from_json_objects([]), [
        MatchItem("Singapore", 6, "P6-I1", "PDPA", ("https://x",))
    ])
    assert report.true_positives == 0
    assert report.recall == 0.0


# ---- FastAPI routes (#14) ----

def _client():
    from fastapi.testclient import TestClient
    import app.main as m
    return TestClient(m.app)


def test_route_economies_lists_gold_countries():
    r = _client().get("/economies")
    assert r.status_code == 200
    assert "Singapore" in r.json()


def test_route_indicators_filtered_by_pillar():
    r = _client().get("/indicators?pillar=6")
    assert r.status_code == 200
    assert all(code.startswith("P6-") for code in r.json())


def test_route_score_round_trip():
    r = _client().post("/score", json=ENVELOPE)
    assert r.status_code == 200
    body = r.json()
    assert set(["true_positives", "false_positives", "false_negatives", "precision",
                "recall", "f1", "per_pillar"]) <= set(body)
    assert isinstance(body["f1"], (int, float))
