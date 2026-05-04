# main.py — ponto de entrada
# python main.py

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from ui.app import ERPDashboard

if __name__ == "__main__":
    app = ERPDashboard()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
