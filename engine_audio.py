"""
engine_audio.py
Responsável por:
  - Buscar músicas no YouTube (yt-dlp)
  - Fazer o download do áudio
  - Separar vocal e instrumental (Demucs — substitui o Spleeter)
"""

import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import yt_dlp

logger = logging.getLogger(__name__)

DIR_DOWNLOADS = Path("downloads")
DIR_TRACKS    = Path("tracks")
DIR_DOWNLOADS.mkdir(exist_ok=True)
DIR_TRACKS.mkdir(exist_ok=True)


@dataclass
class Faixa:
    titulo: str
    url: str
    caminho_original: Path
    caminho_vocal: Optional[Path]        = None
    caminho_instrumental: Optional[Path] = None
    duracao_segundos: float              = 0.0


def buscar_musica(query: str, max_resultados: int = 5) -> list[dict]:
    opcoes = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "default_search": "ytsearch",
    }
    with yt_dlp.YoutubeDL(opcoes) as ydl:
        info     = ydl.extract_info(f"ytsearch{max_resultados}:{query}", download=False)
        entradas = info.get("entries", [])

    resultados = []
    for e in entradas:
        mins, secs = divmod(e.get("duration") or 0, 60)
        resultados.append({
            "titulo":  e.get("title", "Sem título"),
            "url":     f"https://www.youtube.com/watch?v={e.get('id')}",
            "duracao": f"{mins}:{secs:02d}",
        })
    return resultados


def baixar_audio(url: str) -> Faixa:
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        meta = ydl.extract_info(url, download=False)

    titulo   = meta.get("title", "musica")
    duracao  = meta.get("duration", 0.0)
    nome_arq = _nome_seguro(titulo)
    destino  = DIR_DOWNLOADS / f"{nome_arq}.wav"

    if destino.exists():
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
    with yt_dlp.YoutubeDL(opcoes) as ydl:
        ydl.download([url])

    return Faixa(titulo=titulo, url=url,
                 caminho_original=destino, duracao_segundos=duracao)


def separar_faixa(faixa: Faixa) -> Faixa:
    """
    Usa o Demucs (htdemucs, 2 stems) para separar vocal e instrumental.
    Gera: vocals.wav + no_vocals.wav em /tracks/<titulo>/htdemucs/<titulo>/
    """
    nome_arq  = _nome_seguro(faixa.titulo)
    pasta_out = DIR_TRACKS / nome_arq
    stem_dir  = pasta_out / "htdemucs" / nome_arq

    vocal_path = stem_dir / "vocals.wav"
    instr_path = stem_dir / "no_vocals.wav"

    if vocal_path.exists() and instr_path.exists():
        faixa.caminho_vocal        = vocal_path
        faixa.caminho_instrumental = instr_path
        return faixa

    pasta_out.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python", "-m", "demucs",
        "--two-stems=vocals",
        "-o", str(pasta_out),
        str(faixa.caminho_original),
    ]

    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"Demucs falhou: {resultado.stderr}")

    faixa.caminho_vocal        = vocal_path
    faixa.caminho_instrumental = instr_path
    return faixa


def preparar_musica(url: str) -> Faixa:
    faixa = baixar_audio(url)
    faixa = separar_faixa(faixa)
    return faixa


def _nome_seguro(texto: str) -> str:
    for ch in r'\/:*?"<>|':
        texto = texto.replace(ch, "_")
    return texto[:80].strip()
