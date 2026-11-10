"""Fontes de dados. Cada fonte devolve rodadas (rotinas) ou um resumo por dia (agentes por banco).

Rodada = dict(ini, fim, dur, status, motivo, trecho, arquivo, volume)
  status: ok | sem_novidade | falhou | rodando
"""
from . import log_texto, jsonl, sql  # noqa: F401

COLETORES = {"log_texto": log_texto.coletar, "jsonl": jsonl.coletar, "sql": sql.coletar}
