"""
biometria.py
Responsável por:
  - Cadastrar (enroll) a "assinatura de voz" de cada jogador
  - Salvar e carregar perfis em /perfis_voz
  - Identificar quem está cantando em tempo real
"""

import logging
import pickle
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch
from speechbrain.inference.speaker import SpeakerRecognition

logger = logging.getLogger(__name__)

# ── Configurações ──────────────────────────────────────────────────────
DIR_PERFIS        = Path("perfis_voz")
MODELO_FONTE      = "speechbrain/spkrec-ecapa-voxceleb"
MODELO_LOCAL      = "models/ecapa_tdnn"
LIMIAR_SIMILARIDADE = 0.75    # cosine similarity mínima para confirmar ID
SEGUNDOS_MINIMOS    = 5       # duração mínima de áudio para enrollment

DIR_PERFIS.mkdir(exist_ok=True)


# ── Estrutura de dados de um jogador ──────────────────────────────────
@dataclass
class Jogador:
    """Perfil de um jogador com sua assinatura de voz."""
    jogador_id: str
    nome: str
    embedding: Optional[torch.Tensor] = None

    @property
    def cadastrado(self) -> bool:
        return self.embedding is not None


# ══════════════════════════════════════════════════════════════════════ #
#  CLASSE PRINCIPAL                                                      #
# ══════════════════════════════════════════════════════════════════════ #

class Biometria:
    """
    Gerencia o reconhecimento de voz dos jogadores.

    Uso básico:
        bio = Biometria()
        bio.cadastrar("j1", "Ana", audio_numpy)
        quem = bio.identificar(chunk_audio)
    """

    def __init__(self):
        logger.info("Carregando modelo ECAPA-TDNN (pode demorar na 1ª vez)…")
        self.modelo = SpeakerRecognition.from_hparams(
            source=MODELO_FONTE,
            savedir=MODELO_LOCAL,
        )
        self.jogadores: dict[str, Jogador] = {}
        self._carregar_todos_perfis()

    # ------------------------------------------------------------------ #
    #  Cadastro (Enrollment)                                               #
    # ------------------------------------------------------------------ #

    def registrar(self, jogador_id: str, nome: str) -> Jogador:
        """
        Cria um perfil vazio para o jogador (sem áudio ainda).
        Chame `cadastrar()` depois para adicionar a assinatura de voz.
        """
        jogador = Jogador(jogador_id=jogador_id, nome=nome)
        self.jogadores[jogador_id] = jogador
        logger.info("Jogador registrado: %s (%s)", nome, jogador_id)
        return jogador

    def cadastrar(
        self,
        jogador_id: str,
        audio: np.ndarray,
        sample_rate: int = 16000,
    ) -> bool:
        """
        Gera e salva a assinatura de voz do jogador a partir de um áudio.

        Args:
            jogador_id: ID do jogador (deve estar registrado).
            audio: Array numpy mono com amostras de voz.
            sample_rate: Taxa de amostragem (padrão 16 kHz).

        Returns:
            True se o cadastro foi bem-sucedido.
        """
        if jogador_id not in self.jogadores:
            raise ValueError(
                f"Jogador '{jogador_id}' não encontrado. "
                "Chame registrar() primeiro."
            )

        duracao = len(audio) / sample_rate
        if duracao < SEGUNDOS_MINIMOS:
            logger.warning(
                "Áudio muito curto (%.1fs). Recomendado: >= %ds.",
                duracao, SEGUNDOS_MINIMOS,
            )

        embedding = self._gerar_embedding(audio, sample_rate)
        self.jogadores[jogador_id].embedding = embedding
        self._salvar_perfil(jogador_id)

        logger.info("✅ Cadastro concluído: %s", self.jogadores[jogador_id].nome)
        return True

    # ------------------------------------------------------------------ #
    #  Identificação em tempo real                                         #
    # ------------------------------------------------------------------ #

    def identificar(
        self,
        audio_chunk: np.ndarray,
        sample_rate: int = 16000,
    ) -> Optional[str]:
        """
        Identifica qual jogador está cantando em um chunk de áudio.

        Args:
            audio_chunk: Fragmento de áudio capturado pelo microfone.
            sample_rate: Taxa de amostragem.

        Returns:
            jogador_id do jogador identificado, ou None se desconhecido.
        """
        cadastrados = {
            jid: j for jid, j in self.jogadores.items() if j.cadastrado
        }
        if not cadastrados:
            logger.warning("Nenhum jogador cadastrado.")
            return None

        embedding_query = self._gerar_embedding(audio_chunk, sample_rate)

        melhor_id    = None
        melhor_score = -1.0

        for jid, jogador in cadastrados.items():
            score = _similaridade_cosseno(embedding_query, jogador.embedding)
            logger.debug("  %s → score: %.3f", jogador.nome, score)
            if score > melhor_score:
                melhor_score = score
                melhor_id    = jid

        if melhor_score >= LIMIAR_SIMILARIDADE:
            nome = self.jogadores[melhor_id].nome
            logger.info("🎤 Identificado: %s (score=%.3f)", nome, melhor_score)
            return melhor_id

        logger.info("Voz não reconhecida (melhor score=%.3f)", melhor_score)
        return None

    def identificar_dois_mics(
        self,
        audio_mic1: np.ndarray,
        audio_mic2: np.ndarray,
        sample_rate: int = 16000,
    ) -> dict[str, Optional[str]]:
        """
        Identifica jogadores em dois microfones simultaneamente.

        Returns:
            {"mic1": jogador_id | None, "mic2": jogador_id | None}
        """
        return {
            "mic1": self.identificar(audio_mic1, sample_rate),
            "mic2": self.identificar(audio_mic2, sample_rate),
        }

    # ------------------------------------------------------------------ #
    #  Persistência de perfis em /perfis_voz                              #
    # ------------------------------------------------------------------ #

    def _salvar_perfil(self, jogador_id: str) -> None:
        """Salva o embedding do jogador em disco."""
        jogador  = self.jogadores[jogador_id]
        caminho  = DIR_PERFIS / f"{jogador_id}.pkl"
        with open(caminho, "wb") as f:
            pickle.dump({"nome": jogador.nome, "embedding": jogador.embedding}, f)
        logger.info("Perfil salvo: %s", caminho)

    def _carregar_perfil(self, caminho: Path) -> None:
        """Carrega um perfil salvo e adiciona aos jogadores."""
        with open(caminho, "rb") as f:
            dados = pickle.load(f)
        jogador_id = caminho.stem
        self.jogadores[jogador_id] = Jogador(
            jogador_id=jogador_id,
            nome=dados["nome"],
            embedding=dados["embedding"],
        )
        logger.info("Perfil carregado: %s (%s)", dados["nome"], jogador_id)

    def _carregar_todos_perfis(self) -> None:
        """Carrega todos os perfis salvos em /perfis_voz na inicialização."""
        for arquivo in DIR_PERFIS.glob("*.pkl"):
            try:
                self._carregar_perfil(arquivo)
            except Exception as e:
                logger.warning("Erro ao carregar %s: %s", arquivo, e)

    # ------------------------------------------------------------------ #
    #  Helper interno                                                      #
    # ------------------------------------------------------------------ #

    def _gerar_embedding(
        self, audio: np.ndarray, sample_rate: int
    ) -> torch.Tensor:
        """Converte um array de áudio em um embedding ECAPA-TDNN."""
        waveform = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            embedding = self.modelo.encode_batch(waveform)
        return embedding.squeeze(0)


# ── Função utilitária ──────────────────────────────────────────────────
def _similaridade_cosseno(a: torch.Tensor, b: torch.Tensor) -> float:
    """Calcula a similaridade cosseno entre dois embeddings."""
    return torch.nn.functional.cosine_similarity(
        a.unsqueeze(0), b.unsqueeze(0)
    ).item()
