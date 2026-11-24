"""Interface local de Othello. O notebook fornece as operações do motor."""

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

import pygame as pg


JANELA = (1200, 800)
FPS = 60
CASAS = 8
TAMANHO_CASA = 75
TABULEIRO = pg.Rect(94, 151, CASAS * TAMANHO_CASA, CASAS * TAMANHO_CASA)
MOLDURA = TABULEIRO.inflate(48, 48)
PAINEIS = tuple(pg.Rect(779, y, 389, h) for y, h in (
    (110, 229), (353, 134), (501, 110), (625, 150)
))
LARGURA_SIDEBAR = 360
SIDEBAR = pg.Rect(JANELA[0] - LARGURA_SIDEBAR, 0, LARGURA_SIDEBAR, JANELA[1])
BOTOES_TOPO = {
    "pausa": pg.Rect(749, 23, 115, 42),
    "reiniciar": pg.Rect(876, 23, 121, 42),
    "nova": pg.Rect(1009, 23, 159, 42),
}
FECHAR = pg.Rect(1130, 27, 38, 38)
INICIAR = pg.Rect(864, 705, 312, 53)
OPCOES = ("Humano", "Estratégico", "Operacional", "Heurístico")
DISPONIVEIS = {"Humano", "Heurístico"}
ESPERA_HEURISTICA_MS = 320

CORES = {
    "fundo": "#101418",
    "painel": "#1B2228",
    "cartao": "#252E34",
    "casa_escura": "#275E49",
    "casa_clara": "#2B684F",
    "menta": "#A8EDC7",
    "texto": "#E9EFEA",
    "secundario": "#97A5AF",
    "borda": "#303B43",
    "borda_verde": "#39594D",
    "hover": "#303C43",
    "menta_hover": "#C7F7DB",
    "menta_escura": "#17362A",
    "desativado": "#76858F",
    "grade": "#193F33",
    "moldura": "#1B302A",
}
C = {nome: pg.Color(cor) for nome, cor in CORES.items()}
FONTES = "inter, segoeui, liberation sans, dejavusans"
FONTES_MONO = "ibmplexmono, dejavu sans mono"


@dataclass(frozen=True)
class MotorOthello:
    pretas: int
    brancas: int
    iniciar_partida: Callable
    movimentos_validos: Callable
    fazer_jogada: Callable
    proximo_turno: Callable
    contar_pecas: Callable
    obter_vencedor: Callable
    escolher_melhor_jogada: Callable


@dataclass
class EstadoInterface:
    motor: MotorOthello
    partida: dict = field(init=False)
    jogadores: dict = field(init=False)
    selecao: dict | None = None
    pausada: bool = False
    passou: int | None = None
    movimentos: set = field(default_factory=set)

    def __post_init__(self):
        self.jogadores = dict.fromkeys((self.motor.pretas, self.motor.brancas), "Humano")
        self.reiniciar()

    @property
    def tabuleiro(self):
        return self.partida["tabuleiro"]

    @property
    def atual(self):
        return self.partida["jogador_atual"]

    @property
    def ultima(self):
        historico = self.partida["historico"]
        return (historico[-1]["row"], historico[-1]["col"]) if historico else None

    @property
    def turno(self):
        return len(self.partida["historico"]) + (self.atual is not None)

    @property
    def ativa(self):
        return self.atual is not None and not self.pausada and self.selecao is None

    def atualizar_movimentos(self):
        self.movimentos = (
            set(self.motor.movimentos_validos(self.tabuleiro, self.atual))
            if self.atual is not None else set()
        )

    def reiniciar(self):
        self.partida = self.motor.iniciar_partida()
        self.pausada = False
        self.passou = None
        self.atualizar_movimentos()

    def jogar(self, linha, coluna):
        if not self.ativa or (linha, coluna) not in self.movimentos:
            return False
        jogador = self.atual
        if not self.motor.fazer_jogada(self.tabuleiro, linha, coluna, jogador):
            return False

        self.partida["historico"].append({"player": jogador, "row": linha, "col": coluna})
        seguinte = self.motor.proximo_turno(self.tabuleiro, jogador)
        self.partida["jogador_atual"] = seguinte
        self.passou = -jogador if seguinte == jogador else None
        self.atualizar_movimentos()
        return True

    def nome_cor(self, jogador):
        return "Pretas" if jogador == self.motor.pretas else "Brancas"


def retangulo_casa(linha, coluna):
    return pg.Rect(
        TABULEIRO.x + coluna * TAMANHO_CASA, TABULEIRO.y + linha * TAMANHO_CASA,
        TAMANHO_CASA, TAMANHO_CASA,
    )


def casa_em(posicao):
    if TABULEIRO.collidepoint(posicao):
        return (
            (posicao[1] - TABULEIRO.y) // TAMANHO_CASA,
            (posicao[0] - TABULEIRO.x) // TAMANHO_CASA,
        )
    return None


def opcoes_sidebar():
    for jogador, topo in enumerate((164, 342)):
        for indice, nome in enumerate(OPCOES):
            linha, coluna = divmod(indice, 2)
            yield jogador, nome, pg.Rect(864 + coluna * 160, topo + linha * 64, 152, 55)


def caixa(superficie, rect, cor, raio=12, borda=None):
    pg.draw.rect(superficie, C[cor], rect, border_radius=raio)
    if borda:
        pg.draw.rect(superficie, C[borda], rect, width=1, border_radius=raio)


def circulo_degrade(superficie, centro, raio, clara, escura):
    """Desenha o volume da peça uma vez, durante a criação dos sprites."""
    cx, cy = centro
    for dy in range(-raio, raio + 1):
        metade = int((raio ** 2 - dy ** 2) ** .5)
        cor = clara.lerp(escura, (dy + raio) / (2 * raio))
        pg.draw.line(superficie, cor, (cx - metade, cy + dy), (cx + metade, cy + dy))


def sprite_peca(preta, raio):
    escala = 3
    tamanho_final = raio * 2 + 16
    dimensao = tamanho_final * escala
    raio *= escala
    sprite = pg.Surface((dimensao, dimensao), pg.SRCALPHA)
    centro = (dimensao // 2, dimensao // 2)
    for margem, opacidade in ((4, 34), (2, 61), (0, 100)):
        pg.draw.circle(sprite, (4, 13, 13, opacidade),
                       (centro[0], centro[1] + 4 * escala), raio + margem * escala)
    cores = ("#4A535C", "#141A1E", "#0A1013", "#303B40") if preta else (
        "#FFFFFF", "#BACDC2", "#82988C", "#F1F7EE"
    )
    clara, escura, aro, brilho = map(pg.Color, cores)
    pg.draw.circle(sprite, aro, centro, raio + escala)
    circulo_degrade(sprite, centro, raio, clara, escura)
    area = pg.Rect(0, 0, raio * 2 - 6 * escala, raio * 2 - 6 * escala)
    area.center = centro
    pg.draw.arc(sprite, brilho, area, .55, 2.6, escala)
    return pg.transform.smoothscale(sprite, (tamanho_final, tamanho_final)).convert_alpha()


class Renderizacao:
    def __init__(self):
        self.tela = pg.Surface(JANELA).convert()
        self.base = pg.Surface(JANELA).convert()
        self.pecas = {preta: sprite_peca(preta, 28) for preta in (True, False)}
        self.mini_pecas = {preta: sprite_peca(preta, 11) for preta in (True, False)}
        self.marcador = pg.Surface((16, 16), pg.SRCALPHA)
        pg.draw.circle(self.marcador, (168, 237, 199, 100), (8, 8), 5)
        pg.draw.circle(self.marcador, (168, 237, 199, 156), (8, 8), 7, 1)
        self.scrim = pg.Surface(JANELA, pg.SRCALPHA)
        self.scrim.fill((5, 8, 11, 155))
        self.desenhar_base()

    @lru_cache(maxsize=20)
    def fonte(self, tamanho, negrito, mono):
        return pg.font.SysFont(FONTES_MONO if mono else FONTES, tamanho, bold=negrito)

    @lru_cache(maxsize=384)
    def rotulo(self, texto, tamanho, cor, negrito, mono, espaco):
        fonte = self.fonte(tamanho, negrito, mono)
        if not espaco:
            return fonte.render(texto, True, C[cor])
        glifos = [fonte.render(letra, True, C[cor]) for letra in texto]
        largura = sum(g.get_width() for g in glifos) + espaco * (len(glifos) - 1)
        imagem = pg.Surface((largura, fonte.get_height()), pg.SRCALPHA)
        x = 0
        for glifo in glifos:
            imagem.blit(glifo, (x, 0))
            x += glifo.get_width() + espaco
        return imagem

    def texto(self, texto, x, y, tamanho=16, cor="texto", *,
              negrito=False, mono=False, espaco=0, alinhar="topleft", superficie=None):
        imagem = self.rotulo(texto, tamanho, cor, negrito, mono, espaco)
        (self.tela if superficie is None else superficie).blit(
            imagem, imagem.get_rect(**{alinhar: (x, y)})
        )

    def titulo(self, texto, x, y, superficie=None):
        self.texto(texto, x, y, 13, "secundario", negrito=True, espaco=2, superficie=superficie)

    def desenhar_base(self):
        base = self.base
        base.fill(C["fundo"])
        pg.draw.rect(base, C["painel"], (0, 0, JANELA[0], 87))
        pg.draw.line(base, C["borda"], (0, 86), (JANELA[0], 86))
        caixa(base, pg.Rect(32, 20, 46, 46), "cartao", 12, "borda")
        centro = (55, 43)
        pg.draw.circle(base, C["texto"], centro, 15)
        pg.draw.circle(base, C["menta"], centro, 15, draw_top_left=True, draw_bottom_left=True)
        pg.draw.line(base, C["moldura"], (54, 31), (54, 55), 2)
        self.texto("OTHELLO", 93, 18, 26, negrito=True, espaco=2, superficie=base)
        self.texto("INTELLIGENT AGENTS", 95, 51, 11, "secundario", negrito=True, espaco=2, superficie=base)

        caixa(base, MOLDURA.move(0, 6), "painel", 21)
        caixa(base, MOLDURA, "moldura", 20, "borda_verde")
        pg.draw.rect(base, C["grade"], TABULEIRO.inflate(4, 4), border_radius=3)
        for linha in range(CASAS):
            for coluna in range(CASAS):
                casa = retangulo_casa(linha, coluna)
                cor = "casa_clara" if (linha + coluna) % 2 else "casa_escura"
                pg.draw.rect(base, C[cor], (casa.x, casa.y, casa.width - 1, casa.height - 1))
            centro_x = retangulo_casa(0, linha).centerx
            centro_y = retangulo_casa(linha, 0).centery
            self.texto("ABCDEFGH"[linha], centro_x, TABULEIRO.top - 12, 12, "menta",
                       mono=True, alinhar="center", superficie=base)
            self.texto(str(linha + 1), TABULEIRO.left - 12, centro_y, 12, "menta",
                       mono=True, alinhar="center", superficie=base)

        for painel, titulo in zip(PAINEIS, ("PLACAR", "TURNO", "ÚLTIMAS FERRAMENTAS", "MÉTRICAS")):
            caixa(base, painel.move(0, 4), "fundo", 17)
            caixa(base, painel, "painel", 17, "borda")
            self.titulo(titulo, painel.x + 21, painel.y + 19, base)

        ferramentas, metricas = PAINEIS[2:]
        caixa(base, pg.Rect(ferramentas.x + 19, ferramentas.y + 48, 351, 43), "cartao", 9)
        self.texto("Nenhuma ferramenta nesta partida local", ferramentas.x + 32,
                   ferramentas.y + 69, 14, "secundario", alinhar="midleft", superficie=base)
        for rotulo, x in zip(("Tokens", "Chamadas LLM", "Tempo LLM"), (798, 917, 1036)):
            caixa(base, pg.Rect(x, metricas.y + 47, 113, 80), "cartao", 10)
            self.texto("—", x + 12, metricas.y + 55, 24, "texto", superficie=base)
            self.texto(rotulo, x + 12, metricas.y + 100, 12, "secundario", superficie=base)

    def botao(self, rect, texto, mouse, primario=False, habilitado=True):
        hover = habilitado and rect.collidepoint(mouse)
        fundo = ("menta_hover" if hover else "menta") if primario else ("hover" if hover else "cartao")
        caixa(self.tela, rect, fundo, 10, None if primario else "borda")
        cor = "menta_escura" if primario else ("texto" if habilitado else "desativado")
        self.texto(texto, *rect.center, 15, cor, negrito=True, alinhar="center")

    def desenhar_tabuleiro(self, estado, mouse):
        t = self.tela
        modos = (estado.jogadores[estado.motor.pretas], estado.jogadores[estado.motor.brancas])
        self.titulo(" × ".join(modo.upper() for modo in modos), MOLDURA.x + 2, 100)
        humana = estado.ativa and estado.jogadores[estado.atual] == "Humano"
        sobre = casa_em(mouse) if humana else None
        if sobre in estado.movimentos:
            pg.draw.rect(t, C["borda_verde"].lerp(C["menta"], .30), retangulo_casa(*sobre).inflate(-4, -4), border_radius=7)
        if estado.ultima is not None:
            pg.draw.rect(t, C["menta"], retangulo_casa(*estado.ultima).inflate(-6, -6), width=2, border_radius=8)
        if humana:
            for movimento in estado.movimentos:
                t.blit(self.marcador, self.marcador.get_rect(center=retangulo_casa(*movimento).center))
        for linha, fileira in enumerate(estado.tabuleiro):
            for coluna, peca in enumerate(fileira):
                if peca:
                    sprite = self.pecas[peca == estado.motor.pretas]
                    t.blit(sprite, sprite.get_rect(center=retangulo_casa(linha, coluna).center))

        if estado.pausada:
            aviso = pg.Rect(0, 0, 188, 47)
            aviso.center = TABULEIRO.center
            caixa(t, aviso.move(0, 4), "grade", 12)
            caixa(t, aviso, "painel", 12, "borda_verde")
            self.texto("Partida pausada", *aviso.center, 15, negrito=True, alinhar="center")

    def desenhar_placar(self, estado):
        painel = PAINEIS[0]
        pontos = estado.motor.contar_pecas(estado.tabuleiro)
        for indice, jogador in enumerate((estado.motor.pretas, estado.motor.brancas)):
            rect = pg.Rect(painel.x + 19, painel.y + 51 + indice * 82, 351, 71)
            ativo = estado.atual == jogador
            caixa(self.tela, rect, "cartao", 11, "menta" if ativo else "borda")
            sprite = self.mini_pecas[indice == 0]
            self.tela.blit(sprite, sprite.get_rect(center=(rect.x + 27, rect.centery)))
            self.texto(estado.nome_cor(jogador).upper(), rect.x + 52, rect.y + 13, 11,
                       "menta" if ativo else "secundario", negrito=True, espaco=1)
            self.texto(estado.jogadores[jogador], rect.x + 52, rect.y + 31, 18, negrito=True)
            self.texto(str(pontos[indice]), rect.right - 17, rect.centery, 36,
                       negrito=True, alinhar="midright")

    def desenhar_turno(self, estado):
        painel = PAINEIS[1]
        x = painel.x + 20
        badge = pg.Rect(painel.right - 78, painel.y + 15, 58, 28)
        caixa(self.tela, badge, "cartao", 8)
        self.texto(f"{estado.turno:02}", *badge.center, 14, "menta", mono=True, alinhar="center")
        if estado.atual is None:
            vencedor = estado.motor.obter_vencedor(estado.tabuleiro)
            titulo = "Empate" if vencedor not in estado.jogadores else f"{estado.nome_cor(vencedor)} venceram"
            status = "Partida encerrada"
        else:
            titulo = f"{estado.nome_cor(estado.atual)} · {estado.jogadores[estado.atual]}"
            if estado.pausada:
                status = "Partida pausada"
            elif estado.passou is not None:
                status = f"{estado.nome_cor(estado.passou)} passaram a vez"
            elif estado.jogadores[estado.atual] == "Heurístico":
                status = "Agente heurístico pensando…"
            else:
                status = "Aguardando jogada"
        self.texto(titulo, x, painel.y + 52, 22, negrito=True)
        pg.draw.circle(self.tela, C["menta"], (x + 4, painel.y + 103), 4)
        self.texto(status, x + 15, painel.y + 103, 14, "secundario", alinhar="midleft")

    def desenhar_sidebar(self, estado, mouse):
        t = self.tela
        t.blit(self.scrim, (0, 0))
        pg.draw.rect(t, C["fundo"], SIDEBAR.move(-8, 0))
        pg.draw.rect(t, C["painel"], SIDEBAR)
        pg.draw.line(t, C["borda"], SIDEBAR.topleft, SIDEBAR.bottomleft)
        self.texto("Nova partida", 864, 27, 28, negrito=True)
        self.botao(FECHAR, "×", mouse)
        self.texto("Escolha quem joga com cada cor.", 864, 76, 15, "secundario")
        pg.draw.line(t, C["borda"], (864, 112), (1176, 112))

        cores = (estado.motor.pretas, estado.motor.brancas)
        for i, y in enumerate((138, 316)):
            sprite = self.mini_pecas[i == 0]
            t.blit(sprite, sprite.get_rect(center=(875, y + 1)))
            self.titulo(f"PEÇAS {estado.nome_cor(cores[i]).upper()}", 898, y - 8)

        for indice, nome, rect in opcoes_sidebar():
            selecionado = estado.selecao[cores[indice]] == nome
            disponivel = nome in DISPONIVEIS
            hover = disponivel and rect.collidepoint(mouse)
            fundo = "moldura" if selecionado else ("hover" if hover else "cartao")
            caixa(t, rect, fundo, 10, "menta" if selecionado else "borda")
            centro = (rect.x + 17, rect.centery)
            pg.draw.circle(t, C["menta" if selecionado else "desativado"], centro, 5, 1)
            if selecionado:
                pg.draw.circle(t, C["menta"], centro, 2)
            self.texto(nome, rect.x + 30, rect.centery, 14,
                       "texto" if disponivel else "desativado", negrito=True, alinhar="midleft")

        self.texto("Estratégico e Operacional em breve.", 864, 486, 13, "secundario")
        pg.draw.line(t, C["borda"], (864, 677), (1176, 677))
        self.botao(INICIAR, "Iniciar partida", mouse, primario=True)

    def desenhar(self, estado, mouse):
        modal = estado.selecao is not None
        mouse_fundo = (-1, -1) if modal else mouse
        self.tela.blit(self.base, (0, 0))
        self.botao(BOTOES_TOPO["pausa"], "Retomar" if estado.pausada else "Pausar",
                   mouse_fundo, habilitado=estado.atual is not None)
        self.botao(BOTOES_TOPO["reiniciar"], "Reiniciar", mouse_fundo)
        self.botao(BOTOES_TOPO["nova"], "+  Nova partida", mouse_fundo, primario=True)
        self.desenhar_tabuleiro(estado, mouse_fundo)
        self.desenhar_placar(estado)
        self.desenhar_turno(estado)
        if modal:
            self.desenhar_sidebar(estado, mouse)
        return self.tela

    def limpar_cache(self):
        self.rotulo.cache_clear()
        self.fonte.cache_clear()


def encaixar(tamanho):
    escala = min(tamanho[0] / JANELA[0], tamanho[1] / JANELA[1])
    area = pg.Rect(0, 0, max(1, round(JANELA[0] * escala)), max(1, round(JANELA[1] * escala)))
    area.center = (tamanho[0] // 2, tamanho[1] // 2)
    return area


def posicao_logica(posicao, area):
    if not area.collidepoint(posicao):
        return -1, -1
    return (
        (posicao[0] - area.x) * JANELA[0] // area.width,
        (posicao[1] - area.y) * JANELA[1] // area.height,
    )


class InterfaceOthello:
    def __init__(self, motor):
        self.estado = EstadoInterface(motor)
        self.render = Renderizacao()
        self.proxima_heuristica = None

    def clique(self, posicao):
        estado = self.estado
        if estado.selecao is not None:
            if posicao == (-1, -1):
                return
            if FECHAR.collidepoint(posicao) or not SIDEBAR.collidepoint(posicao):
                estado.selecao = None
            elif INICIAR.collidepoint(posicao):
                estado.jogadores = estado.selecao
                estado.selecao = None
                estado.reiniciar()
            else:
                cores = (estado.motor.pretas, estado.motor.brancas)
                for i, nome, rect in opcoes_sidebar():
                    if nome in DISPONIVEIS and rect.collidepoint(posicao):
                        estado.selecao[cores[i]] = nome
                        break
            self.proxima_heuristica = None
            return
        if BOTOES_TOPO["nova"].collidepoint(posicao):
            estado.selecao = estado.jogadores.copy()
        elif BOTOES_TOPO["pausa"].collidepoint(posicao) and estado.atual is not None:
            estado.pausada = not estado.pausada
        elif BOTOES_TOPO["reiniciar"].collidepoint(posicao):
            estado.reiniciar()
        elif estado.ativa and estado.jogadores[estado.atual] == "Humano":
            casa = casa_em(posicao)
            if casa is not None:
                estado.jogar(*casa)
        else:
            return
        self.proxima_heuristica = None

    def evento(self, evento, area):
        if evento.type == pg.QUIT:
            return False
        if evento.type == pg.KEYDOWN and evento.key == pg.K_ESCAPE:
            self.estado.selecao = None
        if evento.type == pg.MOUSEBUTTONDOWN and evento.button == 1:
            self.clique(posicao_logica(evento.pos, area))
        return True

    def atualizar(self, agora):
        estado = self.estado
        if not estado.ativa or estado.jogadores[estado.atual] != "Heurístico":
            self.proxima_heuristica = None
        elif self.proxima_heuristica is None:
            self.proxima_heuristica = agora + ESPERA_HEURISTICA_MS
        elif agora >= self.proxima_heuristica:
            jogada = estado.motor.escolher_melhor_jogada(estado.tabuleiro, estado.atual)
            if jogada is not None:
                estado.jogar(jogada["row"], jogada["col"])
            self.proxima_heuristica = None

    def executar(self):
        relogio = pg.time.Clock()
        rodando = True
        ultimo_tamanho = None
        quadro_escalado = None
        while rodando:
            for evento in pg.event.get():
                area = encaixar(pg.display.get_surface().get_size())
                if not self.evento(evento, area):
                    rodando = False
                    break
            if not rodando:
                break

            janela = pg.display.get_surface()
            area = encaixar(janela.get_size())
            self.atualizar(pg.time.get_ticks())
            mouse = posicao_logica(pg.mouse.get_pos(), area)
            quadro = self.render.desenhar(self.estado, mouse)
            janela.fill(C["fundo"])
            if area.size == JANELA:
                janela.blit(quadro, area)
            else:
                if area.size != ultimo_tamanho:
                    quadro_escalado = pg.Surface(area.size).convert()
                    ultimo_tamanho = area.size
                pg.transform.smoothscale(quadro, area.size, quadro_escalado)
                janela.blit(quadro_escalado, area)
            pg.display.flip()
            relogio.tick(FPS)


def abrir_interface(motor):
    """Abre a janela local. O loop retorna ao notebook quando a janela fecha."""
    pg.display.init()
    pg.font.init()
    interface = None
    try:
        pg.display.set_caption("Othello · Intelligent Agents")
        pg.display.set_mode(JANELA, pg.RESIZABLE)
        interface = InterfaceOthello(motor)
        interface.executar()
    finally:
        if interface is not None:
            interface.render.limpar_cache()
        pg.font.quit()
        pg.display.quit()
