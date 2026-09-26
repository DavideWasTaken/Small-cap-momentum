from smallcap_bt.config import load_config


def test_v2_candidate_is_stricter_and_cost_stressed() -> None:
    cfg = load_config("configs/strategy_v2_candidate.yaml")

    assert cfg.strategy.resistance_tolerance_pct == 0.02
    assert cfg.strategy.resistance_top_quantile == 0.75
    assert cfg.risk.stop_mode == "fixed"
    assert cfg.risk.fixed_stop_pct == 0.05
    assert cfg.risk.target_pcts == [0.12]
    assert cfg.risk.exit_variants == ["target_12"]
    assert 2 * cfg.risk.slippage_bps_per_side == 100
