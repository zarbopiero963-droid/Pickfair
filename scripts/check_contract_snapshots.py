

def validate_payload(payload):
    required = ["market_id", "selectionId", "price"]

    for r in required:
        if r not in payload:
            raise ValueError(f"Missing {r}")


if __name__ == "__main__":
    sample = {"market_id": "1", "selectionId": 1, "price": 2.0}

    validate_payload(sample)

    print("OK")