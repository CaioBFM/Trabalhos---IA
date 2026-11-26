# Trabalho Prático 05 — Agentes Inteligentes para Othello

**Universidade Federal de Lavras (UFLA)**  
**Disciplina:** GCC128 — Inteligência Artificial  
**Professor:** Ahmed Ali Abdalla Esmin

## Alunos

- Caio Bueno Finocchio Martins
- Lana da Silva Miranda

## 1. Sobre o projeto

Implementação do jogo Othello (Reversi) com agentes inteligentes capazes de observar o estado da partida, avaliar alternativas, consultar ferramentas e executar jogadas. O projeto utiliza Python, LangChain, LangGraph, Groq e Pygame.

São disponibilizadas três estratégias:

- **Heurístico:** avalia as jogadas legais utilizando pesos posicionais, sem chamadas a uma LLM.
- **Estratégico:** recebe informações do tabuleiro, movimentos válidos, histórico e uma recomendação Minimax com poda alfa-beta (profundidade 3). A LLM pode solicitar consultas complementares antes de decidir.
- **Operacional:** a LLM escolhe autonomamente quais ferramentas consultar e executa a jogada por meio do fluxo de decisão.

A interface permite partidas Humano × Humano, Humano × Agente e Agente × Agente.

## 2. Instalação

**Pré-requisitos:** Python 3.11 ou superior, VS Code com as extensões Python e Jupyter (ou outro ambiente Jupyter local com suporte a janelas gráficas).

Caso esteja utilizando o ZIP da entrega, extraia o arquivo e abra a pasta que contém `othello_agentes.ipynb` no terminal. Para obter o projeto pelo GitHub:

```bash
git clone https://github.com/CaioBFM/Trabalhos---IA.git
cd Trabalhos---IA/othello-agentes
```

### Ubuntu / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

No Ubuntu, caso o módulo `venv` não esteja disponível, instale o pacote `python3-venv`.

### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 3. Como executar

1. Abra `othello_agentes.ipynb` no VS Code.
2. Selecione o kernel Python do ambiente `.venv`.
3. Mantenha a configuração inicial `MODO_EXECUCAO = "pygame"`.
4. Clique em **Run All** (Executar tudo). A interface gráfica será aberta pela última célula.
5. Na opção **Nova partida**, selecione os participantes das pretas e das brancas.

A janela inicia no modo Humano × Humano. É possível acompanhar o placar, as jogadas válidas, as ferramentas e as métricas dos agentes. Os controles permitem iniciar, pausar, retomar e encerrar partidas. **Encerrar partida** retorna ao estado inicial em Humano × Humano.

### Chave da API Groq

Apenas os agentes Estratégico e Operacional necessitam de conexão com a internet e de uma chave da Groq. O modelo utilizado é `openai/gpt-oss-20b`.

1. Obtenha uma chave em <https://console.groq.com/keys>.
2. Ao selecionar um agente LLM sem chave configurada, clique em **Configurar API** na interface.
3. Informe a chave no notebook quando solicitado. A interface será reaberta e manterá os participantes selecionados.

A chave é solicitada via `getpass` e não deve ser inserida no código ou versionada. Partidas exclusivamente humanas ou heurísticas não precisam de chave. Em caso de limite temporário da API, acompanhe o aviso de espera. Se a cota diária se esgotar, aguarde sua renovação e retome a partida, ou configure uma chave autorizada conforme as regras do provedor.

## 4. Experimentos e resultados

Os 13 experimentos oficiais (E01–E13) já foram concluídos. **Executar todas as células não reinicia os experimentos.**

Para consultar os resultados sem abrir a interface, altere a configuração inicial para:

```python
MODO_EXECUCAO = "experimentos"
```

Execute as células do notebook. A seção 8 apresenta o protocolo experimental e os exemplos comentados de execução manual. A seção 9 contém as tabelas, os gráficos e a análise dos resultados. A consulta funciona offline e não exige credenciais.

A execução manual de experimentos pendentes é feita pelas funções `executar_experimento()` e `executar_experimentos()`, conforme os exemplos na seção 8.3. O executor utiliza checkpoints para preservar as partidas pausadas e não repete partidas já concluídas. Preserve os arquivos originais de resultados.

### Classificação final

A classificação considera nove partidas entre estratégias distintas, excluindo quatro autoconfrontos. Cada vitória vale três pontos, cada empate vale um ponto e cada derrota vale zero.

| Estratégia | Partidas | Vitórias | Derrotas | Empates | Taxa de vitória | Pontos |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Estratégico | 7 | 5 | 2 | 0 | 71,43% | 15 |
| Operacional | 7 | 4 | 3 | 0 | 57,14% | 12 |
| Heurístico | 4 | 0 | 4 | 0 | 0% | 0 |

### Resultados individuais

| Experimento | Pretas | Brancas | Placar (P × B) | Jogadas |
| --- | --- | --- | ---: | ---: |
| E01 | Estratégico | Estratégico | 44 × 20 | 60 |
| E02 | Estratégico | Estratégico | 38 × 26 | 60 |
| E03 | Estratégico | Heurístico | 13 × 0 | 9 |
| E04 | Heurístico | Estratégico | 21 × 43 | 60 |
| E05 | Estratégico | Operacional | 38 × 26 | 60 |
| E06 | Operacional | Operacional | 14 × 50 | 60 |
| E07 | Operacional | Operacional | 34 × 30 | 60 |
| E08 | Operacional | Heurístico | 41 × 23 | 60 |
| E09 | Heurístico | Operacional | 21 × 43 | 60 |
| E10 | Operacional | Estratégico | 37 × 27 | 60 |
| E11 | Estratégico | Operacional | 13 × 0 | 9 |
| E12 | Operacional | Estratégico | 12 × 52 | 60 |
| E13 | Operacional | Estratégico | 40 × 24 | 60 |

E03 e E11 terminaram antes do preenchimento do tabuleiro, pois nenhum jogador possuía mais jogadas legais. As partidas E01, E02, E06 e E07 são autoconfrontos e não entram na classificação competitiva.

### Desempenho computacional

Métricas das nove partidas competitivas:

| Estratégia | Jogadas | Tempo médio por jogada | Chamadas à LLM | Tokens registrados | Fallbacks |
| --- | ---: | ---: | ---: | ---: | ---: |
| Estratégico | 159 | 8,20 s | 376 | ≥ 255.479 | 3 |
| Operacional | 185 | 15,88 s | 917 | ≥ 591.255 | 3 |
| Heurístico | 94 | 0,018 s | 0 | 0 | 0 |

Considerando as 13 partidas, foram registradas **678 jogadas, 2.216 chamadas à LLM, pelo menos 1.454.729 tokens, 1.182 novas tentativas (retries), 11 pausas e nove fallbacks**. As contagens parciais de tokens são limites inferiores, pois nem todas as chamadas retornaram informações completas de consumo.

### Análise dos resultados

- **Desempenho competitivo:** o Estratégico liderou a classificação com 15 pontos e venceu três dos cinco confrontos diretos com o Operacional. Ambos os agentes LLM venceram suas duas partidas contra o Heurístico, uma com cada cor.
- **Custo computacional:** nas partidas competitivas, o Estratégico registrou aproximadamente 2,36 chamadas por jogada, contra 4,96 do Operacional. Seu tempo médio por jogada também foi menor. A sequência fixa de observações e a recomendação Minimax são características que ajudam a interpretar essa diferença, sem estabelecer causalidade isolada.
- **Uso de ferramentas:** nas 13 partidas, as consultas mais frequentes foram `get_minimax_move` (425 execuções) e `get_valid_moves` (396). Os registros distinguem consultas automáticas de escolhas autônomas da LLM.
- **Limites da API:** a espera representou cerca de 83% e 82% do tempo ativo do Estratégico e do Operacional, respectivamente, nos confrontos competitivos. Assim, o tempo observado não representa apenas o processamento da estratégia. O Heurístico apresentou o menor tempo por jogada e dispensou chamadas externas, mas perdeu os quatro confrontos.
- **Limitações:** a amostra é pequena, a distribuição das cores nos cinco confrontos diretos é desigual e as condições da API variaram durante a coleta. O uso de fallback e a cobertura parcial de tokens também limitam a comparação.

Os resultados indicam que o Estratégico apresentou o melhor equilíbrio entre desempenho competitivo e custo de execução nesta bateria, sem permitir generalizar sua superioridade para outras condições experimentais.

As tabelas completas, incluindo os tempos de resposta da LLM, estão em [resultados/](resultados/). Os gráficos e a discussão detalhada estão na seção 9 do [notebook](othello_agentes.ipynb).

## 5. Organização dos arquivos

```text
othello-agentes/
├── othello_agentes.ipynb
├── othello_interface.py
├── othello_experimentos.py
├── requirements.txt
├── Relatorio_Othello.pdf
├── README.md
└── resultados/
    ├── configuracao_experimental.json
    ├── partidas.csv
    ├── jogadas.csv
    ├── ferramentas.csv
    ├── resumo_agentes.csv
    ├── checkpoints/
    └── graficos/
```

- `othello_agentes.ipynb`: motor do jogo, estratégias, ferramentas, grafos dos agentes e análise experimental.
- `othello_interface.py`: interface gráfica e controle das partidas.
- `othello_experimentos.py`: execução experimental, persistência de checkpoints e geração dos resultados.
- `resultados/`: dados, configurações e gráficos dos experimentos oficiais.

## 6. Relatório e vídeo

- [Relatório técnico](Relatorio_Othello.pdf)
- Vídeo de apresentação: link a inserir após a gravação.
