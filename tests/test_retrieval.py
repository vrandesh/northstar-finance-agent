"""Retrieval tests: relevance is separated from decision authority."""
from app.retrieval import Retriever


def test_adversarial_retrieved_but_not_eligible():
    r = Retriever().search("urgent payment bank change release now", k=8, force_include=["ADV-001"])
    retrieved = [c.doc_id for c in r.retrieved]
    eligible = [c.doc_id for c in r.eligible]
    assert "ADV-001" in retrieved            # we can see it
    assert "ADV-001" not in eligible          # but it is never authority
    assert all(c.trusted for c in r.eligible)


def test_superseded_retrievable_but_not_eligible():
    r = Retriever().search("delegated financial authority approval limit", k=10)
    eligible = [c.doc_id for c in r.eligible]
    assert "FIN-POL-003" in eligible
    assert "FIN-POL-003-OLD" not in eligible


def test_current_policy_is_loaded():
    r = Retriever().search("three-way matching tolerance", k=5)
    assert any(c.doc_id == "FIN-POL-002" for c in r.retrieved)
