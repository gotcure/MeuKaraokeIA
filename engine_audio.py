"""
engine_audio.py
- Busca músicas no YouTube (yt-dlp)
- Download do áudio
- Separação vocal/instrumental (Demucs)
- Busca de letra sincronizada (lrclib.net)
"""

import re
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import requests
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
    letra: list[dict]                    = field(default_factory=list)
    # letra = [{"tempo": float, "linha": str}, ...]


# ══════════════════════════════════════════════════════════════════════ #
#  BUSCA YOUTUBE                                                         #
# ══════════════════════════════════════════════════════════════════════ #

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
        mins, secs = divmod(int(e.get("duration") or 0), 60)
        resultados.append({
            "titulo":  e.get("title", "Sem título"),
            "url":     f"https://www.youtube.com/watch?v={e.get('id')}",
            "duracao": f"{mins}:{secs:02d}",
        })
    return resultados


# ══════════════════════════════════════════════════════════════════════ #
#  DOWNLOAD                                                              #
# ══════════════════════════════════════════════════════════════════════ #

def baixar_audio(url: str) -> Faixa:
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        meta = ydl.extract_info(url, download=False)

    titulo   = meta.get("title", "musica")
    duracao  = meta.get("duration", 0.0)
    nome_arq = _nome_seguro(titulo)
    destino  = DIR_DOWNLOADS / f"{nome_arq}.wav"

    if not destino.exists():
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


# ══════════════════════════════════════════════════════════════════════ #
#  SEPARAÇÃO (Demucs)                                                    #
# ══════════════════════════════════════════════════════════════════════ #

def separar_faixa(faixa: Faixa) -> Faixa:
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


# ══════════════════════════════════════════════════════════════════════ #
#  LETRA SINCRONIZADA (lrclib.net — gratuito, sem chave de API)         #
# ══════════════════════════════════════════════════════════════════════ #

def buscar_letra(titulo: str, artista: str = "") -> list[dict]:
    """
    Busca letra sincronizada na API pública lrclib.net.

    Returns:
        [{"tempo": float, "linha": str}, ...] ordenado por tempo.
        Lista vazia se não encontrar.
    """
    try:
        query  = f"{artista} {titulo}".strip()
        resp   = requests.get(
            "https://lrclib.net/api/search",
            params={"q": query},
            timeout=8,
        )
        resp.raise_for_status()
        dados = resp.json()

        if not dados:
            return []

        # Prefere letra sincronizada (.lrc)
        for item in dados:
            lrc = item.get("syncedLyrics")
            if lrc:
                return _parsear_lrc(lrc)

        # Fallback: letra simples com tempo estimado (3s por linha)
        plain = dados[0].get("plainLyrics", "")
        if plain:
            linhas = [l.strip() for l in plain.split("\n") if l.strip()]
            return [{"tempo": i * 3.0, "linha": l} for i, l in enumerate(linhas)]

        return []

    except Exception as e:
        logger.warning("Letra não encontrada: %s", e)
        return []


def _parsear_lrc(lrc: str) -> list[dict]:
    """Converte formato LRC [mm:ss.xx]texto em lista de dicts."""
    padrao = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")
    linhas = []
    for linha in lrc.split("\n"):
        m = padrao.match(linha.strip())
        if m:
            tempo = int(m.group(1)) * 60 + float(m.group(2))
            texto = m.group(3).strip()
            if texto:
                linhas.append({"tempo": tempo, "linha": texto})
    return sorted(linhas, key=lambda x: x["tempo"])


# ══════════════════════════════════════════════════════════════════════ #
#  FLUXO COMPLETO                                                        #
# ══════════════════════════════════════════════════════════════════════ #

def preparar_musica(url: str) -> Faixa:
    """Download + separação + busca de letra em uma chamada só."""
    faixa        = baixar_audio(url)
    faixa        = separar_faixa(faixa)
    faixa.letra  = buscar_letra(faixa.titulo)
    return faixa


def _nome_seguro(texto: str) -> str:
    for ch in r'\/:*?"<>|':
        texto = texto.replace(ch, "_")
    return texto[:80].strip()
