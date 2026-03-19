

def test_payload_shape():
    payload = {
        "market_id": "1.123",
        "selection_id": 100,
        "price": 2.0,
    }

    assert "market_id" in payload
    assert "selection_id" in payload
    assert "price" in payload