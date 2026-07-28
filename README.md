# GymRats — apuração mensal

Apura a classificação mensal de uma competição fitness feita no app GymRats e
publica o resultado num site estático que os competidores acessam.

O GymRats não tem API pública nem versão web, e a exportação de dados é paga.
A entrada, portanto, são prints de tela do celular.

## A ideia

Dois públicos, e a arquitetura reflete isso.

**O admin**, uma vez por mês: sobe os prints pelo celular, confere o que o OCR
extraiu, corrige e gera a apuração. Roda localmente, na máquina dele.

**Os competidores**, a qualquer momento: só leem as tabelas. Site estático, sem
backend, sem banco, custo zero.

Ao fechar uma apuração, o backend escreve os JSONs de resultado dentro da pasta
pública do frontend. Commit, e o site republica.

## Como é feito

- **Backend:** Python + FastAPI, só local. Concentra OCR e apuração.
- **Frontend:** React + Vite. Um código-base, duas fontes de dados
  intercambiáveis por variável de ambiente — a API local, ou JSONs servidos
  junto com o build. No modo estático a interface de upload não existe, nem
  entra no bundle.
- **Persistência:** arquivos JSON em `data/`, versionados no git e editáveis à
  mão.
- **Deploy:** build estático no GitHub Pages.

Quatro camadas com fronteiras explícitas, para qualquer uma poder ser trocada
sem mexer nas outras: núcleo de apuração (Python puro, sem I/O), ingestão de
prints (plugável), OCR (plugável) e a API, que só orquestra.

## Estado

O projeto começa aqui. A implementação chega por branch, nesta ordem:

1. Núcleo de apuração e seus testes
2. Modo estático do frontend
3. Ingestão por upload e a tela de conferência
4. OCR

Cada branch traz sua própria documentação. Este README é substituído pela
versão completa no primeiro merge.
