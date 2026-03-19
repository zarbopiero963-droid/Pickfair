"""
Build script for creating Windows executable using PyInstaller.
Run this on Windows: python build.py
"""

import os


def build():
    """Build the Windows executable."""
    try:
        import PyInstaller.__main__
    except ImportError as e:
        raise RuntimeError(
            "PyInstaller non installato. Installa PyInstaller per eseguire build.py."
        ) from e

    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(script_dir, "main.py")

    args = [
        main_script,
        "--name=Pickfair",
        "--onefile",
        "--windowed",
        "--clean",
        "--hidden-import=betfairlightweight",
        "--hidden-import=betfairlightweight.streaming",
        "--hidden-import=requests",
        "--hidden-import=urllib3",
        "--hidden-import=certifi",
        "--collect-all=betfairlightweight",
        "--collect-all=certifi",
    ]

    icon_path = os.path.join(script_dir, "icon.ico")
    if os.path.exists(icon_path):
        args.append(f"--icon={icon_path}")

    print("=" * 50)
    print("Building Pickfair Executable")
    print("=" * 50)
    print()

    PyInstaller.__main__.run(args)

    print()
    print("=" * 50)
    print("Build Complete!")
    print("=" * 50)
    print()
    print("Executable location: dist/Pickfair.exe")
    print()


if __name__ == "__main__":
    build()
