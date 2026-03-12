import os


def check_imports():
    for root, _, files in os.walk("core"):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path) as file:
                    text = file.read()

                    if "ui." in text:
                        print("Warning: UI import in core", path)


if __name__ == "__main__":
    check_imports()