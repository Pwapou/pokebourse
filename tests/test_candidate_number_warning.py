"""Avertissements lorsque le numéro proposé diffère de celui de l'annonce."""

from app.web import candidate_number_conflicts


def test_candidate_number_comparison_preserves_complete_identity() -> None:
    assert candidate_number_conflicts("173/165", "025")
    assert not candidate_number_conflicts("004/102", "4")
    assert not candidate_number_conflicts(None, "025")
    assert candidate_number_conflicts("TG05/TG30", "TG06")
