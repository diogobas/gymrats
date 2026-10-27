# Análise local do GymRats 2026.10.25

Análise do XAPK fornecido pelo usuário e validação autenticada em 27/10/2026.
A análise estática inicial foi seguida de consultas de leitura usando a sessão
que o usuário autenticou localmente. Os dados de apuração não foram alterados.

## Resultado do teste real

- Login por código enviado ao e-mail funcionou para a conta criada com Apple.
- `/account` confirmou a conta esperada com `pro: false`.
- Os cinco rankings mensais foram consultados de `2026-06-01` até `2026-06-30`,
  sem `limit`, com `disable_format=true` e cada `score_by` identificado no APK.
- Todos retornaram 15 participantes, igual ao `member_count` atual de `/info`.
- Dias ativos são contagens, calorias são kcal, distância veio em km e duração
  em minutos, conforme os valores existentes de junho.
- Os valores de pontos e distância têm precisão maior que a exibida nos prints.
  Dos 58 valores transcritos, 57 coincidem após arredondar a resposta a duas casas.
- Divergência: hustle de Lorrana é `211.31` na transcrição antiga e
  `217.68260607439217` na resposta atual. Não há evidência para atribuir a causa
  a erro de transcrição, edição retroativa ou mudança de regra.
- Reapuração em memória com os valores completos da API reproduziu as dez
  posições e os totais de junho, mesmo com a divergência. Nenhum arquivo oficial
  do mês ou JSON publicado foi regravado.
- Respostas originais e relatório detalhado: `.local/responses/` e
  `.local/june-validation.json`, fora do Git.

A comparação valida esse mês e os membros atuais. Não prova a recuperação de
participantes que saíram ou a imutabilidade dos dados históricos. Ainda não foi
feita a integração ao backend.

### Verificação do recorte anual até junho

As consultas de distância e duração de `2026-01-01` a `2026-06-30` também
retornaram 15 participantes. Comparadas aos snapshots anuais antigos, coincidem
3 de 11 distâncias e 2 de 11 durações. Por exemplo, a distância anual de Diogo
veio como `963.02` km, contra `1026.13` km na transcrição antiga.

Os prints antigos usavam "Este ano" na data da captura, enquanto as consultas
novas têm corte explícito em 30/06. Recortes diferentes são uma hipótese para a
divergência, não uma causa comprovada. Os dados não foram substituídos.

Mesmo com esses números diferentes, a reapuração em memória preservou todas as
posições e totais do acumulado de janeiro a junho, inclusive o desempate entre
Diogo e Arthur. Relatório: `.local/june-year-validation.json`.

Decisão do usuário: limitar os critérios anuais ao **último dia do mês apurado**.
O coletor passa a buscar os dois rankings anuais por padrão. A prévia exige as
datas corretas nos arquivos de resposta e recalcula o acumulado apenas até o
mês escolhido. Nenhuma coleta usa a data atual como corte implícito.

## Proveniência

- Pacote e versão no manifesto: `com.hasz.gymrats.app`, `2026.10.25`, build `20261025`.
- SHA-256 do APK principal: `f289cc7237bf30e8f7d7d5cf39a3973b7c2f3a093a725e9e6e3ca9c8fb3c7003`.
- SHA-256 de `assets/index.android.bundle`: `e1d5cd45da375984b012ad786b39b310761179070e55ce0326a76e12600a4a90`.
- Hermes bytecode 98. Decompilação com `P1sec/hermes-dec` no commit
  `2e796663e1fedb93dca51060797ebf3327b3fedb`.
- Classes nativas analisadas com JADX 1.5.6. A classe `GymRatsApi` gerou três
  avisos/erros de decompilação em outros trechos; as conclusões registradas usam
  métodos cujas chamadas e parâmetros puderam ser lidos. Os artefatos ficam em
  `.local/`, fora do Git. Código decompilado não foi incorporado ao coletor.

## Autenticação por código

No bundle, `useEmailSignIn` chama `POST /accounts/email_confirmation` com
`email` e `locale`, lê `data.nonce` e guarda o nonce para o próximo passo.
A tela de código chama `POST /accounts/sign_in` com `token` (código digitado),
`nonce`, `region_code` e `language_locale`. A resposta é passada ao mecanismo
de login do app.

Referências locais: `decompiled.js`, função `useEmailSignIn` (~linha 361161),
rota `POST /accounts/sign_in` (~1135945) e função `submit` (~1136157).
Números de linha são auxiliares e podem mudar com a versão do decompilador.

O fluxo foi validado com o e-mail vinculado à conta Apple deste projeto.
Isso não demonstra que o servidor permite esse método para toda conta Apple, nem
implementa OAuth Apple. O usuário deve fornecer o endereço da conta existente,
incluindo o relay da Apple quando houver, e confirmar a identidade após o login.
Não foram testados efeitos de fornecer um e-mail sem conta existente.

## Rankings por métrica

O método nativo `GymRatsApi.rankings` monta:

| Item | Valor identificado |
|---|---|
| Método e rota | `GET /challenges/{id}/rankings` |
| Formatação | `disable_format=true` |
| Métrica | `score_by`, opcional no método nativo |
| Período | `start_date`, `end_date`, opcionais, formato `yyyy-MM-dd` |
| Quantidade | `limit`, opcional; omitido quando nulo |
| Retorno esperado pelo cliente | Lista de `Ranking` |
| Campos de `Ranking` | `account`, `score` (string), `rank` (inteiro opcional) |

`Challenge.ScoreBy.enumVal()` mapeia as métricas para `points`, `days`,
`calories`, `distance`, `duration`, `steps` e `workouts`.
Referências locais: `GymRatsApi.java`, método `rankings` (~5771–5815);
`Challenge.java`, `ScoreBy.enumVal()` (~567); `Ranking.java`.

O hook JS `useChallengeRankings` confirma a rota e os filtros de data/limite,
mas usa um limite padrão de 5 e não expõe `score_by`; o método nativo é a
evidência para esse parâmetro. Não há sinal de exigência de Pro nesses métodos
do cliente, o que não prova ausência de uma restrição no servidor.

## Grupos, identidade e membros

- `GET /account` aparece no bundle para a identidade da conta.
- `GET /challenges` aparece no bundle; o formato e os filtros para listagem dos
  grupos da conta ainda precisam ser conferidos no servidor. O mesmo caminho
  também aparece com `code` para prévia de convite; não confundir os dois usos.
- `GymRatsApi.memberList`: `GET /challenges/{id}/members`, cabeçalho
  `api-version: 2`, filtros opcionais `q` e `next`. O bundle lê `members` e
  `next` da resposta de dados para montar a listagem e sua continuação.
- `useChallengeGroupStats`: `GET /challenges/{id}/group_stats`, filtros
  `start_date` e `end_date`.
- `usePeriodicRankings`: `GET /challenges/{id}/periodic_rankings`, com
  `period` e `limit`. Valores válidos de `period` não foram investigados.

## Pendências para considerar a coleta válida

1. Conferir recortes e snapshots anuais, inclusive fuso e limites de data.
2. Definir o tratamento de participantes que saíram e de mudanças retroativas.
3. Guardar uma amostra anonimizada como fixture de contrato do servidor.
4. Conectar a coleta à revisão, preservando o cálculo já validado para junho.
