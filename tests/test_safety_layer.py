from core.safety_layer import SafetyLayer


def test_safety_layer_blocks_orders():

    safety = SafetyLayer()

    safety.activate_safe_mode("test")

    assert safety.is_blocked()