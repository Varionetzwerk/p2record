#!/usr/bin/env python3
import sys
import os

# Ensure the python/ directory is on the path
sys.path.insert(0, os.path.dirname(__file__))

from ui.app import P2RecordApp

if __name__ == '__main__':
    app = P2RecordApp()
    sys.exit(app.run(sys.argv))
