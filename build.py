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
        "--hidden-import=app_modules",
        "--hidden-import=app_modules.betting_module",
        "--hidden-import=app_modules.monitoring_module",
        "--hidden-import=app_modules.simulation_module",
        "--hidden-import=app_modules.streaming_module",
        "--hidden-import=app_modules.telegram_module",
        "--hidden-import=app_modules.ui_module",
        "--hidden-import=controllers",
        "--hidden-import=controllers.dutching_controller",
        "--hidden-import=controllers.telegram_controller",
        "--hidden-import=core",
        "--hidden-import=core.event_bus",
        "--hidden-import=core.risk_middleware",
        "--hidden-import=core.trading_engine",
        "--hidden-import=ui",
        "--hidden-import=ui.mini_ladder",
        "--hidden-import=ui.toolbar",
        "--hidden-import=ui.draggable_runner",
        "--hidden-import=ui.tabs.telegram_tab_ui",
        "--hidden-import=ai",
        "--hidden-import=ai.ai_guardrail",
        "--hidden-import=ai.ai_pattern_engine",
        "--hidden-import=ai.wom_engine",
        "--collect-all=betfairlightweight",
        "--collect-all=certifi",
        "--collect-submodules=app_modules",
        "--collect-submodules=controllers",
        "--collect-submodules=core",
        "--collect-submodules=ui",
        "--collect-submodules=ai",
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
