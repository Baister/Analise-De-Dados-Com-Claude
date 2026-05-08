#!/usr/bin/env python
# hub/run_hub.py — executar na máquina com acesso ao SQL Server:
#   python hub/run_hub.py
#
# Ao iniciar, o terminal exibirá o URL local e o URL de rede.
# O browser abrirá automaticamente após 1.5s.

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from hub.server import run_hub

if __name__ == "__main__":
    run_hub()
