

def test_kwargs_backward_compatibility():
    data = {"stake": 10, "price": 2.0}

    assert data["stake"] == 10
    assert data["price"] == 2.0