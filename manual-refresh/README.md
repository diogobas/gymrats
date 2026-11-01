# Atualização manual pelo site

Serviço Cloudflare Worker independente do site estático. Autentica o administrador
e permite executar somente `refresh-data.yml` do repositório `diogobas/gymrats`,
na branch `master`. O cron-job.org e o processo de coleta continuam existentes.
O mesmo workflow aceita o fechamento de um snapshot revisado; não é necessário
adicionar secrets nem ampliar as permissões do token do GitHub.

## Fechamento de meses

Na área protegida, abra **Revisar e fechar mês**, selecione o mês e use
**Abrir / atualizar conferência**. Confira valores, bônus, participantes e
desempates, marque a confirmação e clique em **Confirmar e fechar**. Acompanhe
a execução até terminar. O mês passa a definitivo depois da publicação.

`GET /review` lista os meses pendentes. `GET /review?month=YYYY-MM` carrega
o resultado de um commit fixo; esses arquivos públicos são lidos do GitHub sem
credenciais de Contents. `POST /close` exige sessão, mês, revisão completa e
`confirmed: true`. O Worker recusa meses não pendentes, períodos incompletos,
empates e execuções concorrentes; o job valida novamente o commit, as sete
tabelas, nomes, valores, períodos, meses anteriores e o resultado publicado.
Uma revisão desatualizada precisa ser aberta e confirmada novamente.

O fechamento grava os dados em `data/months/` e preserva a prévia original.
Não coleta novos rankings nem substitui meses já fechados. Atualizações do
Worker usam `npm run deploy` e preservam os secrets existentes. Publique o
workflow atualizado antes de disponibilizar o novo painel.

## Ativação

É necessária uma conta Cloudflare. Dentro de `manual-refresh/`:

```sh
npm ci
npx wrangler login
```

Cadastre as quatro credenciais como secrets, digitando os valores nos prompts
do Wrangler (não coloque valores em comandos, arquivos versionados ou no chat):

```sh
npx wrangler secret put ADMIN_USERNAME
npx wrangler secret put ADMIN_PASSWORD
npx wrangler secret put SESSION_SECRET
npx wrangler secret put GITHUB_TOKEN
npm run deploy
```

- `ADMIN_USERNAME`: o usuário que você escolher para a tela.
- `ADMIN_PASSWORD`: uma senha longa e exclusiva, gerada no seu gerenciador de senhas.
- `SESSION_SECRET`: outro segredo aleatório de pelo menos 32 caracteres, exclusivo
  para assinar as sessões. Gere e guarde no gerenciador de senhas.
- `GITHUB_TOKEN`: token fine-grained limitado a `diogobas/gymrats`, com
  **Actions: Read and write**. Registre a expiração para renová-lo. Não use a
  credencial pessoal do `gh` nem o `GITHUB_TOKEN` temporário do Actions.

O Wrangler pode criar o Worker no primeiro cadastro de secret. Só publique após
cadastrar todos os valores. `SITE_ORIGIN` em `wrangler.jsonc` deve ser a origem
exata do site, sem caminho ou barra final: `https://diogobas.github.io`.

Copie a URL HTTPS retornada no deploy. Na raiz do repositório, configure essa URL
como **repository variable**, que é pública e não contém credenciais:

```sh
gh variable set VITE_REFRESH_URL --repo diogobas/gymrats --body 'https://gymrats-manual-refresh.SEU-SUBDOMINIO.workers.dev'
```

Publique as alterações deste repositório pelo fluxo habitual. Se o código já
estiver em `master`, reexecute o workflow `Deploy site` para incorporar a variável:

```sh
gh workflow run pages.yml --repo diogobas/gymrats --ref master
```

Abra `https://diogobas.github.io/gymrats/#/atualizar`, entre e use **Atualizar agora**.
Confirme no painel a conclusão e abra o placar atualizado. Não há link nas abas
públicas; salve o endereço nos favoritos.

## Segurança e operação

O token do GitHub e a senha ficam apenas nos secrets do Worker. O login emite
uma sessão assinada de quinze minutos; o navegador guarda o token somente na
memória, sem localStorage, sessionStorage ou cookies. Recarregar exige novo login.
**Sair** apaga a sessão deste navegador; um token copiado permanece válido até
expirar. Para revogar todas as sessões imediatamente, troque `SESSION_SECRET`.
As comparações de credenciais usam verificação HMAC. As respostas não são cacheadas
e não repassam erros ou conteúdo privado do GitHub.

Há limites de cinco tentativas de login por IP por minuto e um disparo manual
por minuto, por localidade Cloudflare. São limites aproximados da plataforma,
não um bloqueio global. O serviço procura execuções ativas antes de disparar;
requisições simultâneas em localidades diferentes ainda podem gerar mais de uma
execução. O grupo de concorrência do workflow serializa as coletas.

CORS aceita apenas a origem configurada; a autenticação é obrigatória mesmo para
clientes fora do navegador. O cliente recebe só o ID, estado, conclusão, horário
e link das execuções. O caminho oculto é uma conveniência, não uma credencial.

Se uma solicitação falhar ou expirar, consulte o Actions antes de tentar de novo:
o GitHub pode ter aceitado o disparo antes da interrupção da conexão.

## Verificação local

```sh
npm test
npx wrangler deploy --dry-run
```

Os testes usam credenciais fictícias e respostas sintéticas; não fazem coleta,
disparo real ou publicação. Para desenvolver a interface, configure
`VITE_REFRESH_URL` no ambiente do Vite. O Worker aceita apenas `SITE_ORIGIN`;
para um teste local integrado, use `.dev.vars` (ignorado pelo Git) com as quatro
credenciais de teste e `SITE_ORIGIN=http://localhost:5173`, e execute `npm run dev`.
Nunca conecte um ambiente de testes ao GitHub com credenciais reais sem intenção
de executar o workflow.

Referências: [API de workflows do GitHub](https://docs.github.com/en/rest/actions/workflows),
[secrets de Workers](https://developers.cloudflare.com/workers/configuration/secrets/)
e [limites de requisições](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/).
