# Mudanças

## 2.0.0 — 10/11/2026
- **Comandar, não só olhar.** No painel aberto em `vigia servir` (localhost), cada item ganha botões:
  **Rodar agora** (o comando declarado no toml, nunca comando livre), **Investigar com Claude** (diagnóstico
  só leitura do log e da configuração, aparece no detalhe), **Já vi** (silencia o alerta até o estado mudar)
  e **Pausar / Retomar**. A saída aparece ao vivo no detalhe. Cópias em arquivo e a demo continuam só leitura.
- Aba **Quadro**: colunas Precisa de você · Rodando agora · Próximas 3 horas · Tudo certo · Desligado ou pausado.
- **Aviso** quando um item quebra ou volta ao normal (`[notificar] comando`), sem repetir a cada geração.
- Novos estados: Pausado e Já visto. `vigia pausado <id>` para scripts respeitarem a pausa.
- Correção: linha escrita logo depois do fim da rodada (ex.: "copiado para…") não vira rodada fantasma.

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
