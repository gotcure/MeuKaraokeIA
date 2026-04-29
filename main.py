"""
main.py
Ponto de entrada do Smart Karaoke.
Execute com:  streamlit run main.py
"""

import time
import logging
import numpy as np
import streamlit as st

from engine_audio import buscar_musica, preparar_musica, Faixa
from biometria   import Biometria
from pontuacao   import Pontuacao

# ── Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ══════════════════════════════════════════════════════════════════════ #
#  CONFIGURAÇÃO DA PÁGINA                                                #
# ══════════════════════════════════════════════════════════════════════ #

st.set_page_config(
    page_title="🎤 Meu Karaokê IA",
    page_icon="🎤",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* Fundo escuro nos cards */
.card {
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border-radius: 14px;
    padding: 1.5rem;
    color: white;
    text-align: center;
    margin-bottom: 0.5rem;
}
.card-pontos  { font-size: 3rem; font-weight: 800; color: #a78bfa; }
.card-nome    { font-size: 1.1rem; margin-bottom: 0.3rem; }
.card-detalhe { font-size: 0.85rem; color: #94a3b8; }

/* Banner do vencedor */
.banner-vencedor {
    background: linear-gradient(135deg, #f59e0b, #ef4444);
    border-radius: 14px;
    padding: 1.2rem 2rem;
    text-align: center;
    font-size: 1.6rem;
    font-weight: 800;
    color: white;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════ #
#  INICIALIZAÇÃO — recursos em cache e estado da sessão                  #
# ══════════════════════════════════════════════════════════════════════ #

@st.cache_resource
def carregar_biometria() -> Biometria:
    return Biometria()

@st.cache_resource
def carregar_pontuacao() -> Pontuacao:
    return Pontuacao()

def _init_estado() -> None:
    defaults: dict = {
        "pagina":          "🏠 Início",
        "faixa":           None,          # objeto Faixa atual
        "jogadores":       {},            # {id: nome}
        "cadastrados":     set(),         # ids com enrollment feito
        "modo_battle":     False,
        "sessao_ativa":    False,
        "placares":        {},            # resultado da última sessão
        "resultado_battle": None,
    }
    for chave, valor in defaults.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor

_init_estado()

biometria = carregar_biometria()
pontuacao = carregar_pontuacao()

PAGINAS = [
    "🏠 Início",
    "🔍 Buscar Música",
    "🎙️ Cadastrar Jogadores",
    "🎤 Cantar",
    "🏆 Resultados",
]


# ══════════════════════════════════════════════════════════════════════ #
#  SIDEBAR                                                               #
# ══════════════════════════════════════════════════════════════════════ #

with st.sidebar:
    st.title("🎤 Meu Karaokê IA")
    st.divider()

    pagina = st.radio("Navegar", PAGINAS, label_visibility="collapsed")
    st.session_state.pagina = pagina

    st.divider()
    st.session_state.modo_battle = st.toggle(
        "⚔️ Modo Battle", value=st.session_state.modo_battle
    )
    if st.session_state.modo_battle:
        st.success("Competição ativada!")

    # Status rápido
    st.divider()
    st.caption("Status da sessão")
    st.write("🎵 Música:", "✅" if st.session_state.faixa else "—")
    st.write("👥 Jogadores:", len(st.session_state.jogadores))
    st.write("✅ Cadastrados:", len(st.session_state.cadastrados))


# ══════════════════════════════════════════════════════════════════════ #
#  PÁGINAS                                                               #
# ══════════════════════════════════════════════════════════════════════ #

# ────────────────────────────────────────────────────────────────────── #
#  1. INÍCIO                                                             #
# ────────────────────────────────────────────────────────────────────── #
if pagina == "🏠 Início":
    st.title("🎤 Meu Karaokê IA")
    st.markdown("""
    Bem-vindo ao sistema de Karaokê com Inteligência Artificial!

    ### Como funciona:
    | Passo | O que fazer |
    |-------|-------------|
    | 1️⃣ | **Buscar Música** — pesquise no YouTube |
    | 2️⃣ | **Cadastrar Jogadores** — registre a voz de cada um |
    | 3️⃣ | **Cantar** — o sistema identifica quem canta e pontua |
    | 4️⃣ | **Resultados** — veja o placar e o vencedor do Battle |
    """)

    c1, c2, c3 = st.columns(3)
    c1.metric("Jogadores", len(st.session_state.jogadores))
    c2.metric("Cadastrados", len(st.session_state.cadastrados))
    c3.metric("Música pronta", "✅" if st.session_state.faixa else "Não")


# ────────────────────────────────────────────────────────────────────── #
#  2. BUSCAR MÚSICA                                                      #
# ────────────────────────────────────────────────────────────────────── #
elif pagina == "🔍 Buscar Música":
    st.title("🔍 Buscar Música")

    query = st.text_input(
        "Nome da música ou artista:",
        placeholder="ex: Legião Urbana Tempo Perdido",
    )

    if st.button("🔎 Buscar", type="primary") and query:
        with st.spinner("Buscando no YouTube…"):
            resultados = buscar_musica(query, max_resultados=6)

        if not resultados:
            st.warning("Nenhum resultado encontrado. Tente outra busca.")
        else:
            st.markdown("### Resultados")
            for r in resultados:
                with st.container(border=True):
                    col_info, col_btn = st.columns([5, 1])
                    col_info.markdown(f"**{r['titulo']}**  \n⏱️ {r['duracao']}")

                    if col_btn.button("Selecionar", key=r["url"]):
                        with st.spinner("⬇️ Baixando e separando áudio… (pode levar alguns minutos)"):
                            faixa = preparar_musica(r["url"])
                        st.session_state.faixa = faixa
                        st.success(f"✅ **{faixa.titulo}** está pronta!")


# ────────────────────────────────────────────────────────────────────── #
#  3. CADASTRAR JOGADORES                                                #
# ────────────────────────────────────────────────────────────────────── #
elif pagina == "🎙️ Cadastrar Jogadores":
    st.title("🎙️ Cadastrar Jogadores")

    # Formulário para adicionar jogador
    with st.form("form_jogador", clear_on_submit=True):
        c1, c2 = st.columns(2)
        novo_id   = c1.text_input("ID único", placeholder="ex: j1")
        novo_nome = c2.text_input("Nome",     placeholder="ex: Ana")
        adicionar = st.form_submit_button("➕ Adicionar Jogador")

    if adicionar:
        if not novo_id or not novo_nome:
            st.error("Preencha o ID e o nome do jogador.")
        elif novo_id in st.session_state.jogadores:
            st.warning(f"ID '{novo_id}' já está cadastrado.")
        else:
            biometria.registrar(novo_id, novo_nome)
            st.session_state.jogadores[novo_id] = novo_nome
            st.success(f"Jogador **{novo_nome}** adicionado!")

    # Lista de jogadores
    if st.session_state.jogadores:
        st.divider()
        st.markdown("### Jogadores")
        for jid, jnome in st.session_state.jogadores.items():
            com_cadastro = jid in st.session_state.cadastrados
            col_nome, col_status, col_acao = st.columns([3, 2, 2])
            col_nome.markdown(f"**{jnome}** `{jid}`")
            col_status.markdown("✅ Voz cadastrada" if com_cadastro else "⏳ Pendente")

            if not com_cadastro:
                if col_acao.button("🎙️ Gravar voz", key=f"gravar_{jid}"):
                    # Em produção: grave 5s do microfone com sounddevice
                    # audio_real = sounddevice.rec(5*16000, samplerate=16000, channels=1)
                    st.info(f"Gravando 5s de voz para **{jnome}**… (simulado)")
                    audio_simulado = np.random.randn(16000 * 5).astype(np.float32)
                    biometria.cadastrar(jid, audio_simulado)
                    st.session_state.cadastrados.add(jid)
                    st.success(f"✅ Voz de **{jnome}** cadastrada e salva em /perfis_voz!")
                    st.rerun()
            else:
                col_acao.markdown("—")
    else:
        st.info("Nenhum jogador adicionado ainda.")


# ────────────────────────────────────────────────────────────────────── #
#  4. CANTAR                                                             #
# ────────────────────────────────────────────────────────────────────── #
elif pagina == "🎤 Cantar":
    st.title("🎤 Sessão de Karaokê")

    faixa    = st.session_state.faixa
    jogadores = st.session_state.jogadores

    # Verificações de pré-requisitos
    if not faixa:
        st.warning("⚠️ Selecione uma música primeiro em **Buscar Música**.")
        st.stop()
    if not jogadores:
        st.warning("⚠️ Adicione ao menos 1 jogador em **Cadastrar Jogadores**.")
        st.stop()

    st.markdown(f"**🎵 Música:** {faixa.titulo}")
    st.markdown(f"**👥 Jogadores:** {', '.join(jogadores.values())}")
    st.markdown(f"**Modo:** {'⚔️ Battle' if st.session_state.modo_battle else '🎶 Normal'}")

    if st.button("▶️ Iniciar Sessão", type="primary"):
        pontuacao.iniciar_sessao(jogadores)
        st.session_state.sessao_ativa = True

    if st.session_state.sessao_ativa:
        st.divider()
        st.markdown("### Placar em tempo real")

        # Área de placards dinâmicos
        cols = st.columns(len(jogadores))
        placeholders = {
            jid: cols[i].empty()
            for i, jid in enumerate(jogadores)
        }

        # ── LOOP DE SIMULAÇÃO ──────────────────────────────────────── #
        # Em produção: substitua pelos chunks reais do sounddevice
        # com:  audio_mic = sounddevice.rec(HOP_SAMPLES, ...)
        # e identifique o jogador com:  biometria.identificar(audio_mic)
        for _ in range(6):
            for jid in jogadores:
                ref_audio = np.random.randn(16000).astype(np.float32)
                mic_audio = np.random.randn(16000).astype(np.float32)
                pontuacao.processar_chunk(jid, mic_audio, ref_audio)

            placares = pontuacao.placares_atuais()
            for jid, jnome in jogadores.items():
                p = placares.get(jid, {})
                placeholders[jid].markdown(
                    f"<div class='card'>"
                    f"<div class='card-nome'>{jnome}</div>"
                    f"<div class='card-pontos'>{p.get('pontuacao', 0):.0f}</div>"
                    f"<div class='card-detalhe'>Precisão: {p.get('precisao', 0):.1f}%</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            time.sleep(0.6)

        # Finalizar sessão
        st.session_state.placares = pontuacao.placares_atuais()
        if st.session_state.modo_battle:
            st.session_state.resultado_battle = pontuacao.resultado_battle()

        st.session_state.sessao_ativa = False
        st.success("✅ Sessão concluída! Veja os resultados em **Resultados**.")


# ────────────────────────────────────────────────────────────────────── #
#  5. RESULTADOS                                                         #
# ────────────────────────────────────────────────────────────────────── #
elif pagina == "🏆 Resultados":
    st.title("🏆 Resultados")

    placares = st.session_state.placares
    battle   = st.session_state.resultado_battle

    if not placares:
        st.info("Nenhuma sessão concluída ainda. Vá para **Cantar** para começar!")
        st.stop()

    # Modo Battle — exibir vencedor e ranking
    if battle and st.session_state.modo_battle:
        st.markdown(
            f"<div class='banner-vencedor'>"
            f"🏆 Vencedor: {battle['vencedor']} — {battle['pontuacao_vencedor']} pts"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown("### 📊 Ranking")
        medalhas = ["🥇", "🥈", "🥉"]
        for i, linha in enumerate(battle["ranking"]):
            medal = medalhas[i] if i < 3 else f"{i+1}."
            st.markdown(
                f"{medal} **{linha['nome']}** — "
                f"{linha['pontuacao']} pts | "
                f"Precisão: {linha['precisao']}%"
            )

    # Modo Normal — mostrar cards individuais
    else:
        st.markdown("### Pontuações")
        cols = st.columns(len(placares))
        for i, (jid, p) in enumerate(placares.items()):
            cols[i].markdown(
                f"<div class='card'>"
                f"<div class='card-nome'>{p['nome']}</div>"
                f"<div class='card-pontos'>{p['pontuacao']:.0f}</div>"
                f"<div class='card-detalhe'>Precisão: {p['precisao']:.1f}%</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.divider()
    if st.button("🔄 Nova Sessão"):
        for chave in ("faixa", "placares", "resultado_battle"):
            st.session_state[chave] = None
        st.session_state.sessao_ativa = False
        st.rerun()
