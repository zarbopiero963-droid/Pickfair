import re
from pathlib import Path


def extract_context(log_path="pytest.log"):
    text = Path(log_path).read_text(errors="ignore")

    m = re.search(r"FAILED (tests\/[^\s]+)", text)

    if not m:
        return None

    return m.group(1)


if __name__ == "__main__":
    result = extract_context()
    print(result)
