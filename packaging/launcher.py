"""Entry point for the packaged StatisticBuddy.exe (PyInstaller needs a script, not a package)."""
import sys

from statisticbuddy.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
