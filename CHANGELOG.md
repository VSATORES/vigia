# Mudanças

## 1.0.0 — 10/11/2026
- Primeira versão pública.
- Três fontes: `log_texto`, `jsonl` e `sql` (com flags no PostHog).
- Estados OK · Atrasado · Falhou · Não rodou · Desligado; dia com computador desligado fora da meta.
- Aviso de rotina que não está no crontab.
- Tela: frase do topo que filtra, matriz de 30 dias, registro de hoje, detalhe com gráfico (faixa do normal,
  marcas de mudança, duração p95), teclado, estado na URL, tema Dia/Noite.
- `vigia novo-agente`, `checar-config`, `atualizar`; tema e marca separados do código.
