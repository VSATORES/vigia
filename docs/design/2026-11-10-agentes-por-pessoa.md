# Vigia por pessoa — como cada um integra os próprios agentes

Status: **desenho aprovado para construir (10/11/2026)**. Ainda não implementado; as etapas estão no fim.

## Por que
Hoje o Vigia funciona para uma instalação (a do autor): os agentes estão descritos à mão em `agentes.d/*.toml`
numa pasta local. Para outras pessoas usarem, cada uma precisa (1) ter a própria instalação, sem nada pessoal no
código, e (2) ligar os próprios agentes com o mínimo de esforço — de preferência sem escrever regex de log.

## Rastros que já existem (de onde o desenho parte)
1. **Molde de pasta de agente** (os agentes de rotina já seguem): uma pasta por agente com `CLAUDE.md`/`INSTRUCOES.md`
   (o que ele faz), `rodar.sh` (o que o cron chama), `estado.json`, `rodadas/` e `logs/AAAA-MM-DD[-HHh].txt`
   terminando com `exit=N <date>`. Ex.: `manutencao/agentes/caca-manutencao/`, `ponte-suporte-manutencao/agente/`.
2. **Coletor de uso de IA da empresa** guarda por pessoa, em um JSON de configuração local (ex.: `~/.coletor-ia/config.json`), a chave
   `pastas_agente` (lista das pastas que contam como "agente" na régua) e `pessoa`. É a lista oficial de "quais
   são os agentes de cada um" — mas hoje vem desatualizada (na máquina do autor só tem `/root/projetos/diario`).
3. **Skills com config pessoal** (ex.: uma skill de vigia de conta usa `~/.claude/<nome>.config.json` com nome e
   pastas da pessoa) — padrão já aceito: o código é comum, a config é da pessoa.
4. Agentes que rodam em servidor (banco) não têm pasta local: entram por `fonte = "sql"` (já existe).

## Princípios
- **Código comum, instalação pessoal.** O repositório nunca tem nome, marca, credencial ou dado de ninguém
  (já garantido por teste). Tudo que é da pessoa fica em `~/.config/vigia/` (ou na pasta que ela escolher).
- **O agente se descreve sozinho.** A descrição mora **junto do agente**, não no painel: um arquivo
  `vigia.agente.toml` dentro da pasta do agente. Quem cria o agente já entrega o "como monitorar".
- **Integrar com uma linha.** Agente novo não precisa de regex: no fim do `rodar.sh`, uma chamada
  `vigia registrar <id> ok|falhou "motivo" [--volume N]`. Os modos antigos (ler log, JSONL, SQL) continuam.
- **Descoberta, não cadastro.** O Vigia acha os agentes da pessoa varrendo pastas (as do `pastas_agente` do coletor,
  se existir, e as listadas no `vigia.toml`), e propõe o que falta.

## Peças
### 1. Instalação por pessoa — `vigia init`
`python3 -m vigia init --pessoa "Nome" [--pasta ~/.config/vigia]` cria:
```
~/.config/vigia/
  vigia.toml        # pessoa, meta, porta, tema, [descoberta], [notificar], [conexoes]
  agentes.d/        # agentes extras escritos à mão (opcional)
  temas/            # tema próprio (opcional; padrão = neutro)
  dados/            # histórico, estado, ações, token — nunca sai da máquina
```
e imprime as linhas de cron (`gerar` a cada 15 min e `servir` no boot). `VIGIA_CONFIG` aponta para ela.

### 2. Manifesto do agente — `vigia.agente.toml` (na pasta do agente)
Mesmo formato de `agentes.d/*.toml`, com caminhos **relativos à pasta do agente**:
```toml
nome = "Caça-manutenção"
area = "Manutenção"
o_que = "Procura problema de manutenção sem card e manda a lista na DM."
fonte = "vigia"            # novo: lê os registros feitos por `vigia registrar`
[agenda]
cron = "15 10 * * 1-5"
comando = "rodar.sh"       # confere se está no crontab
[acoes]
rodar = "./rodar.sh"
instrucoes = "INSTRUCOES.md"
```

### 3. Registro direto — `vigia registrar` + `fonte = "vigia"`
- `vigia registrar <id> <ok|falhou|sem_novidade|inicio> ["motivo"] [--volume N] [--duracao S]` grava uma linha em
  `dados/registros/<id>.jsonl` (hora, status, motivo, volume, duração). `inicio` marca começo (para medir duração e
  mostrar "rodando").
- `fonte = "vigia"` lê esse arquivo (reaproveita o coletor `jsonl`). É o jeito recomendado para agente novo.
- Molde de `rodar.sh`: `vigia registrar caca inicio` no começo; no fim
  `vigia registrar caca $([ $? -eq 0 ] && echo ok || echo falhou) "$(tail -1 log)"`.

### 4. Descoberta — `vigia descobrir`
`[descoberta]` no `vigia.toml`:
```toml
[descoberta]
pastas = ["~/manutencao/agentes/*", "~/manutencao/*/agente"]
coletor = "~/.coletor-ia/config.json"   # opcional: usa a chave pastas_agente desse JSON (chave configurável)
```
- Na geração: toda pasta com `vigia.agente.toml` vira item (id = nome da pasta, ou `id` do manifesto).
- `vigia descobrir`: lista pastas que **parecem** agente (têm `rodar.sh` + `logs/`, ou estão no crontab) mas não
  têm manifesto, e oferece criar um a partir do molde (lê o crontab para preencher `cron` e `comando`).
- Opcional e explícito: `vigia descobrir --sincronizar-coletor` mostra as pastas de agente que faltam no
  `pastas_agente` do coletor (não grava sem a pessoa confirmar — a régua de uso de IA depende dessa lista).

### 5. Visão de time (depois, fora desta etapa)
Cada pessoa já grava `dados/ultimo.json`. Um painel de time pode juntar vários `ultimo.json` (pasta compartilhada
ou upload) sem acesso às máquinas. Fica para quando houver mais de uma pessoa usando.

## Fora de escopo
Servidor central, login, permissões por pessoa, executar ações na máquina de outra pessoa.

## Etapas para construir
1. `fonte = "vigia"` + `vigia registrar` (com testes).
2. Manifesto `vigia.agente.toml` + `[descoberta] pastas` (caminhos relativos à pasta do agente; id único).
3. `vigia init` (cria a instalação pessoal e imprime o cron) e `vigia descobrir` (+ leitura opcional do coletor).
4. Migrar os agentes do autor: criar manifesto em `caca-manutencao/` e `ponte-suporte-manutencao/agente/`, tirar os
   toml equivalentes de `agentes.d/`, adicionar `vigia registrar` nos `rodar.sh` (sem mudar o que eles fazem).
5. README: seção "Integrar o seu agente em 3 passos"; molde em `exemplos/agente-modelo/`; versão 2.1.0.
6. Decisão do autor antes de gravar: atualizar `pastas_agente` do coletor com as pastas reais dele.
