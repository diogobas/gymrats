# Coletor experimental GymRats

Coletor independente, em Python 3.11+ e sem dependências externas. O coletor não
importa o backend. A prévia local reaproveita o núcleo de apuração existente.
O coletor e a prévia não escrevem em `data/`. O importador explícito descrito
abaixo salva os dados revisados e regenera o site local. Execute os comandos
abaixo na raiz do repositório. Pode usar `.venv/bin/python` no lugar de `python3`.

O clube padrão é **Gymrats 2026!**, ID `2504035`.
`members`, `rankings` e `collect-month` usam esse clube quando o ID é omitido.
Para outros anos, informe o ID correspondente, obtido com `challenges`.
O admin continua limitado ao clube de 2026; o importador abaixo permite
trazer coletas históricas revisadas para o site. Código de convite e links
privados não são necessários para as consultas autenticadas.

## O que já funciona e o que falta validar

- Login por código enviado ao e-mail ou por e-mail/senha; entrada de token
  existente ou importação de sessão de um HAR local.
- Comandos `account`, `challenges`, `members` e `rankings`, com parâmetros
  identificados no APK da versão `2026.10.25`.
- Consultas GET com filtros, timeout, sem redirects e sem retentativas automáticas.
- Respostas JSON com horário UTC, rota, filtros e versão usados na coleta.
- Busca offline de candidatos a rotas em APK, Dex ou bundle JavaScript/Hermes.
- Testes offline do transporte, armazenamento e tratamento de credenciais.

**Login por código e coleta de junho foram validados com a conta gratuita.**
As cinco métricas retornaram 15 participantes, igual à contagem atual do grupo.
Dos 58 valores transcritos nos arquivos antigos, 57 coincidem após arredondar a
API para duas casas decimais. Há uma divergência em hustle que não altera a
classificação mensal. Veja a [evidência da análise](RESEARCH.md).

## Coletar um mês com um comando

```sh
python3 experiments/gymrats_collector/collector.py collect-month 2026-06
```

O comando consulta as cinco métricas mensais e os dois desempates anuais,
com meio segundo entre requisições, sem
limitar o número de linhas. Cada resposta fica em `.local/responses/`, e um
manifesto em `.local/collections/<execução>/manifest.json` registra os arquivos,
as métricas e as contagens. Os valores originais da API são preservados.
O formato anterior com ID explícito continua válido, por exemplo
`collect-month 2504035 2026-06`.

A coleta só fica `complete` quando todas as respostas têm sucesso, valores
numéricos finitos, IDs únicos e o mesmo conjunto de participantes. Falha ou
mudança de participantes mantém o manifesto `partial`, preservando o que já
foi coletado. Essa consistência não garante presença de ex-membros do grupo.

**Regra definida: distância e duração anuais vão de 1º de janeiro até o último
dia do mês escolhido.** Essa coleta já acontece por padrão. A opção antiga
`--include-year` continua aceita; `--month-only` coleta somente as cinco métricas
mensais para pesquisa e não basta para gerar a prévia.

## Conferir a apuração antes de salvar

Depois de coletar:

```sh
python3 experiments/gymrats_collector/preview.py 2026-06
```

A prévia usa a execução mais recente desse mês e exige sete rankings completos,
com o corte anual correto. Não mistura execuções nem ignora uma coleta parcial
mais recente. Para escolher uma execução específica, passe `--manifest CAMINHO`.

O terminal mostra as classificações mensal e anual. Ao lado do manifesto fica
`preview.json`, com as tabelas candidatas para revisão, os mesmos formatos de
resultado usados pelo site, diferenças contra os arquivos antigos e meses
ausentes no acumulado. Valores de entrada não são arredondados para calcular;
a comparação com a transcrição antiga usa duas casas decimais.

Nomes desconhecidos, participantes inconsistentes e datas divergentes impedem a
prévia. O acumulado considera somente os meses até o escolhido e usa o cadastro
local para o bônus de calorias. Se faltarem meses anteriores, isso é indicado
explicitamente; não são inventados resultados.

O candidato ainda não é salvo em `data/months/` nem publicado. Os snapshots
antigos continuam preservados até serem revisados.

## Sua conta usa Apple

Use o login por código no **e-mail exato da sua conta existente**:

```sh
python3 experiments/gymrats_collector/collector.py login-email
```

Ele pede o e-mail, solicita um código ao GymRats e espera você digitá-lo no mesmo
terminal, sem eco. Código, nonce e resposta de login não são gravados; apenas o
token de sessão resultante é guardado. Se você usou Ocultar Meu E-mail na Apple,
o endereço vinculado pode terminar em `privaterelay.appleid.com`. Confira o e-mail
vinculado à conta antes de usar o comando. O fluxo funcionou com a conta Apple
usada neste projeto; não use um endereço diferente para
evitar entrar em outra conta. Este não é o fluxo OAuth da Apple.

O comando `login` continua disponível para uma senha **do GymRats**, não uma senha
Apple. Não coloque sua senha Apple nele.

Se o login por código não servir, há duas entradas para uma sessão já existente:

```sh
# Solicita um token GymRats existente no terminal, sem mostrá-lo.
python3 experiments/gymrats_collector/collector.py auth-token

# Ou importa Authorization e x-signature de uma captura HAR local.
python3 experiments/gymrats_collector/collector.py auth-har experiments/gymrats_collector/.local/capture.har
```

Esses comandos **não obtêm uma sessão Apple por conta própria**. O HAR precisa
conter uma consulta autenticada para `https://www.gymrats.app/api/`. Somente uma
sessão é aceita, e cabeçalhos de outros serviços são ignorados. A validade da
sessão é testada na primeira consulta. O token necessário é o do GymRats, não o
identity token da Apple.

Uma captura pode ser feita com um proxy de inspeção local, mas a pesquisa
anterior encontrou certificate pinning no Android. Não temos confirmação sobre
a versão atual do iOS; por isso a captura não é um procedimento garantido.
Não é necessário resolver isso para começar o mapeamento offline abaixo.

## Mapear rotas sem autenticação

Use um APK ou bundle que você tenha obtido e coloque-o em `.local/`, para não
versionar o aplicativo. O programa apenas lê o arquivo; não o instala ou executa.

```sh
mkdir -p experiments/gymrats_collector/.local
python3 experiments/gymrats_collector/collector.py discover experiments/gymrats_collector/.local/app.apk
```

O resultado fica em `.local/routes.json`, com método, caminho candidato, arquivo,
offset e contexto. Comece procurando `challenges`, `leaderboard`, `ranking`,
`stats`, `score`, `sign_in` e `sign_interop`. Os contextos podem ajudar a encontrar
o ponto da chamada num bundle decompilado, incluindo o fluxo Apple.

Os candidatos **não são automaticamente consultados**. Hermes pode concatenar
strings e produzir caminhos com sufixos indevidos; é necessário conferir a
chamada e seus parâmetros. Se não encontrar nada, pode ser preciso decompilar
o bundle ou Dex antes de repetir a busca. XAPK com o APK principal chamado
`com.hasz.gymrats.app.apk` é suportado diretamente. O limite do arquivo compactado
é 256 MiB; entradas individuais e bundles têm limite de 64 MiB.

## Fazer a primeira consulta

Depois de obter uma sessão, confirme a identidade e consulte os grupos:

```sh
python3 experiments/gymrats_collector/collector.py account
python3 experiments/gymrats_collector/collector.py challenges
```

Cada comando mostra onde salvou o JSON. Confira no arquivo de `account` se é sua
conta existente e no arquivo de `challenges` os IDs e os grupos disponíveis. Não
é necessário colar tokens ou esses arquivos no chat; eles ficam no workspace.
Não foi confirmado se a listagem de grupos exige filtros adicionais.

Com o ID real do seu grupo, consulte os membros.
Substitua `123` pelo ID do grupo ao qual sua conta pertence. O número não é o
código de convite. Não tente descobrir IDs de outros grupos por enumeração.

```sh
python3 experiments/gymrats_collector/collector.py members 123
```

As opções globais devem ficar **antes do subcomando**. `--app-version` usa por
padrão `2026.10.25`, a versão do APK analisado. `--timezone` usa
`America/Toronto`; ajuste ao fuso de apuração do campeonato antes de comparar
recortes mensais. `--platform` usa `Android`, o cliente analisado, mesmo se sua
conta foi criada no iPhone. `members` usa `api-version: 2`; `get` permite escolher
essa versão com a opção global `--api-version 2`.

Para consultar cada métrica:

```sh
python3 experiments/gymrats_collector/collector.py rankings 123 --score-by points --start-date 2026-06-01 --end-date 2026-06-30
```

Troque `points` por `days`, `calories`, `distance` ou `duration`. A consulta usa
`disable_format=true`, como o código nativo. As datas são enviadas como
`YYYY-MM-DD`, sem converter fuso; a inclusão exata dos limites ainda precisa ser
conferida contra o app. Sem datas, vale o período padrão do servidor, não um mês
presumido. `--limit 100` limita a resposta; sem a opção, o parâmetro é omitido,
como permite o método nativo. Não foi confirmado se o servidor aplica limite
próprio. Não há paginação automática do ranking.

Para outras rotas já confirmadas, use `get` com filtros separados:

```sh
python3 experiments/gymrats_collector/collector.py --platform iOS --app-version VERSAO_DO_SEU_APP get /challenges/123/members
```

Adicione `--param chave=valor` para outros filtros identificados na chamada real.
A listagem de membros usa `next` para continuar a página e `q` para busca,
conforme o APK. A ferramenta não percorre páginas automaticamente e não transforma
os dados. Uma resposta parcial não comprova que todos os membros foram coletados.

Se você também tiver e-mail/senha próprios do GymRats:

```sh
python3 experiments/gymrats_collector/collector.py login
```

Não foi validado se contas criadas com Apple podem adicionar essa forma de login.

## Dados locais e diagnóstico

Tudo gerado fica em `.local/`, ignorado pelo Git:

- `session.json`: token e identificador de sessão, arquivo com permissão `0600`.
  A senha não é salva. O token é salvo em texto, sem criptografia adicional.
- `responses/*.json`: corpo JSON com campos comuns de credenciais removidos e
  ocorrências do token de sessão substituídas. Nomes, IDs e métricas são mantidos
  para análise; os arquivos continuam sendo privados, não anonimizados.
- `routes.json`: candidatos de rotas; `discover` substitui o resultado anterior.

O terminal mostra campos, tipos e tamanho das listas, sem imprimir valores de
participantes. Erros HTTP não exibem o corpo da resposta. `401` pede autenticação;
`403` indica acesso recusado e não é tratado como sucesso; `404` exige revisar a
rota; `429` exige aguardar. Não há retentativas ou tentativa de contornar bloqueios.

```sh
python3 experiments/gymrats_collector/collector.py logout
```

Isso remove apenas a sessão local, sem revogar o token no servidor ou apagar os
dados coletados. Um HAR pode conter credenciais de outros serviços: mantenha-o
também em `.local/` e remova-o quando não for mais necessário.

## Critério para integrar ao projeto

1. Autenticar sua conta gratuita e ler o grupo correto.
2. Identificar as cinco métricas, suas unidades e a paginação completa.
3. Validar fuso e recortes mensal/anual contra o aplicativo.
4. Guardar uma amostra anonimizada como fixture e reproduzir um mês conhecido.
5. Só então criar um adaptador para as tabelas do backend.

## Verificação offline

```sh
.venv/bin/python -m pytest -q tests/test_experimental_collector.py
.venv/bin/ruff check experiments/gymrats_collector tests/test_experimental_collector.py
.venv/bin/ruff format --check experiments/gymrats_collector tests/test_experimental_collector.py
```

## Referência

[FreeRats: engenharia reversa da API do GymRats, 25/02/2026](https://guilhermegarcia.dev/blog/freerats-reverse-eng/).
A referência demonstra `/tokens`, `/account/export` e identifica a rota de membros
no APK. Não demonstra os rankings necessários ao campeonato nem o login Apple.


## Importar um mês de outro ano para o site

Depois de coletar com o ID correto do desafio, confira os nomes e os bônus no
cadastro `data/participants.json`. O importador usa as regras atuais de apuração;
ele não deduz regras antigas nem cadastra participantes automaticamente.

Primeiro veja o resultado sem gravar (substitua `CAMINHO_DO_MANIFESTO`):

```sh
python3 experiments/gymrats_collector/import_month.py \
  --manifest CAMINHO_DO_MANIFESTO --challenge-id 2404482
```

Depois de conferir, execute o mesmo comando com `--commit`. Ele salva
`data/months/YYYY-MM.json` e regenera `frontend/public/data/`, incluindo o ano no
seletor. O ID é obrigatório e precisa coincidir com o manifesto e as respostas.
Não é necessário rodar `gymrats.publish` separadamente.

Se faltarem meses anteriores, `--commit` exige também
`--allow-incomplete-season`; o acumulado público mostra quais meses faltam.
Para substituir um mês já salvo, use `--replace` após revisar a prévia.
Somente meses encerrados são aceitos. As respostas privadas permanecem na pasta
`.local/`; apenas as tabelas revisadas e a origem sem credenciais vão para o site.
Recarregue o frontend para atualizar o manifesto. Publicação remota continua
pelo fluxo Git e deploy.

Dezembro de 2025 (desafio `2404482`) foi importado com Ana e Isis cadastradas
com bônus de 20%, confirmado pelo admin. Janeiro a novembro também foram
importados após a confirmação de bônus para Juliana, Jéssica Felter e Leticia;
os outros oito novos participantes não recebem bônus. Os 12 meses de 2025
estão disponíveis e o acumulado considera o ano completo.


Maio a dezembro de 2024 também estão importados. O admin confirmou bônus de
20% para Laiury, Laura Beatriz e Lays; Luís Eduardo, Rafael Saba, Thiago Pena e
Vicente Jr não recebem bônus. Janeiro a abril não têm coletas disponíveis,
e o acumulado informa essa lacuna. Em maio, todas as dez contas retornaram
zero hustle. O admin autorizou desconsiderar hustle apenas em maio: a posição
mensal soma dias ativos e calorias, mantendo os bônus e os desempates.
`ignore_hustle: true` registra essa exceção no arquivo revisado; os valores
brutos de hustle continuam preservados e os outros meses mantêm a regra normal.
