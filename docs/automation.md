# Atualização diária e execução manual

O **cron-job.org** dispara o workflow **Atualizar dados** diariamente às
**00:07 em America/Sao_Paulo** pela API do GitHub. O cron interno do GitHub foi
retirado para evitar disparos duplicados e os atrasos observados no agendador.
Também pode ser iniciado manualmente em:

https://github.com/diogobas/gymrats/actions/workflows/refresh-data.yml

Selecione **Run workflow → master → Run workflow**. Não é necessário abrir o
admin local ou manter o computador ligado.

Para testar também a publicação quando o placar já estiver atualizado, marque
**force_publish** na execução manual. O mesmo parâmetro pode ser enviado pelo
cron-job.org no corpo `{"ref":"master","inputs":{"force_publish":true}}`.
Ele republica os dados validados sem alterar valores ou a data de corte. Restaure
o corpo habitual `{"ref":"master"}` após o teste.

## Disparo pelo cron-job.org

O job **8749614**, **GymRats - atualizacao diaria**, está ativo no
[console do cron-job.org](https://console.cron-job.org/). O teste de 29/10/2026,
agendado para 10:48 de São Paulo, foi disparado cerca de três segundos depois;
o GitHub aceitou o disparo com HTTP 200. A execução correspondente está em
[Actions](https://github.com/diogobas/gymrats/actions/runs/40885282051).
O workflow terminou com sucesso; a publicação foi dispensada porque não havia
alterações nos dados públicos.
Após o teste, o horário diário de 00:07 foi restaurado e confirmado.

Para recriar o agendamento ou renovar as credenciais:

1. Crie e confirme uma conta em <https://console.cron-job.org/>. Em **Settings**,
   gere uma **API key**.
2. Em <https://github.com/settings/personal-access-tokens/new>, crie um token
   **fine-grained** chamado `GymRats cron-job.org`, com acesso somente a
   **diogobas/gymrats** e **Actions: Read and write**. Anote a expiração para
   renová-lo antes do vencimento.
3. No terminal local, dentro deste repositório, execute:

   ```sh
   python3 scripts/setup_external_schedule.py credentials
   ```

   Cole as duas credenciais quando solicitado. A digitação fica oculta. Elas são
   gravadas em `.local/external-scheduler/credentials.json`, com permissão `0600`,
   fora do Git. Não envie os valores pelo chat.
4. Para criar ou atualizar o agendamento:

   ```sh
   python3 scripts/setup_external_schedule.py configure
   ```

   O script configura **POST**, **00:07**, **America/Sao_Paulo** e o destino
   abaixo. Ele verifica a configuração salva e reutiliza o job existente para
   evitar duplicatas. O token dedicado será armazenado no header privado do job
   no cron-job.org; a credencial pessoal do `gh` não é utilizada.
5. No console do cron-job.org, execute um teste do job e confira a execução
   correspondente no GitHub. Para consultar os horários e os últimos resultados:

   ```sh
   python3 scripts/setup_external_schedule.py status
   ```

O status exibe somente os campos de horário e resultado, sem headers ou tokens.
O script não dispara uma execução de coleta por conta própria. Se for necessário
restaurar o cron do GitHub como alternativa, evite manter os dois agendadores
ativos depois da validação.

Referência da integração: [API do cron-job.org](https://docs.cron-job.org/rest-api.html).

O workflow já aceita `workflow_dispatch`. Um agendador externo pode chamar a
API do GitHub diretamente; a coleta, os secrets e a publicação continuam no
Actions. Não é necessário hospedar um backend do GymRats.

A requisição diária às **00:07**, com fuso **America/Sao_Paulo**, é:

```text
POST https://api.github.com/repos/diogobas/gymrats/actions/workflows/refresh-data.yml/dispatches
Accept: application/vnd.github+json
Authorization: Bearer <token dedicado do GitHub>
Content-Type: application/json
X-GitHub-Api-Version: 2026-03-10

{"ref":"master"}
```

Use um personal access token **fine-grained**, limitado ao repositório
`diogobas/gymrats`, com **Actions: Read and write**. Guarde-o no campo de
credencial/header privado do agendador. Não reutilize a credencial pessoal do
`gh`, nem coloque tokens na URL ou em arquivos versionados. Registre a expiração
do token no serviço para renová-lo antes que o disparo pare de funcionar.

Antes de retirar o `schedule` do workflow:

1. Crie o agendamento externo e confirme o fuso e a próxima execução.
2. Execute um teste pelo próprio serviço externo.
3. Confira a execução `workflow_dispatch` correspondente no Actions e o resultado
   da publicação. Uma resposta HTTP de sucesso só confirma o aceite do disparo,
   não o sucesso da coleta.
4. Retire o bloco `schedule` do YAML somente após a validação, preservando
   `workflow_dispatch`. Isso evita duas execuções diárias.

O agendamento externo também não elimina uma eventual espera por runner no
Actions. O histórico de respostas está habilitado no cron-job.org. Acompanhe
separadamente as falhas HTTP no serviço e as falhas do workflow no GitHub.

Referências: [disparo de workflows pela API do GitHub](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
e [limitações do agendador do Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## O que ele atualiza

- Consulta os sete rankings até o dia anterior em São Paulo.
- Valida período, valores, participantes, nomes conhecidos e desempates.
- Atualiza apenas `data/previews/` e os JSONs públicos correspondentes.
- Executa a regressão e o build antes de versionar os dados.
- Publica no Pages explicitamente: pushes feitos com `GITHUB_TOKEN` não disparam
  outro workflow de push.
- Não faz commit quando os dados e o corte não mudaram.

O fechamento definitivo continua manual. Na virada do mês, a última prévia do
mês anterior recebe o corte do último dia e fica **Aguardando fechamento**.
Depois do primeiro dia completo do novo mês, o acumulado provisório inclui a
prévia completa anterior sem duplicá-la. Se o job perder a virada do mês,
recupera os períodos pendentes antes de publicar qualquer alteração.

O clube continua limitado a 2026. A rotina não cria uma temporada de 2027.
Quando todos os períodos elegíveis já estiverem completos, não há nova coleta.

## Credenciais e respostas originais

São usados dois repository secrets:

- `GYMRATS_SESSION_JSON`: somente o token e a assinatura da sessão GymRats.
- `GYMRATS_ARCHIVE_KEY`: chave aleatória independente para criptografar os
  artefatos que preservam as respostas originais e manifestos.

As credenciais não entram no código, no build público ou nos logs. O arquivo de
sessão temporário é removido ao terminar. Somente as capturas em `collections/`
entram no arquivo de auditoria; a sessão nunca é incluída. Os artefatos são
criptografados com GPG/AES256 e retidos por 30 dias no Actions, inclusive quando
a coleta parcial exige conferência. Nunca publique as respostas originais em
texto puro ou envie a chave de descriptografia junto com os artefatos.

A chave de auditoria gerada durante a configuração fica também em
`experiments/gymrats_collector/.local/daily-archive-key`, fora do Git. Preserve
uma cópia privada para poder consultar capturas antigas. Para descriptografar
um artefato baixado, com GPG instalado:

```sh
gpg --batch --pinentry-mode loopback \
  --passphrase-file experiments/gymrats_collector/.local/daily-archive-key \
  --output captures.tar.gz --decrypt gymrats-captures.tar.gz.gpg
```

## Falhas e renovação da sessão

Coleta incompleta, nomes novos, participantes divergentes, empates pendentes,
correções manuais ou falha de publicação interrompem o job. A versão anterior
do site permanece disponível. Consulte o run do Actions e retome a conferência
no admin local; a automação não altera cadastro nem bônus por conta própria.

Se a sessão expirar, faça login por código no admin local e renove o secret:

```sh
gh secret set GYMRATS_SESSION_JSON --repo diogobas/gymrats \
  < experiments/gymrats_collector/.local/session.json
```

Não coloque o token em comandos, prints, comentários ou no chat. Depois execute
**Run workflow** novamente. Se a chave de auditoria for rotacionada, preserve a
anterior para abrir artefatos já gerados.

## Validação offline

O CI continua sem sessão real. Os testes sintéticos cobrem datas de São Paulo,
virada do mês, recuperação de execução perdida, correções manuais, mudanças de
participantes, falhas parciais, rollback e exclusão da sessão do arquivo cifrado.
