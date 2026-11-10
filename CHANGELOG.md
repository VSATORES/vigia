# Mudanças

## 1.2.0 — 10/11/2026
- Aba **Agentes** ganhou a visão em **cartões** (abre por padrão): um cartão por item, agrupado por área, com
  status, última mensagem, barra de batidas (rotina: últimas 40 rodadas; agente de banco: um traço por dia,
  30 dias), disponibilidade 7d, última, próxima e duração média (ou volume de hoje).
- Filtros **Todos / Precisa de atenção / Funcionando**; botão **Cartões / Tabela** (lembra a escolha).
- Clique no cartão abre o mesmo detalhe de antes; realce ao passar o mouse liga cartão e registro.

## 1.1.0 — 10/11/2026
- Duas abas: **Visão geral** (abre primeiro) e **Agentes** (tabela e detalhe). Teclas 1 e 2 trocam.
- Visão geral: números do mês, o que precisa de você (com a ação), resumo por área com 14 dias,
  calendário do mês (% de itens ok por dia), saúde da infraestrutura e próximas execuções.
- Avisos configuráveis no vigia.toml (`[[avisos]]`), ex.: login que vai expirar, limite de uso estourado.

## 1.0.0 — 10/11/2026
- Primeira versão pública.
- Três fontes: `log_texto`, `jsonl` e `sql` (com flags no PostHog).
- Estados OK · Atrasado · Falhou · Não rodou · Desligado; dia com computador desligado fora da meta.
- Aviso de rotina que não está no crontab.
- Tela: frase do topo que filtra, matriz de 30 dias, registro de hoje, detalhe com gráfico (faixa do normal,
  marcas de mudança, duração p95), teclado, estado na URL, tema Dia/Noite.
- `vigia novo-agente`, `checar-config`, `atualizar`; tema e marca separados do código.
