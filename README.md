# Vigia

Um painel que diz, em 5 segundos, se as suas **rotinas agendadas** (cron) e os seus **agentes de IA**
estão rodando — e, com um clique, o que cada um fez, quando falhou e por quê.

**Demonstração (dados fictícios):** https://vsatores.github.io/vigia/

- Python puro (3.11+), sem dependências. Uma página HTML sem build, que abre até direto do arquivo.
- Só lê: não liga, desliga nem reroda nada.
- Honesto por padrão: **ausência de sinal nunca é verde**; fonte fora do ar aparece como falha;
  dia em que o computador estava desligado aparece hachurado e não conta na meta.

## Aba Aprovação (2.1)

Rodando `vigia servir`, o endereço principal é a **aba Aprovação**: um slide por decisão que os seus agentes
prepararam. O agente nunca executa; ele só grava um pedido, e o Vigia executa depois do seu clique.

```json
// pedidos/<agente>/<id>.json  (contrato completo em docs/pedido.schema.json)
{"id": "relatorio-0412", "agente": "revisor", "titulo": "Publicar o relatório de novembro?", "risco": "envio_externo",
 "proposta": {"acao": "publicar", "rotulo": "Publicar", "destino": "Canal do time", "previa": "Relatório publicado."}}
```

```toml
# agentes.d/revisor.toml — só o que estiver aqui pode ser executado
[executores]
publicar = "/caminho/publicar.py {pedido}"     # recebe o arquivo do pedido, com o texto editado se houver
```

Atalhos: ← → passar · 1 / 2 escolher · E editar · R recusar · L depois · Espaço ver o anexo inteiro.
Cada decisão fica em `dados/decisoes.jsonl` (aprovado, recusado, adiado, executado, falhou).

## Estados

| Item agora | Quando |
|---|---|
| **OK** | última rodada (ou gravação) deu certo |
| **Atrasado** | passou do horário + margem e ainda não rodou; ou agente calado num horário em que costuma trabalhar |
| **Falhou** | a rodada terminou com erro, ou a fonte não pôde ser lida |
| **Não rodou** | o horário passou sem rodada com o computador ligado; ou a rotina não está no crontab; ou a flag está ligada e o agente não grava há 7 dias |
| **Desligado** | flag do agente desligada |

Cada dia vira uma célula: ok · atraso (barra baixa) · falha (textura) · computador desligado (hachurado) · nada esperado.
A **meta do mês** (padrão 95%) conta item × dia, sem os dias com o computador desligado.

## Começar

```bash
git clone https://github.com/VSATORES/vigia.git && cd vigia
python3 -m vigia gerar --config exemplos/vigia.toml      # gera docs/index.html
python3 -m vigia servir --config exemplos/vigia.toml     # http://127.0.0.1:8787
```

Para os seus agentes, crie uma pasta com `vigia.toml` e `agentes.d/`:

```bash
mkdir ~/meu-vigia && cp exemplos/vigia.toml ~/meu-vigia/ && mkdir ~/meu-vigia/agentes.d
python3 -m vigia novo-agente backup --fonte log_texto --config ~/meu-vigia/vigia.toml
python3 -m vigia checar-config --config ~/meu-vigia/vigia.toml
```

Agendar (a página se atualiza sozinha a cada 5 min no navegador):

```cron
*/15 * * * * cd /caminho/vigia && python3 -m vigia gerar --config ~/meu-vigia/vigia.toml
@reboot      cd /caminho/vigia && python3 -m vigia servir --config ~/meu-vigia/vigia.toml
```

## Adicionar ou mudar um agente

Um arquivo por agente em `agentes.d/<id>.toml`. **Não precisa mexer em código.** Três fontes:

### `log_texto` — rotina que escreve log
```toml
nome = "Backup noturno"
area = "Rotinas"                 # agrupa na tela
o_que = "Copia os arquivos para o disco externo."
fonte = "log_texto"
[agenda]
cron = "0 7 * * 1-6"             # o mesmo do crontab
rotulo = "seg–sáb 7h"
comando = "backup.sh"            # opcional: avisa se não estiver no crontab
desde = "2026-11-01 07:00"       # opcional: não cobra rodada antes disso
duracao_max_min = 90             # rodada que termina depois disso é tratada como "à mão"
[log]
arquivos = "/var/log/backup/log-*.txt"
fim_rodada = 'exit=\d+'          # linha que fecha uma rodada
volume = '(\d+) arquivos'        # opcional: número para o gráfico
[[regras]]                       # a primeira que casar decide (regex)
se = "disco cheio"
status = "falhou"                # ok | sem_novidade | falhou | rodando
motivo = "Disco cheio"
acao = "Libere espaço; a próxima rodada tenta de novo."
```
Sem regra que case, vale o último `exit=N` (0 = ok).

### `jsonl` — rotina que grava uma linha JSON por execução
```toml
fonte = "jsonl"
[log]
arquivos = "logs/execucoes.jsonl"
campo_hora = "hora"
campo_erro = ["erro"]
```

### `sql` — agente que não tem log, só grava resultado numa tabela
```toml
fonte = "sql"
[sql]
conexao = "banco"               # definida em [conexoes] do vigia.toml
limite_erros_pct = 10           # erro abaixo disso no dia não pinta de vermelho
por_dia = "SELECT dia, n, erros, humano, ultima FROM ..."   # obrigatório
eventos = "SELECT quando, ok, texto FROM ... LIMIT 5000"     # detecta silêncio
alerta  = "SELECT n, texto FROM ..."                         # n > 0 = atenção agora
entrada_por_dia = "SELECT dia, n FROM ..."                    # trabalho que chegou: dia calado com entrada = falha
[flag]
chave = "nome_da_flag"          # lida no PostHog, se houver conexão
```
Só `SELECT`/`WITH` é aceito. Credenciais sempre por variável de ambiente (`"$NOME"`), nunca no arquivo.

Conexões (`vigia.toml`): `mcp_http` (servidor MCP com uma ferramenta de consulta), `posthog` (flags) e
`arquivo` (JSON pronto, usado na demo e nos testes).

## Ações (comandar pelo painel)

Com `python3 -m vigia servir`, o painel em http://127.0.0.1:8787 ganha botões em cada item:

| Botão | O que faz |
|---|---|
| **Rodar agora** | executa `[acoes] rodar` do toml do agente (o mesmo comando do cron). Nada fora do toml roda. |
| **Investigar com Claude** | `claude -p` só leitura com o log, o toml e `[acoes] instrucoes`; o diagnóstico aparece no detalhe |
| **Já vi** | tira o item de "Precisa de você" até o estado mudar |
| **Pausar / Retomar** | o item para de alertar; scripts podem consultar `vigia pausado <id>` |

```toml
[acoes]
rodar = "/caminho/rodar.sh"
instrucoes = "/caminho/INSTRUCOES.md"          # opcional: contexto para a investigação
ferramentas = ["mcp__meu_banco__consultar"]     # opcional: ferramentas extras (só leitura) para investigar
```
As rotas aceitam pedido só de 127.0.0.1 e com a chave da instalação (`dados/token`), que vai só na página servida.
O arquivo gerado (cópia, demo) nunca executa nada.

**Aviso quando quebra ou volta** (uma mensagem por mudança):
```toml
[notificar]
comando = "python3 enviar.py {arquivo}"   # {arquivo}: texto entre <!-- INICIO --> e <!-- FIM -->
link = "http://localhost:8787"
```

## Tema e marca

`tema = "neutro"` (padrão) ou o caminho de uma pasta com `tema.css` (cores dia/noite), `head.html`
(fontes) e `marca.html` (texto ao lado do nome). A marca da sua empresa fica na sua pasta, fora deste repositório.

## Atualizar

```bash
python3 -m vigia atualizar      # git pull + mostra o que mudou (CHANGELOG)
python3 -m vigia versao
```
A página avisa quando há versão nova publicada. Sua configuração nunca é sobrescrita.

## Testes

```bash
python3 -m unittest discover -s tests
```

## Publicar a demonstração

A pasta `docs/` é a página do GitHub Pages (dados fictícios). Depois de mudar o código:
```bash
python3 scripts/gerar_exemplos.py && python3 -m vigia gerar --config exemplos/vigia.toml
./scripts/checar_publico.sh && git commit -am "..." && git push
```
