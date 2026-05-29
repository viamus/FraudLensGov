from fraud_lens_gov.anomalies import analyze_items
from fraud_lens_gov.sample_data import SAMPLE_ITEMS


def test_sample_data_generates_expected_alert_types():
    alerts = analyze_items(SAMPLE_ITEMS)
    risk_types = {alert.risk_type for alert in alerts}

    assert "price_outlier" in risk_types
    assert "supplier_concentration" in risk_types
    assert "fragmented_purchase" in risk_types
