# GymRats — apuração mensal

Apura a classificação mensal da competição fitness feita no app GymRats e
publica o resultado num site estático que os competidores acessam.

O GymRats não tem API pública nem versão web, e a exportação de dados é paga.
A entrada, portanto, são prints de tela do celular.

## Dois públicos, duas metades

| | quem usa | quando | como roda |
|---|---|---|---|
| **backend** | só o admin | uma vez por mês | local, `0.0.0.0`, acessado pelo celular |
| **site** | os competidores | a qualquer momento | estático no GitHub Pages, sem backend |

O backend, ao fechar uma apuração, escreve os JSONs de resultado dentro de
`frontend/public/data/`. Você commita, o site republica. Sem servidor, sem
banco, sem serviço pago.

## Camadas

Quatro, com fronteiras explícitas — qualquer uma pode ser trocada sem tocar
nas outras.

```
backend/gymrats/
  core/       1. apuração   Python puro. Sem FastAPI, sem OCR, sem I/O.
  ingestion/  2. de onde vêm os prints (interface plugável)
  ocr/        3. bytes de imagem -> linhas extraídas (interface plugável)
  api/        4. FastAPI. Só orquestra.
  storage/       JSON em disco e publicação para o site
```

A regra que sustenta o resto: **nada no núcleo assume que a imagem veio de um
caminho de arquivo**. A ingestão trabalha com bytes e um identificador opaco;
o OCR recebe bytes; o núcleo recebe estruturas de dados já tipadas e nunca vê
`bytes`, `Path` nem string bruta de OCR.

## Estado atual

- [x] **Núcleo de apuração + testes** — regras, desempate, acumulado anual
- [ ] Modo estático do frontend
- [ ] Ingestão por upload e tela de conferência
- [ ] OCR

## Rodando os testes

```sh
uv sync --group dev
uv run pytest
```

Os testes cobrem só o núcleo. Não há dependência de FastAPI, OpenCV ou
Tesseract para rodá-los — é o ponto da separação.

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

O desempate anual roda a mesma cascata contra os números de **"Este ano"** do
mês mais recente apurado — o que o app está mostrando hoje, não a soma dos
mensais.

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

`frontend/public/data/months/YYYY-MM.json` e `season/YYYY.json`. O site é
burro de propósito: tudo que ele precisa para se explicar já vem no JSON,
inclusive a frase que justifica cada desempate.

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

As duas fontes implementadas agora são `upload` (padrão, recebe multipart da
API vindo do navegador do celular — o fluxo principal) e `pasta_local`, que lê
de um diretório do disco, útil para reprocessar em lote e para testes.

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

O padrão é pytesseract com pré-processamento em OpenCV (inverter o dark mode,
escalar, binarizar) e idioma português.

## Os fixtures

### Junho de 2026 — `tests/fixtures/2026-06.json`

Hustle points, dias ativos e calorias são **transcritos dos prints reais**. Os
testes conferem, pessoa por pessoa, a posição em cada uma das três modalidades
contra a planilha de junho, e a soma bate nas dez linhas.

O caso é bom porque não é trivial: o bônus de calorias muda seis das dez
colocações daquela tabela. Túlio fez mais calorias cruas que a Lorrana e
mesmo assim terminou atrás dela.

**Distância e duração ainda são placeholders**, marcados com `"_placeholder":
true` no arquivo. São os critérios de desempate, e junho precisa deles duas
vezes — Arthur/Andressa com 4 pontos e Bruna/Lorrana com 16. A ordem final
está afirmada nos testes; o *motivo* de cada desempate não, porque isso é uma
afirmação sobre números que ainda não chegaram.

Existe um teste que se ativa sozinho: enquanto o `_placeholder` estiver lá,
ele dá skip com a mensagem dizendo o que falta. Tire a marca quando os prints
reais entrarem e ele passa a exigir que o critério de desempate seja fixado.

### Acumulado 2026 — `tests/fixtures/season-2026.json`

Real de ponta a ponta: seis meses, quinze pessoas, campos variando de 10 a 15
competidores. O código recebe **apenas quem foi ranqueado em cada mês, em
ordem** — quem faltou e quanto recebe é ele que deduz.

Isso exercita a regra de ausência em cinco valores diferentes (14, 16, 13, 14,
12, 11), e todos os seis meses da planilha conferem com "último colocado + 1".

**Uma pendência real:** Diogo e Arthur estão os dois com 16 pontos. A planilha
põe o Diogo em 2º e o Arthur em 3º, e pela regra 5 isso precisa ser
justificado por distância no ano, depois duração no ano. Sem esses números, a
cascata não tem em que se apoiar — e o sistema, corretamente, **declara o
empate em vez de escolher**. Quando os dados anuais chegarem, é para conferir
que Diogo realmente fez mais distância no ano.
