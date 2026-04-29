"""
pontuacao.py
Responsável por:
  - Detectar a frequência fundamental (pitch) do microfone
  - Comparar com o vocal de referência extraído pelo Spleeter
  - Calcular e acumular a pontuação de cada jogador
  - Gerenciar o modo Battle (placar competitivo)
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

import librosa

logger = logging.getLogger(__name__)

# ── Configurações de pontuação ─────────────────────────────────────────
HOP_LENGTH          = 512     # amostras por frame de análise
TOLERANCIA_CENTS    = 50      # ±50 cents = meio semitom de tolerância
PONTOS_POR_FRAME    = 100     # pontuação máxima por frame perfeito
LIMITE_SILENCIO_DB  = -40     # frames mais silenciosos que isso são ignorados
SR_PADRAO           = 16_000  # taxa de amostragem padrão


# ══════════════════════════════════════════════════════════════════════ #
#  ESTRUTURAS DE DADOS                                                   #
# ══════════════════════════════════════════════════════════════════════ #

@dataclass
class ResultadoFrame:
    """Pontuação de um único frame de áudio."""
    tempo: float
    jogador_id: str
    hz_referencia: float
    hz_detectado: float
    erro_cents: float
    pontos: float
    silencioso: bool


@dataclass
class PlacarJogador:
    """Placar acumulado de um jogador na sessão."""
    jogador_id: str
    nome: str
    frames_totais: int   = 0
    frames_pontuados: int = 0
    pontos_brutos: float = 0.0

    @property
    def precisao(self) -> float:
        """Percentual de frames onde o jogador acertou o pitch."""
        if self.frames_totais == 0:
            return 0.0
        return self.frames_pontuados / self.frames_totais * 100

    @property
    def pontuacao_final(self) -> float:
        """Média de pontos nos frames em que havia referência."""
        if self.frames_pontuados == 0:
            return 0.0
        return self.pontos_brutos / self.frames_pontuados

    def resumo(self) -> dict:
        return {
            "jogador_id":      self.jogador_id,
            "nome":            self.nome,
            "pontuacao":       round(self.pontuacao_final, 1),
            "precisao":        round(self.precisao, 1),
            "frames_pontuados": self.frames_pontuados,
        }


# ══════════════════════════════════════════════════════════════════════ #
#  DETECÇÃO DE PITCH                                                     #
# ══════════════════════════════════════════════════════════════════════ #

class DetectorPitch:
    """Detecta a frequência fundamental (F0) de um sinal de áudio."""

    def __init__(self, sample_rate: int = SR_PADRAO):
        self.sr = sample_rate

    def detectar(
        self, audio: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Detecta o pitch frame a frame usando pYIN (librosa).

        Returns:
            f0_hz: Array com a frequência em Hz por frame (0 = não detectado).
            voiced: Array booleano indicando frames com voz.
        """
        f0, voiced, _ = librosa.pyin(
            audio,
            fmin=librosa.note_to_hz("C2"),   # ~65 Hz
            fmax=librosa.note_to_hz("C7"),   # ~2093 Hz
            sr=self.sr,
            hop_length=HOP_LENGTH,
        )
        f0 = np.nan_to_num(f0, nan=0.0)
        return f0, voiced

    def rms_db(self, audio: np.ndarray) -> np.ndarray:
        """Calcula o volume em dB por frame (para detectar silêncio)."""
        rms = librosa.feature.rms(y=audio, hop_length=HOP_LENGTH)[0]
        return librosa.amplitude_to_db(rms, ref=np.max)


# ══════════════════════════════════════════════════════════════════════ #
#  SISTEMA DE PONTUAÇÃO                                                  #
# ══════════════════════════════════════════════════════════════════════ #

class Pontuacao:
    """
    Compara o pitch do microfone com o vocal de referência
    e gerencia o placar da sessão (modo normal e modo Battle).

    Uso:
        pts = Pontuacao()
        pts.iniciar_sessao({"j1": "Ana", "j2": "Bruno"})
        pts.processar_chunk("j1", audio_mic, audio_referencia)
        resultado = pts.resultado_battle()
    """

    def __init__(self, sample_rate: int = SR_PADRAO):
        self.sr       = sample_rate
        self.detector = DetectorPitch(sample_rate)
        self._placares: dict[str, PlacarJogador] = {}

    # ------------------------------------------------------------------ #
    #  Sessão                                                              #
    # ------------------------------------------------------------------ #

    def iniciar_sessao(self, jogadores: dict[str, str]) -> None:
        """
        Inicializa o placar para a sessão atual.

        Args:
            jogadores: {jogador_id: nome}
        """
        self._placares = {
            jid: PlacarJogador(jogador_id=jid, nome=nome)
            for jid, nome in jogadores.items()
        }
        logger.info("Sessão iniciada: %s", list(jogadores.values()))

    def placares_atuais(self) -> dict[str, dict]:
        """Retorna o resumo do placar de todos os jogadores."""
        return {jid: p.resumo() for jid, p in self._placares.items()}

    # ------------------------------------------------------------------ #
    #  Processamento de chunk                                              #
    # ------------------------------------------------------------------ #

    def processar_chunk(
        self,
        jogador_id: str,
        audio_mic: np.ndarray,
        audio_referencia: np.ndarray,
    ) -> list[ResultadoFrame]:
        """
        Processa um chunk de áudio e atualiza o placar do jogador.

        Args:
            jogador_id: ID do jogador ativo no momento.
            audio_mic: Áudio capturado pelo microfone.
            audio_referencia: Vocal de referência (mesma duração).

        Returns:
            Lista de ResultadoFrame, um por frame analisado.
        """
        if jogador_id not in self._placares:
            raise ValueError(
                f"Jogador '{jogador_id}' não está na sessão. "
                "Chame iniciar_sessao() primeiro."
            )

        ref_f0,  ref_voiced  = self.detector.detectar(audio_referencia)
        mic_f0,  mic_voiced  = self.detector.detectar(audio_mic)
        mic_db               = self.detector.rms_db(audio_mic)

        n_frames = min(len(ref_f0), len(mic_f0))
        placar   = self._placares[jogador_id]
        frames: list[ResultadoFrame] = []

        for i in range(n_frames):
            tempo      = i * HOP_LENGTH / self.sr
            silencioso = mic_db[i] < LIMITE_SILENCIO_DB
            ref_hz     = float(ref_f0[i])
            mic_hz     = float(mic_f0[i])

            placar.frames_totais += 1

            # Ignorar silêncio ou ausência de voz na referência
            if silencioso or not ref_voiced[i] or ref_hz == 0:
                frames.append(
                    ResultadoFrame(tempo, jogador_id,
                                   ref_hz, mic_hz, 0.0, 0.0, silencioso)
                )
                continue

            erro_cents, pontos = _calcular_pontos(ref_hz, mic_hz, mic_voiced[i])
            placar.frames_pontuados += 1
            placar.pontos_brutos    += pontos

            frames.append(
                ResultadoFrame(tempo, jogador_id,
                               ref_hz, mic_hz, erro_cents, pontos, False)
            )

        return frames

    # ------------------------------------------------------------------ #
    #  Modo Battle                                                         #
    # ------------------------------------------------------------------ #

    def resultado_battle(self) -> dict:
        """
        Calcula o vencedor e o ranking final do modo Battle.

        Returns:
            {
              "vencedor": nome,
              "pontuacao_vencedor": float,
              "ranking": [resumo_jogador, ...]
            }
        """
        if not self._placares:
            return {"vencedor": None, "ranking": []}

        ranking = sorted(
            self._placares.values(),
            key=lambda p: p.pontuacao_final,
            reverse=True,
        )

        vencedor = ranking[0]
        logger.info(
            "🏆 Vencedor: %s com %.1f pontos!",
            vencedor.nome, vencedor.pontuacao_final,
        )

        return {
            "vencedor":            vencedor.nome,
            "pontuacao_vencedor":  round(vencedor.pontuacao_final, 1),
            "ranking":             [p.resumo() for p in ranking],
        }


# ══════════════════════════════════════════════════════════════════════ #
#  HELPERS PRIVADOS                                                      #
# ══════════════════════════════════════════════════════════════════════ #

def _calcular_pontos(
    ref_hz: float,
    mic_hz: float,
    mic_com_voz: bool,
) -> tuple[float, float]:
    """
    Calcula o erro em cents e os pontos de um único frame.

    Returns:
        (erro_cents, pontos)   —  pontos entre 0 e PONTOS_POR_FRAME.
    """
    if mic_hz <= 0 or not mic_com_voz:
        return 0.0, 0.0

    erro_cents = abs(1200 * np.log2(mic_hz / ref_hz))

    if erro_cents <= TOLERANCIA_CENTS:
        # Pontuação linear: 100 pts se perfeito, 0 no limite da tolerância
        pontos = PONTOS_POR_FRAME * (1 - erro_cents / TOLERANCIA_CENTS)
    else:
        pontos = 0.0

    return round(erro_cents, 2), round(pontos, 2)
