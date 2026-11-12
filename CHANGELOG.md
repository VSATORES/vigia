# Mudanças

## 2.8.0 — 12/11/2026
- **Aviso de Desfazer** mais curto (4 s, era 5 s) e no rodapé, abaixo do slide, numa linha só, com uma barrinha do tempo
  que falta: não cobre mais nenhum botão. As dicas de teclado somem enquanto ele aparece.
- **Topo sem sobreposição:** se a lista de agentes ou o contador não cabem numa linha, a lista desce para uma 2ª linha e o
  slide desce junto. No celular o link vira "Painel" e o contador some. A 2ª fileira de botões do slide não fica mais cortada.
- **Aviso de computador desligado:** rotina perdida com o PC desligado avisa uma vez quando ele volta (sem reavisar após
  pausa/retomada nem para item novo).

## 2.7.0 — 12/11/2026
- **Aba Estratégia** no topo da Aprovação (ao lado de Pendências e Painel dos agentes), quando o vigia.toml tem
  `[estrategia]`: `arquivo` (JSON da última análise do time), `rodar` (botão "Rodar agora"), `rotulo` e `trava`.

## 2.6.1 — 12/11/2026
- Correção: "Já vi" em slide de saúde que veio de um pedido (ex.: o conferidor avisando que uma execução não deu certo)
  dava "agente 'undefined' não existe na configuração". Agora fecha o pedido pelo caminho normal (ação "ciente").

## 2.6.0 — 11/11/2026
- Aparência da aba Aprovação: `[aparencia]` no vigia.toml escolhe um de 9 temas (cores, fonte, cantos) e um papel de parede (4 prontos ou uma imagem local, servida em /aparencia/papel) com a força do fundo. Sem `[aparencia]`, nada muda.

## 2.5.1 — 11/11/2026
- Vídeo para ao fechar a tela cheia, ao trocar de anexo ou de aba do navegador, e continua de onde parou ("Continuar de onde parou").

## 2.5.0 — 11/11/2026
- **Vídeo como folha de 8 quadros** (imagem, com o minuto de cada quadro), no slide e na tela cheia, com "Tocar o vídeo"
  embaixo. Não depende da placa de vídeo do navegador (áudio sem imagem) e alivia o navegador. Precisa de ffmpeg na máquina.
- Fundo da tela cheia opaco.

## 2.4.0 — 11/11/2026
- **Pendências separadas:** pedido que não executa nada (lembrete, `[aprovacao] lembretes`, padrão "ciente") sai dos slides e vai
  para a gaveta "Pendências", com "Feito" e "Abrir a origem".
- **Aprovar em lote** (Shift+A): pedidos iguais (mesmo agente, ação e detalhe, ou o mesmo `grupo`) numa lista com caixinhas.
- **Ordem:** o que vence primeiro (prazo, ou criado + 48 h), depois o risco, depois quem espera há mais tempo.
- **Pedido parado vence sozinho** (`[aprovacao] validade_horas`, padrão 72): vira "expirado" e volta para o agente.
- Topo mostra conferidos e falhas do dia (o estado "conferido" vem de quem confere a execução).

## 2.2.0 — 11/11/2026
- **Outra ação** (tecla O): quando nenhuma opção serve, você escreve o que quer; a decisão vai para o agente com o texto
  (`estado: "outra"` em decisoes.jsonl) e ele refaz na próxima rodada com um pedido novo.
- **Anexos buscados na hora:** o pedido aponta de onde vêm as fotos (`"anexos": {"de": "<resolvedor>", "id": ...}`) e o
  Vigia chama o resolvedor de `[aprovacao.resolvedores]` quando o slide aparece (cache de 6 h). Bom para links que vencem.
  Vídeo mostra o primeiro quadro; até 8 miniaturas e "+N" abre todos em tela cheia.
- A etiqueta "Sua decisão" muda de cor conforme a fonte do pedido (ou o risco, se a fonte não tiver cor).

## 2.1.0 — 11/11/2026
- **Aba Aprovação, a tela principal** (`/` no `vigia servir`; o painel dos agentes foi para `/painel`). Um slide por
  decisão, passando para o lado: anexo grande à esquerda (imagem, PDF, página; Espaço abre em tela cheia), à direita a
  pergunta, o texto exato que vai sair e para onde, até 4 números e a linha do tempo; embaixo a etiqueta "Sua decisão"
  com 1 (proposta), 2 (alternativa), Editar, Recusar e Depois. Cada slide se ajusta para caber sem rolagem.
- **Pedidos:** o agente grava `pedidos/<agente>/<id>.json` (contrato em `docs/pedido.schema.json`) e nunca executa.
  Depois do Aprovar, o Vigia roda **só** o executor declarado em `[executores]` no toml do agente, recebendo o arquivo do
  pedido (com o texto editado, se houver). Cada evento vai para `dados/decisoes.jsonl`; um pedido não executa duas vezes.
- "Desfazer" por 5 segundos antes de a decisão ir para o servidor. "Depois" esconde por 1 hora.
- Agente quebrado, atrasado ou sem rodar também aparece como slide (Já vi · Rodar agora · Investigar).
- Ícones das fontes configuráveis em `[aprovacao.fontes]` no vigia.toml.
- Acessibilidade: foco visível, nomes nos botões só de ícone, respeito a "reduzir movimento".

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
