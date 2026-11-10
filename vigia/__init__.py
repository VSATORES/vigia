"""Vigia: um painel que diz, em 5 segundos, se as suas rotinas e agentes estão rodando."""
import os

_AQUI = os.path.dirname(os.path.abspath(__file__))
try:
    __version__ = open(os.path.join(_AQUI, "..", "VERSION")).read().strip()
except OSError:
    __version__ = "0.0.0"
