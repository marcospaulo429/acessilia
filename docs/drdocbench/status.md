# DrDocBench — checkpoint e retomada na máquina GPU

Atualizado em **07/09/2026**. Este arquivo descreve o estado verificado;
[PLANO.md](PLANO.md) descreve os objetivos. Não confundir protótipos com migração
concluída. A decisão do usuário é **continuar implementação e experimentos na
máquina potente**, usando **uv para criar ambientes**, sem esperar concluir tudo
neste Mac.

**Autorização posterior do usuário (07/09/2026):** commitar este checkpoint e
publicar `feat/drdocbench-toolbox` no fork do Core, sem PR. DrDocBench e
OmniDocBench podem continuar como clones dos oficiais, sem novos forks. As
anotações abaixo sobre árvore não commitada descrevem o estado pré-publicação;
na máquina remota conferir o commit recebido com `git log -1`.

## 1. Regras para quem retomar

- Não commitar nem fazer push futuramente sem consentimento explícito; não abrir PR.
- O commit/push deste checkpoint foi autorizado; isso não autoriza futuras publicações.
- Core e Toolbox usam forks do usuário. DrDocBench e OmniDocBench podem ser
   clonados diretamente dos oficiais, conforme dispensa explícita do usuário.
   Para outros repositórios, manter a orientação de forks e confirmar disponibilidade.
- Nunca colocar tokens, senhas, imagens do dataset ou modelos no Git.
- Envio ao EvalAI e chamadas pagas de API exigem autorização específica.
- Código, comentários e documentação da Toolbox em inglês; Core pode usar português.
- Não prometer melhora de score. Resultados negativos também são resultados.

## 2. Git e o que precisa ser transportado

| Repositório | Branch / revisão verificada | Estado |
|---|---|---|
| Core, fork `marcospaulo429/acessilia` | `feat/drdocbench-toolbox`, HEAD `5e444c4` | Merges concluídos (`1759843` e `5e444c4`); implementação nova e estes documentos ainda não commitados |
| Toolbox, fork `marcospaulo429/acessilia-toolbox` | Branch **local** `feat/providers-drdocbench`, `489c691ad819d04fd2a112f5b5d65778009dee25` | Árvore limpa; nenhum novo provider implementado |
| DrDocBench, upstream `2077AI/DrDocBench` | `87b06ea3676e52366a08066cb104b56da83ec1c6` | Clone raso em `third_party/`, ainda com origin oficial |
| OmniDocBench, upstream `opendatalab/OmniDocBench` | `193627ae9e97d89188468ed1ee3b7a856ff76044` | Clone raso em `third_party/`, ainda com origin oficial |

Não criar forks dos avaliadores: usar `2077AI/DrDocBench` e
`opendatalab/OmniDocBench` nas revisões registradas acima. A ausência de forks
não é mais um bloqueio. Não publicar alterações nos repositórios oficiais.

Transferência autorizada:
1. Commitar o checkpoint parcial e fazer push da branch do Core para `origin`.
2. Toolbox pode recriar a branch local a partir da revisão acima: não há mudanças
   novas a transportar nesse repositório.
3. Na máquina remota, conferir que o clone da branch contém este arquivo **e**
   os módulos novos. Conferir commit e árvore limpa; não refazer merges.

`third_party/`, `var/data/`, `var/reports/` e `var/submissions/` são ignorados.
Clonar o Core não traz dataset, modelos, métricas brutas nem outros repositórios.
Não há necessidade de copiar esses volumes do Mac: recriá-los no destino.

**Agentes:** `.github/agents/main.agent.md` também é ignorado pelo Git. Foi
atualizado localmente para uv, mas não será levado no commit normal. Não forçar
inclusão de todos os agentes. O prompt da seção 7 e o catálogo do plano permitem
retomar com o agente padrão, mesmo sem agentes customizados instalados.

## 3. Estado por frente e subagente

| Papel | Estado / último artefato | Próximo aceite / bloqueio |
|---|---|---|
| SA-00 infraestrutura | Plano apenas; nenhum compose GPU específico criado | Descobrir GPU/VRAM, RAM, disco, SO; validar GPU no container; subir Docling + Toolbox primeiro |
| SA-01 Git | Merges concluídos, publicação do checkpoint autorizada | Conferir commit remoto; avaliadores oficiais dispensados de fork |
| SA-02 dataset | Loader, GT adapter e downloader existem | Fixar revisão, inventário e checksums; validar GT ausente, tipos/ids e ordenação numérica |
| SA-03 avaliador | Wrapper executado no Mac sem CDM | Corrigir métricas, paths e isolamento; instalar/testar CDM no Linux |
| SA-04 renderer/submissão | Implementação inicial com testes sintéticos | Revisar preservação de células vazias/rótulos, delimitadores/fences e validação estrita |
| SA-05 provedores | Fork Toolbox preparado; **nenhum adapter novo** | Generalizar saídas do executor antes de registrar capacidades não estruturais |
| SA-06 registro de ações | Protótipo isolado + mocks; cliente genérico novo | Contrato HTTP real, identificadores PDDL seguros, integração com executor/orquestrador |
| SA-07 estado/domínio v3 | Não iniciado | WorldState, domain composer, problem builder, FD e VAL reais |
| SA-08 reflexão | Não iniciada na arquitetura nova | L1/L2/L3, candidatos ≠ validados, limites de tentativas/custo e fallback humano |
| SA-09 baselines | Nenhuma inferência nova medida | Runner de provedores, inferência single-page, holdout por documento e E0–E2 |
| SA-10 experimentos planner | Não iniciado | E3–E5 após baselines e loop real |
| SA-11 submissão | Empacotador existe; nenhum envio | Validação oficial do contrato e autorização para enviar |
| SA-12 acessibilidade | Código legado de fórmulas preservado | Providers de MathML/MathCAT, verificar pt-BR, benchmarks antes/depois |
| SA-13 relatório | Plano e este checkpoint | Resultados reais, revisões, recursos/licenças e limitações |

As três chamadas de subagentes para revisão retornaram resultado desconhecido.
**Não contar suas tarefas como entregues nem seus testes como executados.**

### Arquivos já presentes

- [Dataset e adaptação de GT](../../backend/benchmarks/drdocbench/dataset.py),
  [GT adapter](../../backend/benchmarks/drdocbench/gt_adapter.py) e
  [submissão](../../backend/benchmarks/drdocbench/submission.py).
- [Renderer](../../backend/export/renderers/drdocbench_markdown.py),
  [registro de ações](../../backend/core/execution/action_registry.py) e
  [cliente Toolbox](../../backend/tools/toolbox_client.py).
- [Download](../../scripts/drdocbench/download.py),
  [avaliação](../../scripts/drdocbench/evaluate.py),
  [round-trip](../../scripts/drdocbench/check_gt_roundtrip.py) e
  [empacotamento](../../scripts/drdocbench/pack_submission.py).
- [Testes de dataset](../../tests/test_drdocbench_dataset.py),
  [renderer](../../tests/test_drdocbench_markdown.py),
  [submissão](../../tests/test_drdocbench_submission.py) e
  [ações](../../tests/test_action_registry.py).

## 4. Evidências e limitações — não confundir com score

- Última suíte leve registrada antes do handoff: **233 passed, 8 deselected,
  5 warnings**, com exclusão do marcador `docling`, no ambiente Poetry existente
  do Mac. Não foi repetida nesta etapa documental nem no Linux; alterações finais
  do avaliador ocorreram depois daquela execução. Reexecutar na máquina remota.
- Última contagem local: **986 imagens de página em dev e 132 em test**. O
  download estava em andamento; essas contagens não comprovam integridade ou
  presença de todos os JSON/Markdown. Revisão do dataset ainda não fixada.
- Não iniciar downloads duplicados no Mac. No Linux, iniciar um novo download
  com revisão fixada e conferir inventário, não apenas número total de JPGs
  (há também recortes em `imgs/`).
- Ambiente de avaliação macOS: uv Python 3.10, OmniDocBench editable, `mmeval`
  e `rapidfuzz` instalados adicionalmente. Não há lock completo dessa instalação.
- Os ensaios locais usaram Markdown de GT ou GT → canônico → Markdown contra
  as próprias referências. Isso avalia serialização/matching, **não inferência**.
  Discrepâncias ainda precisam de investigação; não atribuir um teto ao matcher.
- Wrapper atual usa distância de edição como substituto de CDM ausente e média
  dos componentes agregados. **Não usar esse número como Overall do desafio.**
  O Overall correto calcula média dos componentes disponíveis por página e
  depois média das páginas pontuáveis. Verificar também escala de CDM na fonte.
- A opção `--num_pages 1` não existe na revisão do avaliador. O wrapper usa
  `{document_id}_page_{N}-{N}.md` para representar uma página.

## 5. Correções prioritárias antes de experimentos caros

1. **Toolbox:** `CapabilityExecutor.execute()` sempre chama
   `build_processing_manifest` após o adapter. Saídas LaTeX, HTML de tabela,
   imagem renderizada ou relatório exigem contrato genérico versionado com
   compatibilidade. YAML sozinho não implementa essas capacidades. Inspecionar
   REST, modelos de resultado e normalização antes de mudar o Core.
2. **Cliente/ações:** conferir JSON versus multipart e parâmetros reservados;
   rejeitar resposta não objeto/JSON inválido; validar capacidade/provedor.
   Registro não deve anunciar capacidades inexistentes nem escolher provedor
   implicitamente no lugar do planner. Custos/duplicatas/ids precisam de testes.
3. **PDDL:** não interpolar ids arbitrários, `@` ou pontos em símbolos. Validar
   fragmentos da Toolbox (tipagem/parâmetros atuais são suspeitos) com ferramentas
   reais antes de compor domínio por bloco. Manter v2.2 funcional. O modelo
   `MethodResult` exige `success => validated`: não usá-lo para um candidato
   ainda não revisado. Tentativas devem identificar ação/capacidade/provedor.
4. **Dados/submissão:** tipos estritos (`bool`, float ou string não são número
   de página válido), inventário vazio deve falhar, duplicados e paths com
   traversal devem ser rejeitados. Tratar registros/JSONL malformados. GT ausente
   não é página em branco. Revisar exclusão de `page_footnote`/`aside_text`.
5. **Renderer:** preservar células vazias também no fallback; figure transcrita
   não deve ser descartada antes da renderização; nunca usar alt-text como texto
   do desafio. Testar fórmulas inline/display, fences dentro do código e páginas
   totalmente vazias. Não executar HTML/LaTeX arbitrário no host.
6. **Avaliação:** isolar diretórios e rejeitar reutilização que misture execuções;
   validar ids/nome da execução; separar métricas proxy de CDM e diagnóstico de
   pontuação oficial. Registrar imagens avaliadas, revisões, configuração e tempos.
7. **Experimentos:** separar ajuste e holdout por documento/fonte. GT adapter e
   oracle nunca entram na inferência ou escolha de candidatos no holdout/test.
   Render-and-compare é hipótese a testar, não garantia de correção.

## 6. Bootstrap remoto incremental com uv

**Ainda não executado no destino. Não é um ambiente reproduzido/validado.**

1. Conferir branch e checkpoint, depois GPU/modelo/VRAM, SO/arquitetura, RAM,
   disco e driver. Não escolher tamanho de VLM ou lote sem esses dados.
2. Recriar o layout da seção 3 do plano, mantendo outros repositórios dentro
   de `third_party/` porque os scripts usam esses caminhos relativos ao Core.
3. Criar com `uv venv --python 3.11 .venv` no Core; criar outro ambiente Python
   3.11 na Toolbox; criar `third_party/.venv-eval` com Python 3.10. Não reutilizar
   o `.venv` da raiz do Mac: foi observado Python **3.9.6**, incompatível com o
   requisito do projeto. Não recriar nem apagar ambientes existentes sem conferir.
4. Instalar o Core editable com `uv pip install --python .venv/bin/python -e .`.
   Seu manifesto ainda é Poetry; grupos dev não são automaticamente instalados
   por esse comando. Resolver/instalar dev respeitando as restrições do
   [pyproject.toml](../../pyproject.toml). Há versões mínimas de pacotes a verificar
   contra Python 3.11 (por exemplo NumPy 2.4.6): se o resolver falhar, registrar
   o erro e corrigir com testes; não trocar silenciosamente a versão do Python.
5. Na Toolbox, instalar editable com extras `dev` em seu próprio ambiente uv.
   Não instalar Docling/PyTorch dentro dela: isolamento de providers é requisito.
6. No avaliador Python 3.10, instalar o fork de OmniDocBench editable e verificar
   `mmeval`, `rapidfuzz`, dependências do wrapper (`PyYAML`) e downloader
   (`huggingface_hub`). Fixar a resolução que funcionar; não copiar binários macOS.
7. Rodar testes leves no Core e unitários da Toolbox **antes** de baixar modelos.
   Registrar comandos, versões e resultados. Instalar extras Docling no Core
   apenas para caminhos legados/benchmarks que os exijam.
8. Subir apenas Docling-serve + Toolbox; tags/digests, rotas de saúde e payloads
   devem ser verificados no código/documentação da revisão escolhida. Driver e
   Container Toolkit são do host; executar instalações privilegiadas só pelo
   usuário. Não pedir senha ao agente.
9. Rodar uma página real do dev → estrutura → Markdown. Corrigir harness/CDM,
   avaliar uma amostra pequena e só depois expandir provedores e experimentos.
10. Instalar Fast Downward/VAL em seus forks quando SA-07 começar; confirmar
    suporte das features PDDL usadas. Renderers devem rodar em sandbox sem rede,
    segredos ou shell escape, com limites de tempo/memória e arquivos temporários.

Runtimes CUDA conflitantes devem usar containers/ambientes por provedor. uv gere
ambientes Python; não substitui driver NVIDIA nem Container Toolkit. Registrar
versões/digests/licenças conforme cada caminho for validado, sem inventar tags.

## 7. Prompt para colar no agente da máquina remota

> Continue o trabalho DrDocBench + Core/Toolbox nesta máquina. Leia primeiro
> `docs/drdocbench/status.md` e depois `docs/drdocbench/PLANO.md`. Verifique o estado
> real do clone: merges já foram feitos e o código novo é um protótipo, não a
> migração completa. Não refaça merges e não confunda diagnóstico de GT com score
> de um modelo. Use uv para criar ambientes separados (Core 3.11, Toolbox 3.11,
> avaliação 3.10). Descubra hardware/driver e dependências antes de instalar.
> Use os forks de marcospaulo429 para Core/Toolbox e os repositórios oficiais
> 2077AI/DrDocBench e opendatalab/OmniDocBench para avaliação (fork dispensado).
> Não faça novos commits/push sem meu OK, não abra PR nem envie submissões ou
> chame APIs pagas sem autorização. Não peça segredos no chat.
>
> Primeiro faça SA-00/SA-01 e uma revisão dos problemas da seção 5. Divida trabalho
> independente entre subagentes com propriedade exclusiva de arquivos e relatório
> de testes. Os nomes do catálogo são papéis: use agentes disponíveis, não assuma
> que os arquivos locais de agentes vieram no clone. A integração de compose e
> registries compartilhados é responsabilidade do orquestrador. Na Toolbox,
> escreva código/comentários/docs em inglês.
>
> Priorize um caminho real Docling → Toolbox → Core → Markdown numa página do dev,
> depois avaliação single-page confiável numa amostra pequena. Generalize o
> contrato de saída da Toolbox antes dos providers de fórmulas/renderização.
> Continue com WorldState/PDDL/reflexão e provedores segundo as dependências do
> plano. Mantenha v2.2 funcionando; candidato produzido não significa validado.
> Separe ajuste e holdout por documento; jamais use GT/test para escolher saídas.
> Atualize este status com evidências, bloqueios e testes efetivamente executados.

## 8. Pendências que dependem do usuário

- Commit e push deste checkpoint já autorizados; verificar publicação no remoto.
- Forks dos avaliadores dispensados; usar oficiais nas revisões registradas.
- Disponibilizar a máquina/VS Code remoto; hardware ainda não informado.
- Confirmar orçamento/APIs e autorizar envios ao desafio apenas quando necessário.

Não é necessário informar senhas/tokens ou instalar todos os provedores antes de
retomar. É possível começar pela validação do ambiente e pelo caminho Docling.