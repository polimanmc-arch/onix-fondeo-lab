from onix_fondeo.metrics import calculate_business_metrics
from onix_fondeo.models import Account


def test_business_metrics_handles_straight_to_funded_without_evaluation_cost():
    results = {
        "accounts": [Account(account_id=1, phase="FUNDED", pnl=500)],
        "trade_log": [],
        "payouts": [],
        "business_events": [],
    }
    config = {
        "evaluation": {
            "enabled": False,
            "evaluation_cost": None,
        },
        "funded": {},
        "simulation": {},
    }

    metrics = calculate_business_metrics(results, config)

    assert metrics["total_evaluations"] == 0
    assert metrics["pass_rate"] == 0
    assert metrics["payout_rate_on_evaluations"] == 0
    assert metrics["payout_rate_on_passed"] == 0
    assert metrics["total_evaluation_cost"] == 0
    assert metrics["expected_value_per_evaluation"] == 0
