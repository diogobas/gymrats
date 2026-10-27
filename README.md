# GymRats — apuração mensal

Apura a classificação mensal da competição fitness feita no app GymRats e
publica o resultado num site estático que os competidores acessam.

O GymRats não tem API pública nem versão web, e a exportação de dados é paga.
O admin local coleta os rankings pela API interna, com login por código de e-mail.
Prints de tela do celular continuam disponíveis como alternativa.

## Dois públicos, duas metades

| | quem usa | quando | como roda |
|---|---|---|---|
| **backend** | só o admin | uma vez por mês | local, `0.0.0.0`, acessado pelo celular |
| **site** | os competidores | a qualquer momento | estático no GitHub Pages, sem backend |

O backend, ao fechar uma apuração, escreve os JSONs de resultado dentro de
`frontend/public/data/`. Você commita, o site republica. Sem servidor, sem
banco, sem serviço pago.

## Camadas

Cinco, com fronteiras explícitas — qualquer uma pode ser trocada sem tocar
nas outras.

```
backend/gymrats/
  core/       1. apuração   Python puro. Sem FastAPI, sem OCR, sem I/O.
  ingestion/  2. de onde vêm os prints (interface plugável)
  ocr/        3. bytes de imagem -> linhas extraídas (interface plugável)
  review/     4. o rascunho conferido: junta, deduplica, desconfia
  api/        5. FastAPI. Só orquestra.
  storage/       JSON em disco e publicação para o site
```

A regra que sustenta o resto: **nada no núcleo assume que a imagem veio de um
caminho de arquivo**. A ingestão trabalha com bytes e um identificador opaco;
o OCR recebe bytes; o núcleo recebe estruturas de dados já tipadas e nunca vê
`bytes`, `Path` nem string bruta de OCR.

## Estado atual

O admin local oferece **Dados → Conferir → Resultado** para o clube
**Gymrats 2026! (2504035)**. A API interna é compartilhada com o
[coletor de pesquisa](experiments/gymrats_collector/README.md); não é uma API
pública oficial. A sessão existente é reutilizada quando válida.

- [x] **Núcleo de apuração + testes** — regras, desempate, acumulado anual
- [x] **Modo estático do frontend** — o site que os competidores leem
- [x] **Ingestão por upload e tela de conferência** — o mês inteiro pelo celular
- [ ] OCR — hoje o motor é o `manual`: você digita olhando o print ao lado

## Conferindo o que já existe

```sh
uv sync --group dev
uv run pytest
uv run ruff check backend tests
uv run ruff format --check backend tests
PYTHONPATH=backend uv run python -m gymrats.report
```

Esses são exatamente os comandos que o CI roda — se passam aqui, passam lá.

O `report` recalcula o último mês fechado e o acumulado a partir de `data/` e imprime as duas
tabelas no terminal, para você conferir contra os prints do app linha por
linha. Ele **não escreve nada** — é seguro rodar a qualquer momento.

```
 #  nome       pts   hustle  dias   cal   valor hustle  dias    kcal       km    tempo
 1. Arthur      4         2     1     1         356.50    26  14771   107.33   31h01
 2. Andressa    4         1     1     2         361.76    26  10593*    5.64   33h53
...
  Arthur x Andressa (4 pts): distância no mês — Arthur 107.33 km, Andressa 5.64 km
```

Vale a pena testar o caminho do erro também. Edite `data/months/2026-06.json`,
troque a distância do Arthur para menos que a da Andressa, e rode de novo: a
ordem de junho inverte, e o acumulado muda junto. Desfaça com `git checkout`.

Os testes não dependem de FastAPI, OpenCV nem Tesseract — é o ponto da
separação em camadas.

### Publicando para o site

```sh
PYTHONPATH=backend uv run python -m gymrats.publish
```

Recalcula tudo e escreve `frontend/public/data/`. É o único comando que grava
alguma coisa. Os arquivos que ele gera **são versionados**: o site não tem
backend, então o que está commitado é o que os competidores leem. Um teste
(`tests/test_publisher.py`) republica em memória e compara com o que está no
disco, então esquecer de rodar o publish depois de mexer numa regra aparece
como teste vermelho, não como uma tabela velha no ar.

### O site

```sh
cd frontend
npm install
npm run dev        # modo estático — o que os competidores veem
npm run dev:local  # modo admin: upload, conferência e fechamento
npm test           # trava a separação entre os dois modos
```

### Onde ficam os dados

- `data/participants.json` — cadastro
- `data/months/2026-01.json` até `2026-09.json` — sete rankings por mês, coletados pela API.
- `data/previews/2026-10.json` — prévia de outubro, separada dos meses fechados.
- `data/history/2026.json` — classificações originais de janeiro a maio, preservadas como referência. As tabelas detalhadas têm prioridade no cálculo.
- `data/reviews/2026-api-refresh.json` — decisões de revisão, diferenças e limites da fonte.

`tests/fixtures/` preserva a transcrição original de junho e a planilha antiga
para regressão. Os dados revisados em `data/` têm testes próprios; as saídas
em `frontend/public/data/` precisam corresponder exatamente à republicação.

## O site

React + Vite + TypeScript, mobile-first, sem dependência de runtime além do
React. Um código-base, **dois builds**, escolhidos por `VITE_APP_MODE`:

| modo | quem usa | fonte de dados | tela de apuração |
|---|---|---|---|
| `static` (padrão) | os competidores | os JSONs do próprio build | **não existe no bundle** |
| `local` | só você | a API FastAPI | sim |

```
frontend/src/
  App.tsx  router.ts  types.ts  format.ts  styles.css
  data/         de onde vêm as tabelas (interface + fonte estática)
  components/   as telas de leitura
  modes/local/  a metade admin: prints, conferência, fechamento
                — some inteira no build estático
```

### O modo não é um `if` em runtime

`vite.config.ts` troca `__LOCAL__` por um literal. No build estático,
`if (__LOCAL__)` vira `if (false)`, o Rollup poda o ramo e **o chunk do
`AdminApp` não chega a ser gerado**. O site é público e não tem backend: o que
for para o bundle vai para todo mundo, então a tela de upload precisa estar
*ausente*, não escondida.

Isso é uma otimização, e otimizações silenciosamente param de valer quando
alguém refatora a condição para uma variável. Por isso `frontend/tests/bundle.test.ts`
roda os **dois** builds de verdade e lê o que saiu: falha se o bundle estático
contiver qualquer marca da tela de upload, **e falha também se o bundle local
não contiver** — senão o teste ficaria verde no dia em que a tela fosse
renomeada ou apagada.

### Navegação

Rotas por hash (`#/mes/2026-06`, `#/ano/2026`), porque o Pages serve arquivo
estático: um caminho de verdade daria 404 ao recarregar. `base` vem de
`VITE_BASE`, então nada fica preso a um domínio.

Janeiro a setembro de 2026 têm tabelas detalhadas no seletor. O caminho de
histórico sem detalhes continua disponível para temporadas com somente a
classificação final, mas os nove meses atuais usam a coleta revisada.

### Desempates

O objetivo é o resultado se explicar sozinho. Cada linha desempatada leva um
selo, a linha expandida traz a frase inteira, e abaixo da tabela há a lista de
todos os desempates do mês — visível sem tocar em nada. A frase vem pronta do
JSON: é a mesma que a apuração emitiu.

## Apurando um mês

Duas coisas rodando na sua máquina, e o resto acontece no celular.

```sh
uv run python -m gymrats.serve        # API em 0.0.0.0:8000
npm run dev:local --prefix frontend   # site em modo admin, com --host
```

O `serve` imprime no boot **a URL para abrir no celular** — é o ponto do
comando: os prints estão lá, não aqui. O site descobre a API sozinho (mesmo
host, porta 8000), então não há nada para configurar depois de digitar o
endereço. `VITE_API_URL` existe para o caso estranho.

Três etapas, e a do meio não tem atalho:

1. **Prints.** Escolha o mês e mande os prints direto do rolo da câmera —
   seleção múltipla, um envio só. Um lote pela metade fica listado em "lotes
   pendentes" para você retomar depois.
2. **Conferir.** Cada print com o que foi lido dele ao lado, tudo editável. O
   valor vai **como está escrito no app** (`14,939 calorias`), porque quem
   interpreta a string é o domínio, e redigitar `14939` jogaria fora a
   conferência. Linha com problema fica destacada com o motivo em português.
   Nome desconhecido abre vincular-ou-cadastrar — vincular grava o apelido, e
   no mês seguinte aquele mesmo print se resolve sozinho. Salva sozinho a cada
   edição: o rascunho fica em `data/inbox/<lote>/draft.json`, e uma aba
   descartada pelo Safari não custa vinte correções.
3. **Fechar.** As classificações do mês e do ano, renderizadas pelos mesmos
   componentes do site público — é literalmente o que o grupo vai ver.
   Confirmar grava `data/months/YYYY-MM.json`, regera os JSONs do site e
   aposenta os prints do lote. Falta só commitar no git.

**No caminho legado de screenshots**, os avisos não impedem fechar o mês. A autoridade final é sua; a interface
é que exige passar pela conferência. Os seis tipos são `position_mismatch`,
`unknown_name`, `unparsed_value`, `duplicate_name`, `missing_modality` e
`missing_period`.

### A camada `review/`

Juntar as duas metades de uma lista que não coube na tela, deduplicar a
sobreposição, resolver apelidos, e conferir a posição que o app imprimiu
contra a ordem que os valores implicam. Python puro, sem motor de OCR e sem
HTTP — as regras da conferência não são nem do Tesseract nem da apuração.

A conferência cruzada compara contra a ordem **crua**, inclusive em calorias.
E é ela que pega a pior classe de erro de OCR: `"3S6.SO"` lido no lugar de
`"356.50"` vira o número 3, calado e errado. Nada na string denuncia isso — o
que denuncia é o app ter posto aquela linha em primeiro, e 3 não vir primeiro.

### As rotas

| método | rota | papel |
|---|---|---|
| `GET` | `/api/health` | quais plugins estão ligados agora |
| `GET`/`POST` | `/api/participants` | cadastro, criar |
| `PATCH` | `/api/participants/{nome}` | apelidos e flag de bônus |
| `POST` | `/api/ingest/upload` | multipart `files[]` → `{batch_id, items[]}` |
| `POST` | `/api/ingest/scan` | fontes não-upload: chama `list_pending()` |
| `GET` | `/api/ingest/{lote}/items/{item}/image` | bytes, para o preview |
| `POST` | `/api/ocr/{lote}` | roda o motor e monta o rascunho |
| `GET`/`PUT` | `/api/ocr/{lote}/draft` | o rascunho salvo, reavaliado a cada leitura |
| `POST` | `/api/tally/preview` | calcula sem gravar |
| `POST` | `/api/tally/commit` | grava, republica, aposenta o lote |
| `GET` | `/api/export/{mês}.csv` | CSV para colar no Sheets |

A API é fina de propósito: as rotas validam, chamam uma coisa e serializam. Se
uma delas ganhar uma segunda decisão, essa decisão é de outra camada.

## CI / CD

Dois workflows, em `.github/workflows/`.

### `ci.yml` — em todo push na master e em todo PR

| job | o que faz |
|---|---|
| `lint` | `ruff check` e `ruff format --check` |
| `test` | a suíte em Python 3.11 e 3.13 |
| `frontend` | `tsc`, os testes de bundle e o mesmo build que o Pages faz |
| `tally` | roda o `report` contra `data/` e joga as duas tabelas no resumo do run |

O job `tally` é o que mais vale num PR: as classificações de junho e do ano
aparecem no resumo da execução, então **qualquer mexida numa regra de apuração
fica visível como uma mudança de tabela**, não como um teste vermelho que você
precisa decifrar.

Todos os jobs usam `uv sync --locked`, que falha se o `pyproject.toml` e o
`uv.lock` discordarem — um `uv lock` esquecido não passa despercebido.

### `pages.yml` — publica o site

Constrói o frontend em modo estático (`VITE_APP_MODE=static`, com `VITE_BASE`
derivado do nome do repositório para o GitHub Pages servir em `/gymrats/`) e
publica.

O workflow começa checando se `frontend/package.json` está lá — sobra do tempo
em que o site não existia, e continua sendo uma rede: se o frontend sumir, ele
escreve "nada a publicar ainda" no resumo em vez de ficar vermelho ou verde
mentindo.

O que vai para o ar é o conteúdo de `frontend/public/data/` **como está
commitado**. O build não roda o publish: gerar dados durante o deploy
significaria descobrir uma mudança de tabela depois de ela já estar publicada.

O GitHub Pages usa **Settings → Pages → Source: GitHub Actions**.
O site público está em https://diogobas.github.io/gymrats/.

## Regras de apuração

Implementadas em `core/scoring.py`, `core/tiebreak.py` e `core/season.py`.

1. **Bônus de calorias.** +20% sobre o valor bruto de quem tem a flag ligada,
   aplicado **antes** de ordenar a tabela. Vale só para calorias — distância e
   duração usam sempre o valor bruto.
2. **Exclusão.** Quem tem 0 hustle points fica fora da apuração mensal, e sai
   antes do ranqueamento, sem ocupar posição.
3. **Ranking de competição** em cada uma das três tabelas de pontuação:
   empate em 1º gera 1, 1, 3.
4. **Pontuação mensal** = soma das três posições. Menor soma lidera.
5. **Cascata de desempate:** maior distância no período → maior duração no
   período → empate declarado. Na terceira, o sistema **não escolhe vencedor**:
   as pessoas dividem a posição e o empate entra em `unresolved_ties` para o
   admin decidir.

### Acumulado anual ("pontos corridos")

Uma coluna por mês com a **posição final** da pessoa naquele mês. Quem não
competiu — entrou depois, faltou, ou foi excluído por hustle zero — recebe a
posição do último colocado **daquele mês** mais um, calculado mês a mês e
aplicado retroativamente. Total é a soma das colunas; menor total lidera.

O desempate anual roda a mesma cascata contra distância e duração de **1º de
janeiro até o último dia do mês apurado**. Esse corte fica registrado na coleta;
reapurar junho em outubro continua consultando somente até 30 de junho. Os
snapshots antigos de "Este ano" são preservados como referência até a revisão.

### Detalhes que não são óbvios

- **Comparações são exatas.** Todo valor passa por `Decimal` antes de ser
  comparado (`core/ranking.py`). Em ponto flutuante binário, `3 * 1.2` dá
  `3.5999999999999996`, e o bônus de 20% multiplica exatamente o tipo de
  número que derrapa. Uma derrapada dessas decide um campeonato.
- **A conferência cruzada usa o valor bruto.** O app numera as posições na
  lateral direita sem saber do bônus de calorias, então a ordem calculada que
  se compara contra ela é a ordem **crua**, não a ajustada.
- **O bônus de calorias não é cosmético.** Em junho ele mudou seis das dez
  colocações da tabela de calorias. Por isso a regra 1 insiste em aplicá-lo
  *antes* de ordenar, e não depois.
- **Nome desconhecido nunca é adivinhado.** `core/roster.py` resolve por nome
  exato, depois por apelido, depois por comparação sem acento e sem
  maiúsculas (é o que absorve o OCR comendo o acento de "Túlio"). Além disso,
  devolve `None` e a interface pergunta.
- **Valor ilegível não vira zero.** `parse_number` levanta `ParseError`, e a
  linha é destacada na conferência.

## Formatos de dados

### Entrada, versionada e editável à mão

`data/participants.json` — cadastro. `name` é o nome canônico das tabelas;
`aliases` cobre o nome completo do perfil que o app mostra.

```json
{ "name": "Andressa",
  "aliases": ["Andressa Barcelos Aires Barros"],
  "calorie_bonus": false }
```

`data/months/YYYY-MM.json` — as tabelas já conferidas. É a **fonte de verdade**:
o resultado é sempre recalculável a partir daqui.

```json
{ "schema_version": 1,
  "month": "2026-06",
  "tables": {
    "hustle":   { "month": [ {"name": "Arthur", "value": 339.75, "reported_position": 1} ] },
    "distance": { "month": [ … ], "year": [ … ] }
  } }
```

Unidades fixas: hustle em pontos, `active_days` em dias, `calories` em kcal
**brutas, sem bônus**, `distance` em km, `duration` em **minutos**.
`reported_position` é o número que o app imprimiu na tela, guardado para a
conferência cruzada continuar auditável depois.

### Saída, consumida pelo site

Três arquivos, escritos pelo `publish` em `frontend/public/data/`. O site é
burro de propósito: tudo que ele precisa para se explicar já vem no JSON,
inclusive a frase que justifica cada desempate.

`index.json` é o manifesto — a primeira coisa que o site carrega, e o que diz
o que ele pode pedir depois:

```json
{ "schema_version": 1,
  "generated_at": "2026-07-28T15:17:06-03:00",
  "latest_month": "2026-06", "latest_year": 2026, "years": [2026],
  "months": [ { "month": "2026-01", "year": 2026, "detail": false },
              { "month": "2026-06", "year": 2026, "detail": true } ] }
```

`detail: false` marca os meses que vieram do `history/`: não existe
`months/2026-01.json` para buscar, e a ordem daquele mês sai das colunas do
acumulado. Sem essa marca, um 404 seria ambíguo entre "apurado à mão" e
"publish quebrado".

`months/YYYY-MM.json` e `season/YYYY.json` são o resultado em si:

```json
{ "position": 1, "name": "Arthur", "total": 4,
  "positions": { "hustle": 1, "active_days": 1, "calories": 2 },
  "values": { "calories": { "raw": 15980, "bonus_applied": false, "adjusted": 15980 },
              "distance_km": 138.61, "duration_min": 13301, "duration_label": "221h41" },
  "tiebreak": {
    "resolved_by": "distance",
    "detail": "Empate em 4 pontos com Andressa. Desempatado por maior distância no mês: Arthur 138,61 km, Andressa 121,40 km."
  } }
```

O núcleo não gera texto — ele emite um `TiebreakInfo` estruturado, e
`storage/schema.py` renderiza a frase. Apresentação fica fora do domínio.

## Plugando uma fonte de prints nova

*(A interface e as duas implementações entram no próximo passo; esta seção
descreve o contrato já fixado.)*

A ingestão existe para que os prints possam vir de outro lugar no futuro —
um bot de Telegram, Dropbox, Google Drive — **sem tocar em OCR, apuração ou
frontend**. Para acrescentar uma fonte, é só isto:

1. Crie `backend/gymrats/ingestion/<sua_fonte>.py` com uma classe que
   implemente três métodos:

   ```python
   class ScreenshotSource(Protocol):
       def list_pending(self) -> list[ScreenshotItem]: ...
       def fetch(self, item: ScreenshotItem) -> bytes: ...
       def mark_processed(self, item: ScreenshotItem) -> None: ...
   ```

   `ScreenshotItem` carrega um **identificador opaco** e metadados
   (nome original, tamanho, quando chegou). O identificador é da sua fonte —
   pode ser um `message_id` do Telegram ou um file ID do Drive. Nada fora da
   ingestão o interpreta.

2. Registre-a em `ingestion/registry.py`, associando um nome curto.

3. Aponte `GYMRATS_SOURCE=<nome>` na configuração.

Só isso. `fetch` devolve bytes, e é o único formato que o resto do sistema
conhece — nenhuma camada acima assume caminho de arquivo, então uma fonte
remota entra sem adaptação.

As duas fontes implementadas são `upload` (padrão, recebe multipart da API
vindo do navegador do celular — o fluxo principal) e `local_folder`, que lê de
um diretório do disco, útil para reprocessar em lote e para testes. Nenhuma
apaga nada: o que foi processado vai para `processed/`, porque um mês que
precise ser reapurado precisa dos prints de que saiu.

Os identificadores viajam por uma URL e voltam como pedaço de caminho, então
são **construídos pela fonte**, nunca aceitos como vieram — e a API só busca
itens que a própria fonte listou.

## Plugando outro motor de OCR

Mesma ideia, em `ocr/`:

```python
class OcrEngine(Protocol):
    def extract(self, image: bytes) -> Extraction: ...
```

`Extraction` traz `{modalidade, recorte, linhas: [{posição, nome, valor_bruto}]}`.
`valor_bruto` é a string como o OCR leu — quem a interpreta é
`core/values.py`, que é domínio, não OCR. Trocar Tesseract por PaddleOCR,
EasyOCR ou o framework Vision do macOS não pode mudar como
`"1,026.13 quilômetros"` é lido.

O motor que existe hoje é o `manual`: ele devolve uma extração vazia por print,
e a tela de conferência abre com a imagem de um lado e as linhas em branco do
outro. Não é um placeholder por preguiça — é o que fecha o ciclo antes do OCR
existir, e continua sendo o plano B para o print que o motor de verdade
engasgar. O passo 4 registra o pytesseract (com pré-processamento em OpenCV:
inverter o dark mode, escalar, binarizar, idioma português) ao lado dele, e
nada mais muda.

## Os fixtures

### Junho de 2026 — `tests/fixtures/2026-06.json`

As cinco modalidades, nos dois recortes, **transcritas dos prints reais**. Os
testes conferem pessoa por pessoa a posição em cada modalidade contra a
planilha de junho, e a soma bate nas dez linhas.

O caso não é trivial, e é por isso que ele vale:

- **O bônus de calorias muda seis das dez colocações** daquela tabela. Túlio
  fez 8.059 kcal cruas contra 7.325 da Lorrana e terminou atrás dela.
- **A Andressa liderou a duração do mês e mesmo assim perdeu o desempate.**
  33h53 contra 31h01 do Arthur, o melhor tempo de junho. Mas a cascata
  pergunta distância primeiro, e ali são 5,64 km dela contra 107,33 km dele.
  Se os dois critérios estivessem na ordem inversa, junho teria outro campeão.

### Acumulado 2026 — `tests/fixtures/season-2026.json`

Real de ponta a ponta: seis meses, quinze pessoas, campos variando de 10 a 15
competidores. O código recebe **apenas quem foi ranqueado em cada mês, em
ordem** — quem faltou e quanto recebe é ele que deduz.

Isso exercita a regra de ausência em cinco valores diferentes (14, 16, 13, 14,
12, 11), e todos os seis meses da planilha conferem com "último colocado + 1".

**O empate do topo se justifica.** Diogo e Arthur estão os dois com 16 pontos,
e a planilha põe o Diogo em 2º. Conferido contra a distância do ano: 1.026,13
km dele contra 893,06 km do Arthur. A ordenação seguia a regra 5, não foi
arbitrária. Repare que o Arthur lidera a **duração** do ano (221h41 a 200h03)
— o segundo critério, que a cascata nunca alcança porque a distância já
separou os dois.


## Coleta pela interface local

Inicie a API e o frontend com os comandos de desenvolvimento acima e abra
`#/admin`. Selecione um mês encerrado de 2026 (o padrão é o mês anterior),
conecte a conta pelo código de e-mail e clique em **Buscar dados do GymRats**.
A conta e o vínculo com o clube são validados antes de substituir a sessão
anterior. Token, assinatura e nonce ficam no backend; o código não é salvo.

São cinco consultas mensais e duas anuais (distância e duração). O recorte
anual é sempre de 1º de janeiro até o último dia do mês selecionado, inclusive
quando se reapura um mês antigo. Há uma coleta ativa por instância da API;
reinícios marcam coletas em andamento como interrompidas. Falhas preservam as
respostas parciais e a nova tentativa recebe outra execução.

As respostas e os manifestos ficam em
`experiments/gymrats_collector/.local/collections/<execução>/`. As correções
ficam em `corrections.json`, separadas das respostas originais. A configuração
`GYMRATS_PRIVATE` permite mudar essa raiz; ela deve continuar fora do Git.
O botão **Conferir / retomar** recupera as correções, inclusive após reinício.

Na conferência, resolva nomes desconhecidos por vínculo ou cadastro e revise
explicitamente os bônus de calorias. A duração numérica é expressa em minutos,
sem arredondar frações na entrada. A tela mostra o período e as diferenças
contra o mês anterior salvo, inclusive valores e participantes ausentes.
Junho tem uma divergência conhecida de hustle de Lorrana (`211.31` antigo,
`217.68260607439217` coletado) e snapshots anuais antigos com cortes diferentes;
essas diferenças precisam de revisão, não de substituição automática.

Os salvamentos são serializados. A tela aguarda a fila antes de abrir o
resultado. Cada rascunho tem uma revisão; a prévia também registra o estado do
cadastro e dos dados históricos. Correções ou mudanças de cadastro após uma
prévia exigem gerar outra. O fechamento pela API de coleta bloqueia rankings
incompletos, datas incompatíveis, nomes sem vínculo, valores inválidos,
participantes divergentes e meses anteriores ausentes. Avisos de posição
continuam visíveis. Substituir um mês existente exige confirmação explícita
após os avisos e diferenças.

O fechamento valida uma publicação numa cópia temporária antes de gravar e
restaura os arquivos anteriores se a gravação local falhar. Salva a origem e
os cortes na tabela revisada, sem levar as respostas privadas para o site.
**Apuração salva** significa arquivos locais prontos; **resultado publicado**
só ocorre depois do fluxo Git/PR e do deploy. O navegador não faz commit/push.

Rotas novas, todas sob `/api/gymrats`:

| Método | Rota | Uso |
|---|---|---|
| GET / DELETE | `/session` | validar conexão / desconectar localmente |
| POST | `/session/code` | solicitar código (`email`) |
| POST | `/session/verify` | verificar código (`code`) |
| GET / POST | `/runs` | listar / iniciar coleta (`month`) |
| GET | `/runs/{id}` | consultar progresso e falhas |
| GET / PUT | `/runs/{id}/draft` | carregar / salvar correções com `revision` |
| POST | `/runs/{id}/preview` | prévia da `revision` salva |
| POST | `/runs/{id}/commit` | fechar com `revision`, `preview_token` e `replace` |

Os testes são offline e não usam a sessão privada. Em 27/10/2026 o admin
confirmou os bônus do cadastro e autorizou reapurar **janeiro a setembro** com
a API atual, mesmo após a comparação mostrar diferenças contra o histórico.

A API retorna 15 contas e **não recupera Thamyres**, presente nas classificações
originais de janeiro a abril. Isso é uma limitação da fonte, não prova de que
ela não participou. A reapuração substitui os resultados efetivos com essa
limitação aceita; as ordens antigas e as diferenças ficam preservadas no
relatório de revisão. Junho mantém as dez posições; os valores de hustle de
Lorrana e os recortes anuais são atualizados de forma explícita no relatório.

Os nove meses têm sete rankings cada. O acumulado atualizado até setembro
começa por Arthur (21), Isadora (24) e Diogo (33). Não há dados inventados para
participantes ausentes da fonte. O `report --month YYYY-MM` usa somente os meses
até o selecionado, sem contar novamente o histórico substituído.


O CI também executa o fluxo completo no Chrome com respostas offline.
Para repetir a verificação do navegador sem sessão real, inicie o frontend
local e um Chrome com perfil temporário e depuração na porta 9222. Execute
`npm run test:browser --prefix frontend`. `ADMIN_URL` e `CDP_URL` permitem
usar outras portas. O teste intercepta todas as chamadas à API local e usa
fixtures offline: login, coleta, conferência com salvamento pendente, prévia,
substituição e fechamento em 1440px e 390px, além do upload alternativo.
As capturas ficam no diretório temporário do sistema (`gymrats-desktop.png`
e `gymrats-mobile.png`).


## Mês vigente: prévia parcial

Outubro de 2026 está disponível como **mês em andamento**, com dados até
**26/10/2026**. O acumulado que inclui outubro também é provisório. As posições
podem mudar; os nove meses fechados de janeiro a setembro ficam preservados.

No admin, selecione o mês com o rótulo **em andamento**. A coleta usa o último
dia completo em America/Toronto (ontem), tanto para o período mensal quanto
para distância e duração anuais. No primeiro dia do mês ainda não existe um
dia completo para consultar. Meses futuros continuam bloqueados.

A ação final é **Salvar prévia do mês**, e grava em `data/previews/`, sem criar
um mês fechado em `data/months/`. O site marca o mês e o acumulado como
provisórios e mostra a data do corte; o manifesto informa separadamente o
último mês fechado. A classificação dos meses fechados continua recalculável
com `Publisher.season(2026, include_provisional=False)`.

A prévia é um snapshot: para atualizar, faça uma nova coleta. Quando outubro
terminar, uma coleta completa permite fechá-lo normalmente; a apuração fechada
passa a ter prioridade e a prévia anterior permanece como referência. O caminho
de screenshots também recusa fechar um mês que ainda não terminou.
