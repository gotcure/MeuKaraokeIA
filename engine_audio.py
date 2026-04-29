"""
engine_audio.py
Responsável por:
  - Buscar músicas no YouTube (yt-dlp)
  - Fazer o download do áudio
  - Separar vocal e instrumental (Spleeter)
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import yt_dlp
from spleeter.separator import Separator

logger = logging.getLogger(__name__)

# ── Pastas do projeto ──────────────────────────────────────────────────
DIR_DOWNLOADS = Path("downloads")
DIR_TRACKS    = Path("tracks")

DIR_DOWNLOADS.mkdir(exist_ok=True)
DIR_TRACKS.mkdir(exist_ok=True)


# ── Estrutura de dados de uma faixa ───────────────────────────────────
@dataclass
class Faixa:
    """Representa uma música baixada e (opcionalmente) separada."""
    titulo: str
    url: str
    caminho_original: Path
    caminho_vocal: Optional[Path]       = None
    caminho_instrumental: Optional[Path] = None
    duracao_segundos: float             = 0.0


# ══════════════════════════════════════════════════════════════════════ #
#  BUSCA                                                                 #
# ══════════════════════════════════════════════════════════════════════ #

def buscar_musica(query: str, max_resultados: int = 5) -> list[dict]:
    """
    Busca músicas no YouTube sem fazer download.

    Args:
        query: Nome da música ou artista.
        max_resultados: Quantidade máxima de resultados.

    Returns:
        Lista de dicts com 'titulo', 'url', 'duracao'.
    """
    opcoes = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "default_search": "ytsearch",
    }

    with yt_dlp.YoutubeDL(opcoes) as ydl:
        info = ydl.extract_info(
            f"ytsearch{max_resultados}:{query}", download=False
        )
        entradas = info.get("entries", [])

    resultados = []
    for e in entradas:
        mins, secs = divmod(e.get("duration") or 0, 60)
        resultados.append({
            "titulo":  e.get("title", "Sem título"),
            "url":     f"https://www.youtube.com/watch?v={e.get('id')}",
            "duracao": f"{mins}:{secs:02d}",
        })

    logger.info("%d resultado(s) encontrado(s) para '%s'.", len(resultados), query)
    return resultados


# ══════════════════════════════════════════════════════════════════════ #
#  DOWNLOAD                                                              #
# ══════════════════════════════════════════════════════════════════════ #

def baixar_audio(url: str) -> Faixa:
    """
    Faz o download do áudio de uma URL do YouTube em formato WAV.

    Args:
        url: URL do vídeo no YouTube.

    Returns:
        Objeto Faixa com o caminho do áudio baixado.
    """
    # Nome seguro para o arquivo, baseado no título da música
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        meta = ydl.extract_info(url, download=False)

    titulo   = meta.get("title", "musica")
    duracao  = meta.get("duration", 0.0)
    nome_arq = _nome_seguro(titulo)
    destino  = DIR_DOWNLOADS / f"{nome_arq}.wav"

    if destino.exists():
        logger.info("Arquivo já existe em cache: %s", destino)
        return Faixa(titulo=titulo, url=url,
                     caminho_original=destino, duracao_segundos=duracao)

    opcoes = {
        "format": "bestaudio/best",
        "outtmpl": str(DIR_DOWNLOADS / f"{nome_arq}.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "192",
        }],
        "quiet": True,
    }

    logger.info("Baixando: %s", titulo)
    with yt_dlp.YoutubeDL(opcoes) as ydl:
        ydl.download([url])

    logger.info("Download concluído → %s", destino)
    return Faixa(titulo=titulo, url=url,
                 caminho_original=destino, duracao_segundos=duracao)


# ══════════════════════════════════════════════════════════════════════ #
#  SEPARAÇÃO DE STEMS (Spleeter)                                         #
# ══════════════════════════════════════════════════════════════════════ #

def separar_faixa(faixa: Faixa) -> Faixa:
    """
    Usa o Spleeter (2 stems) para separar vocal e instrumental.
    Os arquivos são salvos em /tracks/<titulo>/.

    Args:
        faixa: Objeto Faixa com o áudio original já baixado.

    Returns:
        O mesmo objeto Faixa atualizado com os caminhos dos stems.
    """
    nome_arq  = _nome_seguro(faixa.titulo)
    pasta_out = DIR_TRACKS / nome_arq

    vocal_path = pasta_out / "vocals.wav"
    instr_path = pasta_out / "accompaniment.wav"

    if vocal_path.exists() and instr_path.exists():
        logger.info("Stems já existem: %s", pasta_out)
        faixa.caminho_vocal        = vocal_path
        faixa.caminho_instrumental = instr_path
        return faixa

    pasta_out.mkdir(parents=True, exist_ok=True)

    logger.info("Separando stems de '%s' com Spleeter…", faixa.titulo)
    separador = Separator("spleeter:2stems")
    separador.separate_to_file(str(faixa.caminho_original), str(pasta_out))

    # Spleeter salva em <pasta_out>/<nome_sem_ext>/vocals.wav
    sub = pasta_out / nome_arq
    if sub.exists():
        faixa.caminho_vocal        = sub / "vocals.wav"
        faixa.caminho_instrumental = sub / "accompaniment.wav"
    else:
        faixa.caminho_vocal        = vocal_path
        faixa.caminho_instrumental = instr_path

    logger.info("Stems prontos: vocal=%s | instrumental=%s",
                faixa.caminho_vocal, faixa.caminho_instrumental)
    return faixa


# ══════════════════════════════════════════════════════════════════════ #
#  FLUXO COMPLETO                                                        #
# ══════════════════════════════════════════════════════════════════════ #

def preparar_musica(url: str) -> Faixa:
    """
    Combina download + separação em uma única chamada conveniente.

    Args:
        url: URL do YouTube.

    Returns:
        Faixa completamente pronta para o jogo.
    """
    faixa = baixar_audio(url)
    faixa = separar_faixa(faixa)
    return faixa


# ── Helper ─────────────────────────────────────────────────────────────
def _nome_seguro(texto: str) -> str:
    """Remove caracteres inválidos de um nome de arquivo."""
    chars_invalidos = r'\/:*?"<>|'
    for ch in chars_invalidos:
        texto = texto.replace(ch, "_")
    return texto[:80].strip()
