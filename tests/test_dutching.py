import pytest
from dutching import (
    calculate_dutching_stakes,
    calculate_mixed_dutching,
    calculate_ai_mixed_stakes,
    dynamic_cashout_single,
    validate_selections
)

def test_dutching_standard_modes():
    sels = [{"selectionId": 1, "price": 2.0}, {"selectionId": 2, "price": 3.0}]
    
    res_back, prof_back, _ = calculate_dutching_stakes(sels, 100, "BACK")
    assert len(res_back) == 2
    
    res_lay, prof_lay, _ = calculate_dutching_stakes(sels, 100, "LAY")
    assert len(res_lay) == 2
    assert all(r["side"] == "LAY" for r in res_lay)

def test_ai_mixed_aliases_and_kwargs():
    sels = [{"selectionId": 1, "price": 2.0, "side": "BACK"}, {"selectionId": 2, "price": 3.0, "side": "LAY"}]
    
    # Test firma 1 (amount)
    res1, _, _ = calculate_ai_mixed_stakes(sels, amount=100)
    assert len(res1) == 2
    
    # Test firma 2 (stake) - Legacy kwargs tolerance
    res2, _, _ = calculate_ai_mixed_stakes(sels, stake=100)
    assert len(res2) == 2

def test_dynamic_cashout_legacy_kwargs():
    # Firma Nuova
    res1 = dynamic_cashout_single(matched_stake=10, matched_price=2.0, current_price=1.5)
    # Firma Legacy (deve reggere)
    res2 = dynamic_cashout_single(back_stake=10, back_price=2.0, lay_price=1.5)
    
    assert res1["lay_stake"] == res2["lay_stake"]
    assert res1["lay_stake"] > 0

def test_validate_selections_dirty_inputs():
    # Input stringati, float sballati e senza nomi
    errors = validate_selections([
        {"selectionId": 1, "price": "1.0", "stake": 0.05}, # Errore quota e stake < 0.10
        {"selectionId": 2, "price": 5.0, "stake": 100, "profitIfWins": "9999999"} # Errore max win
    ])
    assert len(errors) == 3