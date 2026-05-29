from fraud_lens_gov.item_categorization import categorize_item
from fraud_lens_gov.sample_data import SAMPLE_ITEMS


def test_item_categorization_keeps_auditable_rag_contract():
    notebook = next(item for item in SAMPLE_ITEMS if "NOTEBOOK" in item.item_description)

    suggestion = categorize_item(notebook)

    assert suggestion.category == "Tecnologia da informacao"
    assert suggestion.confidence > 0.5
    assert suggestion.method == "lexical_rules_v1"
    assert "tokens" in suggestion.evidence
    assert "rag_ready" in suggestion.evidence
