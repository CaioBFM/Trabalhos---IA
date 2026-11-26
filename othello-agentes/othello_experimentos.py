"""Execução manual, checkpoints e relatórios dos experimentos Othello."""

import csv
import io
import json
import os
import re
from collections import Counter
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter


CONFRONTOS = (
    ("E01", "estrategica", "estrategica"),
    ("E02", "estrategica", "estrategica"),
    ("E03", "estrategica", "heuristica"),
    ("E04", "heuristica", "estrategica"),
    ("E05", "estrategica", "operacional"),
    ("E06", "operacional", "operacional"),
    ("E07", "operacional", "operacional"),
    ("E08", "operacional", "heuristica"),
    ("E09", "heuristica", "operacional"),
    ("E10", "operacional", "estrategica"),
)
CORES = ("pretas", "brancas")
CAMPOS_TOKENS = ("tokens_entrada", "tokens_saida", "tokens_total")
METRICAS = (
    "movimentos", "tempo_medio_jogada_s", "tempo_total_s", "tempo_processamento_s",
    "tempo_espera_s", "tempo_llm_s", "chamadas_llm",
    *(campo for nome in CAMPOS_TOKENS for campo in (nome, f"{nome}_cobertura")),
    "erros", "erros_por_tipo", "retries", "retries_por_categoria", "pausas",
    "pausas_por_motivo", "fallbacks", "origens_decisao", "esperas_por_motivo_s",
)
DESEMPENHO = ("pecas", "diferenca_pecas", "vitorias", "derrotas", "empates", "taxa_vitoria", "pontos")
COLUNAS = {
    "partidas": (
        "id", "grupo", "status", "pretas", "brancas", "vencedor", "organizacoes",
        "motivo_pausa", "configuracao", "modelo", *METRICAS,
        *(f"{cor}_{campo}" for cor in CORES for campo in (*DESEMPENHO, *METRICAS)),
    ),
    "jogadas": (
        "id", "turno", "cor", "estrategia", "status", "row", "col", "origem",
        "organizacoes", "tentativas_de_turno", "ferramentas_automaticas",
        "ferramentas_autonomas", "ferramentas_solicitadas", *METRICAS,
    ),
    "ferramentas": ("id", "grupo", "status", "cor", "estrategia", "ferramenta",
                    "execucoes", "automaticas", "autonomas", "solicitadas"),
    "resumo_agentes": (
        "grupo", "estrategia", "cor", "partidas", *DESEMPENHO, *METRICAS,
    ),
}


def agora_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def gravar_atomico(caminho, texto):
    temporario = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="", delete=False,
                                dir=caminho.parent) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(texto)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


def gravar_json(caminho, dados):
    gravar_atomico(caminho, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")


def ler_json(caminho):
    return json.loads(caminho.read_text(encoding="utf-8"))


def gravar_csv(caminho, tabela, linhas):
    saida = io.StringIO(newline="")
    writer = csv.DictWriter(saida, fieldnames=COLUNAS[tabela])
    writer.writeheader()
    for linha in linhas:
        writer.writerow({
            chave: json.dumps(valor, ensure_ascii=False, sort_keys=True)
            if isinstance(valor, (dict, list)) else valor for chave, valor in linha.items()
        })
    gravar_atomico(caminho, saida.getvalue())


@contextmanager
def trava_execucao(diretorio):
    """O sistema operacional libera a trava quando o kernel termina."""
    with (diretorio / ".execucao.lock").open("a+b") as arquivo:
        if os.name == "nt":
            import msvcrt
            if arquivo.tell() == 0:
                arquivo.write(b"0")
                arquivo.flush()
            arquivo.seek(0)
            bloquear = lambda: msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            liberar = lambda: msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            bloquear = lambda: fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            liberar = lambda: fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)
        try:
            bloquear()
        except OSError as erro:
            raise RuntimeError("Já há uma operação de escrita nos resultados.") from erro
        try:
            yield
        finally:
            arquivo.seek(0)
            liberar()


def status_partida(checkpoint):
    if not checkpoint:
        return "pendente"
    if checkpoint["estado"]["jogador_atual"] is None:
        return "concluida"
    return "pausada" if checkpoint["eventos"] or checkpoint["em_andamento"] else "pendente"


def grupo_confronto(pretas, brancas):
    return "auto_confronto" if pretas == brancas else "competitivo"


def ferramentas_eventos(eventos):
    automaticas, autonomas, solicitadas = Counter(), Counter(), Counter()
    for evento in eventos:
        fixas = Counter(evento.get("ferramentas_automaticas", ()))
        automaticas.update(fixas)
        autonomas.update(Counter(evento.get("ferramentas_executadas", ())) - fixas)
        pedidos = evento.get("ferramentas_solicitadas")
        if pedidos is None:
            pedidos = [nome for chamada in evento["chamadas"] for nome in chamada.get("solicitadas", ())]
        solicitadas.update(pedidos)
    return automaticas, autonomas, solicitadas


def exibir_tokens(metricas, campo):
    valor = metricas[campo]
    if valor is None:
        return "indisponível"
    sinal = "≥" if metricas[f"{campo}_cobertura"] == "parcial" else ""
    return f"{sinal}{valor:,}"


class Experimentos:
    def __init__(self, diretorio, protocolo, versoes, *,
                 iniciar, contar, vencedor, resumir, ferramentas):
        self.raiz = Path(diretorio)
        self.checkpoints = self.raiz / "checkpoints"
        self.protocolo = protocolo
        self.versoes = versoes
        self.iniciar = iniciar
        self.contar = contar
        self.vencedor = vencedor
        self.resumir = resumir
        self.ferramentas = tuple(ferramentas)

    def preparar(self):
        self.checkpoints.mkdir(parents=True, exist_ok=True)
        (self.raiz / "graficos").mkdir(exist_ok=True)
        arquivo = self.raiz / "configuracao_experimental.json"
        dados = {
            "protocolo": self.protocolo, "versoes_iniciais": self.versoes,
            "confrontos": [{"id": i, "pretas": p, "brancas": b} for i, p, b in CONFRONTOS],
            "ferramentas": list(self.ferramentas),
        }
        if arquivo.exists():
            anterior = ler_json(arquivo)
            if any(anterior[chave] != dados[chave] for chave in ("protocolo", "confrontos", "ferramentas")):
                raise ValueError("O protocolo atual difere do protocolo salvo. Preserve as configurações.")
        else:
            gravar_json(arquivo, dados)

    def carregar(self):
        return {
            i: ler_json(arquivo) for i, _, _ in CONFRONTOS
            if (arquivo := self.checkpoints / f"{i}.json").exists()
        }

    def salvar(self, checkpoint):
        gravar_json(self.checkpoints / f"{checkpoint['id']}.json", checkpoint)

    def ritmos_organizacao(self, organizacao):
        return [
            sessao.get("ritmo_groq", {}) for checkpoint in self.carregar().values()
            for sessao in checkpoint["sessoes"] if sessao["organizacao"] == organizacao
        ]

    @staticmethod
    def eventos(checkpoint):
        return checkpoint["eventos"] + ([checkpoint["em_andamento"]] if checkpoint["em_andamento"] else [])

    def metricas(self, eventos):
        chamadas = [chamada for evento in eventos for chamada in evento["chamadas"]]
        duracao = sum(evento["duracao_s"] for evento in eventos)
        motivos = Counter(evento["pausa"] for evento in eventos if evento.get("pausa"))
        origens = Counter(evento["origem"] for evento in eventos if evento.get("origem"))
        movimentos = sum(evento["status"] == "confirmada" for evento in eventos)
        m = self.resumir(
            chamadas, duracao, [erro for evento in eventos for erro in evento.get("erros_finais", ())],
            fallbacks=origens["fallback_heuristico"],
            esperas=[espera for evento in eventos for espera in evento["esperas"]],
        )
        dados = {
            "movimentos": movimentos,
            "tempo_medio_jogada_s": sum(
                evento["duracao_s"] for evento in eventos if evento["status"] == "confirmada"
            ) / movimentos if movimentos else None,
            "tempo_total_s": duracao,
            "tempo_processamento_s": m["tempo_processamento_s"],
            "tempo_espera_s": m["tempo_espera_s"],
            "tempo_llm_s": m["tempo_llm_s"],
            "chamadas_llm": m["chamadas_llm"],
            "erros": m["total_erros"], "erros_por_tipo": m["erros"],
            "retries": m["tentativas_adicionais"], "retries_por_categoria": m["tentativas_por_categoria"],
            "pausas": sum(motivos.values()), "pausas_por_motivo": dict(motivos),
            "fallbacks": m["fallbacks"], "origens_decisao": dict(origens),
            "esperas_por_motivo_s": m["tempo_espera_por_motivo_s"],
        }
        for campo in CAMPOS_TOKENS:
            conhecidos = m["chamadas_com_tokens"][campo]
            total = m["chamadas_llm"]
            dados[campo] = m[campo] if total else 0
            dados[f"{campo}_cobertura"] = (
                "sem_chamadas" if not total else "exata" if conhecidos == total
                else "parcial" if conhecidos else "indisponivel"
            )
        return dados

    def planejar(self, id_partida):
        base = self.carregar()
        concluidas = [i for i, _, _ in CONFRONTOS if status_partida(base.get(i)) == "concluida"]
        pendentes = [i for i, _, _ in CONFRONTOS if i not in concluidas]
        if not pendentes or id_partida != pendentes[0]:
            proxima = pendentes[0] if pendentes else "nenhuma"
            raise ValueError(f"Próxima partida na ordem experimental: {proxima}.")
        _, pretas, brancas = next(item for item in CONFRONTOS if item[0] == id_partida)
        equivalentes = [
            self.metricas(self.eventos(base[i])) for i, p, b in CONFRONTOS
            if i in concluidas and sorted((p, b)) == sorted((pretas, brancas))
        ]
        exatos = [m["tokens_total"] for m in equivalentes if m["tokens_total_cobertura"] == "exata"]
        parciais = [m["tokens_total"] for m in equivalentes if m["tokens_total_cobertura"] == "parcial"]
        print("Concluídas:", ", ".join(concluidas) or "nenhuma")
        print("Pendentes ou pausadas:", ", ".join(pendentes))
        print(f"{id_partida} | {pretas} (pretas) × {brancas} (brancas)")
        print(f"Equivalentes concluídos: {len(equivalentes)} | com contagem exata: {len(exatos)}")
        if exatos:
            print(f"Tokens exatos observados — média {sum(exatos) / len(exatos):.0f}, máximo {max(exatos)}")
        if parciais:
            print(f"Mínimos observados nas contagens parciais — média ≥{sum(parciais) / len(parciais):.0f}, "
                  f"máximo ≥{max(parciais)}")
        if not exatos:
            print("Estimativa incerta. Ainda não há uma partida equivalente com contagem exata.")
        return base.get(id_partida)

    def executar(self, id_partida, organizacao=None, *, criar_sessao, executar_turno,
                 acesso=None, capturar_ritmo=dict):
        self.checkpoints.mkdir(parents=True, exist_ok=True)
        with trava_execucao(self.checkpoints):
            self.preparar()
            cp = self.planejar(id_partida)
            sessoes = cp["sessoes"] if cp else []
            if organizacao is None:
                organizacao = sessoes[-1]["organizacao"] if sessoes else "org-a"
            if not re.fullmatch(r"org-[a-z0-9_-]{1,16}", organizacao):
                raise ValueError("Use um código anônimo, como org-a.")
            if cp is None:
                cp = {"id": id_partida, "estado": self.iniciar(), "eventos": [],
                      "em_andamento": None, "sessoes": [], "motivo_pausa": None}
            else:
                tokens = exibir_tokens(self.metricas(self.eventos(cp)), "tokens_total")
                print(f"Retomando {id_partida} após {len(cp['estado']['historico'])} jogadas confirmadas"
                      f" e {tokens} tokens acumulados.")
            with acesso(organizacao) if acesso is not None else nullcontext():
                self._executar_autorizado(
                    cp, organizacao, criar_sessao, executar_turno, capturar_ritmo,
                )

    def _executar_autorizado(self, cp, organizacao, criar_sessao, executar_turno, capturar_ritmo):
        id_partida = cp["id"]
        if pendente := cp["em_andamento"]:
            pendente.update(status="interrompida", pausa="kernel_interrompido")
            cp["eventos"].append(pendente)
            cp["em_andamento"] = None

        _, pretas, brancas = next(item for item in CONFRONTOS if item[0] == id_partida)
        modos = {"pretas": pretas, "brancas": brancas}
        sessao_id = len(cp["sessoes"]) + 1
        cp["sessoes"].append({
            "id": sessao_id, "organizacao": organizacao, "inicio_utc": agora_utc(),
            "politica_execucao": "espera_automatica", "versoes": self.versoes,
        })
        cp["motivo_pausa"] = None
        self.salvar(cp)
        chamadas, esperas = [], []
        while cp["estado"]["jogador_atual"] is not None:
            cor = "pretas" if cp["estado"]["jogador_atual"] == 1 else "brancas"
            turno = len(cp["estado"]["historico"]) + 1
            evento = {
                "turno": turno, "cor": cor, "organizacao": organizacao, "sessao": sessao_id,
                "duracao_s": 0, "status": "em_andamento", "chamadas": [], "esperas": [],
            }
            cp["em_andamento"] = evento
            inicio, inicio_chamadas, inicio_esperas = perf_counter(), len(chamadas), len(esperas)

            def registrar():
                evento.update(
                    duracao_s=perf_counter() - inicio,
                    chamadas=chamadas[inicio_chamadas:],
                    esperas=esperas[inicio_esperas:],
                )
                cp["sessoes"][-1]["ritmo_groq"] = capturar_ritmo()

            def persistir():
                registrar()
                self.salvar(cp)

            sessao = criar_sessao(chamadas, esperas, persistir)
            copia = deepcopy(cp["estado"])
            persistir()
            pausa = None
            novo_estado = cp["estado"]
            try:
                resultado = executar_turno(modos[cor], copia, sessao)
                pausa = resultado.get("pausa_api")
                if len(copia["historico"]) != turno - bool(pausa):
                    raise RuntimeError("O turno não devolveu o número esperado de jogadas.")
                for chave in ("ferramentas_automaticas", "ferramentas_executadas",
                              "ferramentas_solicitadas", "erros_finais"):
                    evento[chave] = resultado.get(chave, [])
                if not pausa:
                    evento.update(status="confirmada", origem=resultado.get("origem_decisao"))
                    novo_estado = copia
            except KeyboardInterrupt:
                pausa = "interrupcao_manual"
            except Exception as erro:
                pausa = "erro_execucao"
                evento["erros_finais"] = [type(erro).__name__]
            if novo_estado is cp["estado"]:
                evento["status"] = "pausada"
                evento.pop("origem", None)
            if pausa:
                evento["pausa"] = pausa
            registrar()
            cp.update(estado=novo_estado, eventos=[*cp["eventos"], evento],
                      em_andamento=None, motivo_pausa=pausa)
            self.salvar(cp)
            self.exportar()
            metricas = self.metricas(cp["eventos"])
            pretas_pontos, brancas_pontos = self.contar(cp["estado"]["tabuleiro"])
            tokens = exibir_tokens(metricas, "tokens_total")
            print(
                f"{id_partida} · turno {turno} ({cor}) · {pausa or evento['status']} · "
                f"placar {pretas_pontos} × {brancas_pontos} · {tokens} tokens acumulados",
                flush=True,
            )
            if pausa:
                break
        self.exibir_resumo(cp)

    def exibir_resumo(self, cp):
        estado = cp["estado"]
        pretas, brancas = self.contar(estado["tabuleiro"])
        m = self.metricas(cp["eventos"])
        if estado["jogador_atual"] is None:
            resultado = {1: "pretas venceram", -1: "brancas venceram", 0: "empate"}
            status = resultado[self.vencedor(pretas, brancas)]
        else:
            status = f"pausada ({cp['motivo_pausa']})"
        print(f"{cp['id']} · {status} · {pretas} × {brancas} · {m['movimentos']} jogadas")
        entrada, saida, total = (exibir_tokens(m, campo) for campo in CAMPOS_TOKENS)
        print(f"Tokens (entrada/saída/total): {entrada} / {saida} / {total} · {m['chamadas_llm']} chamadas")
        print(f"Espera: {m['tempo_espera_s']:.1f}s · retries: {m['retries']} · fallbacks: {m['fallbacks']}")

    def exportar(self):
        base = self.carregar()
        partidas, jogadas, ferramentas = [], [], []
        grupos = {}
        for id_partida, pretas, brancas in CONFRONTOS:
            cp = base.get(id_partida)
            status = status_partida(cp)
            grupo = grupo_confronto(pretas, brancas)
            linha = {"id": id_partida, "pretas": pretas, "brancas": brancas,
                     "status": status, "grupo": grupo, "modelo": self.protocolo["modelo"],
                     "configuracao": "configuracao_experimental.json"}
            partidas.append(linha)
            if not cp:
                continue
            eventos = self.eventos(cp)
            linha.update(self.metricas(eventos))
            linha.update(organizacoes=sorted({s["organizacao"] for s in cp["sessoes"]}),
                         motivo_pausa=cp["motivo_pausa"])
            pontos = self.contar(cp["estado"]["tabuleiro"])
            terminado = status == "concluida"
            vencedor = self.vencedor(*pontos) if terminado else None
            linha["vencedor"] = {1: "pretas", -1: "brancas", 0: "empate"}.get(vencedor)

            for indice, (cor, modo) in enumerate(zip(CORES, (pretas, brancas))):
                individuais = [evento for evento in eventos if evento["cor"] == cor]
                cor_vencedora = 1 if cor == "pretas" else -1
                desempenho = {}
                if terminado:
                    v, d, e = int(vencedor == cor_vencedora), int(vencedor == -cor_vencedora), int(vencedor == 0)
                    desempenho = {
                        "pecas": pontos[indice], "diferenca_pecas": pontos[indice] - pontos[1-indice],
                        "vitorias": v, "derrotas": d, "empates": e, "taxa_vitoria": v, "pontos": 3 * v + e,
                    }
                    for subdivisao in ("todas", cor):
                        grupos.setdefault((grupo, modo, subdivisao), []).append((desempenho, individuais))
                linha.update({f"{cor}_{k}": x for k, x in {**desempenho, **self.metricas(individuais)}.items()})
                fixas, livres, pedidos = ferramentas_eventos(individuais)
                for nome in self.ferramentas:
                    ferramentas.append({
                        "id": id_partida, "grupo": grupo, "status": status, "cor": cor, "estrategia": modo,
                        "ferramenta": nome, "execucoes": fixas[nome] + livres[nome],
                        "automaticas": fixas[nome], "autonomas": livres[nome], "solicitadas": pedidos[nome],
                    })

            por_turno = {}
            for evento in eventos:
                por_turno.setdefault((evento["turno"], evento["cor"]), []).append(evento)
            for (turno, cor), tentativas in por_turno.items():
                confirmada = next((e for e in tentativas if e["status"] == "confirmada"), None)
                origem = confirmada.get("origem") if confirmada else None
                jogada = cp["estado"]["historico"][turno - 1] if confirmada else {}
                fixas, livres, pedidos = ferramentas_eventos(tentativas)
                jogadas.append({
                    "id": id_partida, "turno": turno, "cor": cor,
                    "estrategia": pretas if cor == "pretas" else brancas,
                    "status": tentativas[-1]["status"], "row": jogada.get("row"), "col": jogada.get("col"),
                    "origem": origem, "organizacoes": sorted({e["organizacao"] for e in tentativas}),
                    "tentativas_de_turno": len(tentativas), "ferramentas_automaticas": dict(fixas),
                    "ferramentas_autonomas": dict(livres), "ferramentas_solicitadas": dict(pedidos),
                    **self.metricas(tentativas),
                })

        resumos = []
        for (grupo, estrategia, cor), amostra in sorted(grupos.items()):
            totais = {campo: sum(d[campo] for d, _ in amostra) for campo in DESEMPENHO if campo != "taxa_vitoria"}
            totais["taxa_vitoria"] = totais["vitorias"] / len(amostra)
            resumos.append({
                "grupo": grupo, "estrategia": estrategia, "cor": cor, "partidas": len(amostra),
                **totais, **self.metricas([evento for _, eventos in amostra for evento in eventos]),
            })
        for tabela, linhas in zip(COLUNAS, (partidas, jogadas, ferramentas, resumos)):
            gravar_csv(self.raiz / f"{tabela}.csv", tabela, linhas)


def ler_tabela(raiz, nome):
    with (Path(raiz) / f"{nome}.csv").open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def mostrar_tabela(raiz, nome, *, limite=None):
    from IPython.display import HTML, display

    if nome not in COLUNAS:
        raise ValueError(f"Tabela inválida: {nome}")
    linhas = ler_tabela(raiz, nome)
    campos = COLUNAS[nome]
    cabecalho = "".join(f"<th>{escape(campo)}</th>" for campo in campos)
    itens = "".join(
        "<tr>" + "".join(f"<td>{escape(linha[campo])}</td>" for campo in campos) + "</tr>"
        for linha in linhas[:limite]
    )
    display(HTML(
        f"<details open><summary>{escape(nome)} · {len(linhas)} registros</summary>"
        f'<div style="overflow:auto;max-height:450px"><table><thead><tr>{cabecalho}</tr></thead>'
        f"<tbody>{itens}</tbody></table></div></details>"
    ))


def gerar_graficos(raiz, *, exibir=True):
    import matplotlib.pyplot as plt

    raiz = Path(raiz)
    pasta = raiz / "graficos"
    pasta.mkdir(exist_ok=True)
    agentes = [r for r in ler_tabela(raiz, "resumo_agentes") if r["cor"] == "todas"]
    ferramentas = [r for r in ler_tabela(raiz, "ferramentas") if r["status"] == "concluida"]
    graficos = (
        ("resultados", "Vitórias, derrotas e empates", ("vitorias", "derrotas", "empates")),
        ("taxa_vitoria", "Taxa de vitória (%)", ("taxa_vitoria",)),
        ("pontos", "Classificação por pontos", ("pontos",)),
        ("tempo_por_jogada", "Tempo médio por jogada (s)", ("tempo_medio_jogada_s",)),
        ("processamento_espera", "Processamento e espera (s)", ("tempo_processamento_s", "tempo_espera_s")),
        ("tokens", "Tokens medidos (≥ indica contagem parcial)", CAMPOS_TOKENS),
        ("chamadas_llm", "Chamadas à LLM", ("chamadas_llm",)),
        ("ferramentas", "Frequência de uso das ferramentas", ("automaticas", "autonomas")),
        ("erros", "Erros, retries e fallbacks", ("erros", "retries", "fallbacks")),
    )
    rotulos = {
        "vitorias": "Vitórias", "derrotas": "Derrotas", "empates": "Empates",
        "tempo_processamento_s": "Processamento", "tempo_espera_s": "Espera",
        "tokens_entrada": "Entrada", "tokens_saida": "Saída", "tokens_total": "Total",
        "automaticas": "Automáticas", "autonomas": "Autônomas",
        "erros": "Erros", "retries": "Retries", "fallbacks": "Fallbacks",
    }
    nomes = {"estrategica": "Estratégico", "operacional": "Operacional", "heuristica": "Heurístico"}
    caminhos = []
    for nome, titulo, campos in graficos:
        fig, eixos = plt.subplots(1, 2, figsize=(13 if nome == "ferramentas" else 10, 4.6), layout="constrained")
        fig.suptitle(titulo)
        for grupo, eixo in zip(("competitivo", "auto_confronto"), eixos):
            eixo.set_title("Estratégias diferentes" if grupo == "competitivo" else "Mesma estratégia")
            dados = [r for r in agentes if r["grupo"] == grupo]
            if nome == "pontos":
                dados.sort(key=lambda r: -int(r["pontos"]))
            categorias = [nomes[r["estrategia"]] for r in dados]
            if nome == "ferramentas":
                registros = [r for r in ferramentas if r["grupo"] == grupo]
                categorias = sorted({r["ferramenta"] for r in registros})
                dados = [{campo: sum(int(r[campo]) for r in registros if r["ferramenta"] == item)
                          for campo in campos} for item in categorias]
            if not dados:
                eixo.text(.5, .5, "Sem partidas concluídas", ha="center", va="center", transform=eixo.transAxes)
                eixo.set_xticks([])
                eixo.set_yticks([])
                continue
            largura = .76 / len(campos)
            for i, campo in enumerate(campos):
                legenda = rotulos.get(campo, campo) if len(campos) > 1 else None
                for j, linha in enumerate(dados):
                    deslocamento = (i - (len(campos) - 1) / 2) * largura
                    valor = linha[campo]
                    posicao = j + deslocamento
                    if valor == "":
                        eixo.annotate("n/d", (posicao, 0), ha="center", fontsize=8)
                        continue
                    altura = float(valor) * (100 if campo == "taxa_vitoria" else 1)
                    barra = eixo.bar(posicao, altura, width=largura, color=f"C{i}", label=legenda)
                    legenda = None
                    if linha.get(f"{campo}_cobertura") == "parcial":
                        barra[0].set_hatch("//")
                        eixo.annotate("≥", (posicao, altura), ha="center", va="bottom", fontsize=9)
            eixo.set_xticks(range(len(categorias)), categorias, rotation=40 if nome == "ferramentas" else 0,
                            ha="right" if nome == "ferramentas" else "center")
            eixo.grid(axis="y", alpha=.25)
            eixo.set_axisbelow(True)
            if nome == "taxa_vitoria":
                eixo.set_ylim(0, 100)
            if eixo.get_legend_handles_labels()[0]:
                eixo.legend()
        destino = pasta / f"{nome}.png"
        fig.savefig(destino, dpi=150)
        caminhos.append(destino)
        if exibir:
            plt.show()
        plt.close(fig)
    return caminhos
