def test_devops_engine_file():
    with open("devops_engine_test/test_engine.txt", encoding="utf-8") as f:
        content = f.read()

    assert "DevOps Engine Test" in content
    assert "Second run append test" in content

