Excelente. Chegamos a um design robusto e completo. Abaixo está o plano consolidado e detalhado, estruturado como um documento de especificação técnica para a equipe de desenvolvimento.

---

### **Plano de Implementação Lógica: Framework de Serviços Conversacionais v1.0**

**1. Visão Geral e Conceitos Fundamentais**

**1.1. Objetivo**
Construir um framework back-end para a execução de serviços complexos e multi-passo. O framework é projetado para ser a principal "ferramenta" (tool) de um agente de IA conversacional, que interage com o usuário final. A cada turno da conversa, o agente consultará o framework, que por sua vez informará o estado atual do serviço e qual a próxima ação necessária.

**1.2. Princípios de Design**

*   **Declarativo:** A estrutura e o fluxo de um serviço são definidos como dados (uma configuração), não como código imperativo.
*   **Orientado a Estado:** O estado atual do serviço para um usuário é a única fonte da verdade que determina os próximos passos possíveis.
*   **Fluxo Condicional:** Um serviço é um grafo com ramificações e múltiplos finais possíveis, controlado por condições lógicas baseadas no estado.
*   **Hierárquico:** A estrutura de dados e os passos podem ser aninhados para representar entidades complexas do mundo real (`usuario.endereco.coordenadas`).
*   **Informativo:** A resposta do framework ao agente de IA deve ser rica em contexto, fornecendo não apenas a próxima pergunta, mas também um resumo completo do progresso.

**2. Componentes Principais e Estruturas de Dados**

**2.1. Definição do Serviço (`ServiceDefinition`)**
O "blueprint" imutável de um serviço.

*   **`service_name`**: Identificador único em string (ex: "pagamento_iptu").
*   **`description`**: Descrição geral do serviço.
*   **`steps`**: Uma lista contendo as definições do primeiro nível de passos (`StepInfo`).

**2.2. Definição do Passo (`StepInfo`)**
O átomo do framework, descrevendo um único nó no grafo do serviço.

*   **Identificação e Hierarquia:**
    *   **`name`**: Nome único do passo. Deve suportar uma notação que indique hierarquia (ex: `user_info` ou `user_info.address`).
    *   **`substeps`**: Uma lista de outras `StepInfo` para permitir aninhamento infinito.
*   **Interação e Coleta de Dados:**
    *   **`description`**: O texto que instrui o agente de IA sobre o que este passo faz ou o que ele precisa pedir ao usuário. Pode conter variáveis do estado (ex: "Encontrei estas dívidas: {found_debts.options}. Qual você escolhe?").
    *   **`payload_schema`**: A definição da estrutura (em formato JSON Schema) que este passo espera receber do usuário.
*   **Controle de Fluxo (Lógica do Grafo):**
    *   **`depends_on`**: Uma lista de nomes de outros passos que devem ser concluídos para que este passo possa ser ativado.
    *   **`condition`**: Uma expressão lógica em string a ser avaliada contra o estado do serviço (ex: `'search_debts.outcome == "DEBTS_FOUND"'`).
    *   **`is_end`**: Um booleano que marca este passo como um ponto final bem-sucedido do fluxo.
    *   **`required`**: Um booleano que indica a obrigatoriedade do passo.
*   **Execução de Lógica de Negócio:**
    *   **`action`**: Uma referência a uma função/método que executa a lógica de negócio do passo (ex: chamar uma API). Se um passo não tem `action`, ele é, por definição, um passo de coleta de dados do usuário.

**2.3. Estado do Serviço (`ServiceState`)**
Objeto mutável que armazena todos os dados de uma execução de serviço para um único usuário.

*   **Funcionalidade:** Deve operar como um dicionário aninhado.
*   **Requisito Chave:** Deve expor métodos para ler e escrever valores usando **notação de ponto** para navegar na hierarquia de dados (ex: `state.get('user_info.address.zip_code')`).

**2.4. Resultado da Execução da Ação (`ExecutionResult`)**
O contrato de retorno *interno* para toda `action`, usado pelo Orquestrador.

*   **`success`**: Booleano indicando o sucesso da ação.
*   **`outcome`**: Uma string que descreve o resultado semântico da ação (ex: "DEBTS_FOUND"), usado para alimentar as `condition`.
*   **`updated_data`**: Um objeto com dados a serem mesclados no `ServiceState`.
*   **`error_message`**: Mensagem de erro, caso `success` seja falso.

**3. O Orquestrador do Serviço (`ServiceOrquestrator`)**

O cérebro do framework e o único ponto de contato para o agente de IA.

**3.1. Ponto de Entrada Lógico**
O Orquestrador expõe uma função principal que recebe: `(service_name, user_id, payload_recebido)`.

**3.2. Fluxo de Execução Principal**

1.  **Carregamento:** Carrega a `ServiceDefinition` e o `ServiceState` do usuário.
2.  **Processamento da Entrada:** Se `payload_recebido` existir, valida-o contra o `payload_schema` do passo que estava pendente e atualiza o `ServiceState`.
3.  **Loop de Execução Automática:**
    *   O Orquestrador entra em um loop contínuo para executar todos os passos que não requerem intervenção do usuário.
    *   **a. Encontrar Próximo Passo Válido:** Em cada iteração, ele varre a árvore completa de `steps` e encontra o primeiro passo que satisfaça **todas** as seguintes regras:
        1.  Não foi concluído ainda.
        2.  Todos os seus `depends_on` foram satisfeitos.
        3.  Sua `condition` (se existir) é avaliada como verdadeira contra o `ServiceState`.
    *   **b. Decidir e Agir:**
        *   **Se um passo válido é encontrado e ele possui uma `action`:** A `action` é executada. O `ServiceState` é atualizado com o `ExecutionResult`. O loop **reinicia** para reavaliar o fluxo com o novo estado.
        *   **Se um passo válido é encontrado mas ele NÃO possui uma `action`:** O loop é **quebrado**. O framework precisa de dados do usuário.
        *   **Se nenhum passo válido é encontrado:** O loop é **quebrado**. O fluxo chegou a um fim.
4.  **Geração da Resposta para o Agente (`AgentResponse`)**: Após o loop quebrar, o Orquestrador monta e retorna o objeto `AgentResponse`.

**4. A Resposta para o Agente (`AgentResponse`)**

Este é o objeto de resposta completo e rico em contexto que o Orquestrador envia ao agente de IA a cada chamada.

*   **`service_name`**: O identificador do serviço em execução.
*   **`status`**: O estado geral do fluxo (`IN_PROGRESS`, `COMPLETED`, `FAILED`).
*   **`error_message`**: Descrição do erro, apenas se `status` for `FAILED`.
*   **`current_data`**: O objeto completo do `ServiceState` atual.
*   **`next_step_info`** (presente se `status` for `IN_PROGRESS`):
    *   `step_name`: O nome do passo que aguarda dados.
    *   `description`: A instrução para o agente (do `StepInfo.description`).
    *   `payload_schema`: O JSON Schema para a entrada de dados (do `StepInfo.payload_schema`).
*   **`execution_summary`**:
    *   `completed_data_schema`: Um JSON Schema consolidado de todos os dados já coletados.
    *   `dependency_tree_ascii`: Uma representação textual do grafo do serviço (detalhada na seção 5.1).
*   **`final_output`** (presente se `status` for `COMPLETED`): Os dados de resultado final do serviço.

**5. Lógicas de Suporte para a Geração da Resposta**

**5.1. Gerador da Árvore de Dependências ASCII**

*   **Objetivo:** Criar uma representação textual visualmente rica do progresso.
*   **Lógica:** Deve percorrer a árvore de `steps` e, para cada um, determinar seu status (Concluído, Pendente/Atual, Bloqueado) com base no `ServiceState`. A saída deve usar indentação para hierarquia e ícones para o status.
*   **Ícones de Status:**
    *   `🟢`: Concluído
    *   `🟡`: Pendente/Atual (aguardando dados do usuário)
    *   `🔴`: Bloqueado (pré-condições não satisfeitas)
*   **Exemplo de Saída:**
    ```
    🌳 DEPENDENCY TREE:
    └── 🟢 user_info (required)
        ├── 🟢 name (required)
        ├── 🟡 document (required)   <-- PASSO ATUAL
        └── 🔴 address (required)
    ```

**5.2. Consolidador de Schemas**

*   **Objetivo:** Criar um único JSON Schema que represente tudo o que já foi coletado.
*   **Lógica:** Identificar todos os passos concluídos, extrair seus `payload_schema` e mesclá-los em um único JSON Schema mestre.

**6. Requisitos Não Funcionais e Pontos de Atenção**

*   **Persistência de Estado:** A lógica de carregamento e salvamento do `ServiceState` deve ser abstrata para suportar diferentes mecanismos (ex: Redis, banco de dados).
*   **Avaliador de Condições Seguro:** A implementação que avalia a string da `condition` deve ser segura, evitando o uso de `eval()` direto. Recomenda-se uma biblioteca de avaliação de expressões limitada.
*   **Imutabilidade na Ação:** As `action` não devem modificar o estado diretamente. Elas devem retornar as alterações via `ExecutionResult` para serem aplicadas pelo Orquestrador.



adendo: o payload pode ser enviado um a um {"name":"Joao"} ou em bulk {"name":"Joao", "documment":"12312332112",...} isso é definido pelo depends_on, pois se os passos sao idependentes podemos inserilos todos de uma vez ao inves de ir chamando um por vez (aumentando custo de chamadas ao agente)

