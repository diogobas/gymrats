# Atualização diária e execução manual

O workflow **Atualizar dados** roda diariamente às **00:00 em America/Sao_Paulo**.
O GitHub pode atrasar o início em períodos de carga; não é uma garantia de execução
no segundo exato. Também pode ser iniciado em:

https://github.com/diogobas/gymrats/actions/workflows/refresh-data.yml

Selecione **Run workflow → master → Run workflow**. Não é necessário abrir o
admin local ou manter o computador ligado.

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
