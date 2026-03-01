"""
Build script for creating Windows executable using PyInstaller.
Run this on Windows: python build.py
"""

import PyInstaller.__main__
import os
import sys

def build():
    """Build the Windows executable."""
    
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(script_dir, "main.py")
    
    # PyInstaller arguments
    args = [
        main_script,
        "--name=Pickfair",
        "--onefile",  # Single executable
        "--windowed",  # No console window
        "--clean",  # Clean build
        # Add icon if exists
        # "--icon=icon.ico",
        # Hidden imports for betfairlightweight
        "--hidden-import=betfairlightweight",
        "--hidden-import=betfairlightweight.streaming",
        "--hidden-import=requests",
        "--hidden-import=urllib3",
        "--hidden-import=certifi",
        # Collect all data files
        "--collect-all=betfairlightweight",
        "--collect-all=certifi",
    ]
    
    # Check for icon
    icon_path = os.path.join(script_dir, "icon.ico")
    if os.path.exists(icon_path):
        args.append(f"--icon={icon_path}")
    
    print("=" * 50)
    print("Building Pickfair Executable")
    print("=" * 50)
    print()
    
    # Run PyInstaller
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
