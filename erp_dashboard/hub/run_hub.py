#!/usr/bin/env python
# hub/run_hub.py — run on the dedicated hub machine: python hub/run_hub.py

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from hub.server import run_hub

if __name__ == "__main__":
    run_hub()
