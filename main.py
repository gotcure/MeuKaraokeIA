"""
main.py — Smart Karaoke IA
Execute com: streamlit run main.py
"""

import io
import time
import logging
import numpy as np
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from engine_audio import buscar_musica, preparar_musica, Faixa
from biometria   import Biometria
from pontuacao   import Pontuacao

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")

# ══════════════════════════════════════════════════════════════════════ #
#  CONFIG                                                                #
# ══════════════════════════════════════════════════════════════════════ #
st.set_page_config(page_title="🎤 Meu Karaokê IA", page_icon="🎤",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.card { background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:14px;
        padding:1.5rem;color:white;text-align:center;margin-bottom:.5rem; }
.card-pts  { font-size:3rem;font-weight:800;color:#a78bfa; }
.card-nome { font-size:1.1rem;margin-bottom:.3rem; }
.card-det  { font-size:.85rem;color:#94a3b8; }
.banner    { background:linear-gradient(135deg,#f59e0b,#ef4444);border-radius:14px;
             padding:1.2rem 2rem;text-align:center;font-size:1.6rem;
             font-weight:800;color:white;margin-bottom:1rem; }
.lyric-box { background:#1e1e3a;border-radius:12px;padding:1.5rem;
             text-align:center;margin:1rem 0; }
.lyric-cur { font-size:1.8rem;font-weight:700;color:#a78bfa; }
.lyric-nxt { font-size:1.1rem;color:#64748b;margin-top:.5rem; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════ #
#  RECURSOS EM CACHE                                                     #
# ══════════════════════════════════════════════════════════════════════ #

@st.cache_resource
def carregar_biometria():
    return Biometria()

@st.cache_resource
def carregar_pontuacao():
    return Pontuacao()


# ══════════════════════════════════════════════════════════════════════ #
#  ESTADO DA SESSÃO                                                      #
# ══════════════════════════════════════════════════════════════════════ #

def _init():
    defaults = {
        "pagina":           "🏠 Início",
        "faixa":            None,
        "jogadores":        {},
        "cadastrados":      set(),
        "modo_battle":      False,
        "sessao_ativa":     False,
        "tempo_inicio":     None,
        "placares":         {},
        "resultado_battle": None,
        "resultados_busca": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()

biometria = carregar_biometria()
pontuacao = carregar_pontuacao()

PAGINAS = ["🏠 Início", "🔍 Buscar Música",
           "🎙️ Cadastrar Jogadores", "🎤 Cantar", "🏆 Resultados"]


# ══════════════════════════════════════════════════════════════════════ #
#  SIDEBAR                                                               #
# ══════════════════════════════════════════════════════════════════════ #
with st.sidebar:
    st.title("🎤 Meu Karaokê IA")
    st.divider()
    pagina = st.radio("Menu", PAGINAS, label_visibility="collapsed")
    st.session_state.pagina = pagina
    st.divider()
    st.session_state.modo_battle = st.toggle(
        "⚔️ Modo Battle", value=st.session_state.modo_battle)
    if st.session_state.modo_battle:
        st.success("Competição ativada!")
    st.divider()
    st.caption("Status")
    st.write("🎵", "Pronta" if st.session_state.faixa else "—")
    st.write("👥", len(st.session_state.jogadores), "jogador(es)")
    st.write("✅", len(st.session_state.cadastrados), "cadastrado(s)")


# ══════════════════════════════════════════════════════════════════════ #
#  1. INÍCIO                                                             #
# ══════════════════════════════════════════════════════════════════════ #
if pagina == "🏠 Início":
    st.title("🎤 Meu Karaokê IA")
    st.markdown("""
    Bem-vindo ao sistema de Karaokê com Inteligência Artificial!

    | Passo | Ação |
    |---|---|
    | 1️⃣ | **Buscar Música** — pesquise no YouTube |
    | 2️⃣ | **Cadastrar Jogadores** — registre a voz de cada um |
    | 3️⃣ | **Cantar** — toque o instrumental, veja a letra e cante! |
    | 4️⃣ | **Resultados** — veja o placar e o vencedor do Battle |
    """)
    c1, c2, c3 = st.columns(3)
    c1.metric("Jogadores", len(st.session_state.jogadores))
    c2.metric("Cadastrados", len(st.session_state.cadastrados))
    c3.metric("Música pronta", "✅" if st.session_state.faixa else "Não")


# ══════════════════════════════════════════════════════════════════════ #
#  2. BUSCAR MÚSICA                                                      #
# ══════════════════════════════════════════════════════════════════════ #
elif pagina == "🔍 Buscar Música":
    st.title("🔍 Buscar Música")

    query = st.text_input("Nome da música ou artista:",
                          placeholder="ex: Legião Urbana Tempo Perdido")

    if st.button("🔎 Buscar", type="primary") and query:
        with st.spinner("Buscando no YouTube…"):
            st.session_state.resultados_busca = buscar_musica(query, max_resultados=6)

    resultados = st.session_state.get("resultados_busca", [])
    if resultados:
        st.markdown("### Resultados")
        for r in resultados:
            with st.container(border=True):
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"**{r['titulo']}**  \n⏱️ {r['duracao']}")
                if c2.button("Selecionar", key=r["url"]):
                    with st.spinner("⬇️ Baixando, separando áudio e buscando letra… (pode levar alguns minutos)"):
                        faixa = preparar_musica(r["url"])
                    st.session_state.faixa = faixa
                    st.session_state.resultados_busca = []
                    letra_info = f"{len(faixa.letra)} linhas encontradas" if faixa.letra else "não encontrada"
                    st.success(f"✅ **{faixa.titulo}** pronta! Letra: {letra_info}")
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════ #
#  3. CADASTRAR JOGADORES                                                #
# ══════════════════════════════════════════════════════════════════════ #
elif pagina == "🎙️ Cadastrar Jogadores":
    st.title("🎙️ Cadastrar Jogadores")

    with st.form("form_jogador", clear_on_submit=True):
        c1, c2  = st.columns(2)
        novo_id = c1.text_input("ID único", placeholder="ex: j1")
        novo_nm = c2.text_input("Nome",     placeholder="ex: Ana")
        adicionar = st.form_submit_button("➕ Adicionar")

    if adicionar:
        if not novo_id or not novo_nm:
            st.error("Preencha ID e nome.")
        elif novo_id in st.session_state.jogadores:
            st.warning(f"ID '{novo_id}' já existe.")
        else:
            biometria.registrar(novo_id, novo_nm)
            st.session_state.jogadores[novo_id] = novo_nm
            st.success(f"Jogador **{novo_nm}** adicionado!")

    if st.session_state.jogadores:
        st.divider()
        st.markdown("### Jogadores")
        for jid, jnome in st.session_state.jogadores.items():
            cadastrado = jid in st.session_state.cadastrados
            c1, c2, c3 = st.columns([3, 2, 2])
            c1.markdown(f"**{jnome}** `{jid}`")
            c2.markdown("✅ Cadastrado" if cadastrado else "⏳ Pendente")
            if not cadastrado:
                if c3.button("🎙️ Cadastrar voz", key=f"enroll_{jid}"):
                    audio_sim = np.random.randn(16000 * 5).astype(np.float32)
                    biometria.cadastrar(jid, audio_sim)
                    st.session_state.cadastrados.add(jid)
                    st.success(f"✅ Voz de **{jnome}** cadastrada!")
                    st.rerun()
    else:
        st.info("Nenhum jogador adicionado ainda.")


# ══════════════════════════════════════════════════════════════════════ #
#  4. CANTAR                                                             #
# ══════════════════════════════════════════════════════════════════════ #
elif pagina == "🎤 Cantar":
    st.title("🎤 Sessão de Karaokê")

    faixa    = st.session_state.faixa
    jogadores = st.session_state.jogadores

    if not faixa:
        st.warning("⚠️ Selecione uma música em **Buscar Música**.")
        st.stop()
    if not jogadores:
        st.warning("⚠️ Adicione ao menos 1 jogador em **Cadastrar Jogadores**.")
        st.stop()

    st.markdown(f"**🎵** {faixa.titulo}")
    st.markdown(f"**👥** {', '.join(jogadores.values())} · "
                f"**Modo:** {'⚔️ Battle' if st.session_state.modo_battle else '🎶 Normal'}")

    # ── Player do Instrumental ─────────────────────────────────────────
    st.divider()
    st.markdown("### 🔊 Instrumental")

    if faixa.caminho_instrumental and faixa.caminho_instrumental.exists():
        audio_bytes = faixa.caminho_instrumental.read_bytes()
        st.audio(audio_bytes, format="audio/wav")
        st.caption("▶️ Clique em play e depois em **Iniciar Sincronização** para alinhar a letra.")
    else:
        st.warning("Instrumental ainda não separado. Volte em Buscar Música e selecione a música novamente.")
        st.stop()

    # ── Controle de sincronização ──────────────────────────────────────
    col_ini, col_par = st.columns(2)

    if col_ini.button("▶️ Iniciar Sincronização", type="primary",
                      disabled=st.session_state.sessao_ativa):
        pontuacao.iniciar_sessao(jogadores)
        st.session_state.tempo_inicio  = time.time()
        st.session_state.sessao_ativa  = True
        st.session_state.placares      = {}
        st.rerun()

    if col_par.button("⏹ Encerrar Sessão",
                      disabled=not st.session_state.sessao_ativa):
        st.session_state.sessao_ativa  = False
        st.session_state.tempo_inicio  = None
        st.session_state.placares      = pontuacao.placares_atuais()
        if st.session_state.modo_battle:
            st.session_state.resultado_battle = pontuacao.resultado_battle()
        st.rerun()

    # ── Letra sincronizada ─────────────────────────────────────────────
    if st.session_state.sessao_ativa and st.session_state.tempo_inicio:

        # Auto-refresh a cada 1 segundo para atualizar a letra
        st_autorefresh(interval=1000, key="sync_letra")

        elapsed = time.time() - st.session_state.tempo_inicio
        letra   = faixa.letra

        st.divider()
        st.markdown("### 📝 Letra")

        if not letra:
            st.info("Letra não encontrada para essa música. Cante à vontade! 🎵")
        else:
            # Encontra a linha atual e a próxima
            linha_atual = ""
            linha_prox  = ""

            for i, entry in enumerate(letra):
                if entry["tempo"] <= elapsed:
                    linha_atual = entry["linha"]
                    if i + 1 < len(letra):
                        linha_prox = letra[i + 1]["linha"]
                    else:
                        linha_prox = ""

            st.markdown(
                f"<div class='lyric-box'>"
                f"<div class='lyric-cur'>{linha_atual or '♪ ♪ ♪'}</div>"
                f"<div class='lyric-nxt'>{linha_prox}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Barra de progresso da música
            if faixa.duracao_segundos > 0:
                prog = min(elapsed / faixa.duracao_segundos, 1.0)
                st.progress(prog, text=f"⏱️ {int(elapsed//60)}:{int(elapsed%60):02d} / "
                            f"{int(faixa.duracao_segundos//60)}:{int(faixa.duracao_segundos%60):02d}")

        # ── Microfone + Pontuação ──────────────────────────────────────
        st.divider()
        st.markdown("### 🎤 Cante aqui")

        if len(jogadores) > 1:
            jogador_ativo = st.selectbox(
                "Quem está cantando agora?",
                options=list(jogadores.keys()),
                format_func=lambda x: jogadores[x],
            )
        else:
            jogador_ativo = list(jogadores.keys())[0]

        audio_gravado = st.audio_input("🎙️ Grave sua voz (clique para gravar)")

        if audio_gravado is not None:
            with st.spinner("Analisando pitch e calculando pontuação…"):
                import soundfile as sf
                audio_np, sr = sf.read(io.BytesIO(audio_gravado.read()))

                # Converte para mono se necessário
                if audio_np.ndim > 1:
                    audio_np = audio_np.mean(axis=1)
                audio_np = audio_np.astype(np.float32)

                # Carrega trecho correspondente do vocal de referência
                ref_np = np.zeros_like(audio_np)
                if faixa.caminho_vocal and faixa.caminho_vocal.exists():
                    ref_full, sr_ref = sf.read(str(faixa.caminho_vocal))
                    if ref_full.ndim > 1:
                        ref_full = ref_full.mean(axis=1)
                    inicio = int(elapsed * sr_ref)
                    fim    = inicio + len(audio_np)
                    if fim <= len(ref_full):
                        ref_np = ref_full[inicio:fim].astype(np.float32)

                frames  = pontuacao.processar_chunk(jogador_ativo, audio_np, ref_np)
                placares = pontuacao.placares_atuais()
                st.session_state.placares = placares

            p = placares.get(jogador_ativo, {})
            st.success(
                f"✅ **{jogadores[jogador_ativo]}** — "
                f"Pontuação: **{p.get('pontuacao', 0):.0f} pts** | "
                f"Precisão: **{p.get('precisao', 0):.1f}%**"
            )

        # ── Placar ao vivo ─────────────────────────────────────────────
        placares = st.session_state.placares
        if placares:
            st.divider()
            st.markdown("### 📊 Placar")
            cols = st.columns(len(jogadores))
            for i, (jid, jnome) in enumerate(jogadores.items()):
                p = placares.get(jid, {})
                cols[i].markdown(
                    f"<div class='card'>"
                    f"<div class='card-nome'>{jnome}</div>"
                    f"<div class='card-pts'>{p.get('pontuacao', 0):.0f}</div>"
                    f"<div class='card-det'>Precisão: {p.get('precisao', 0):.1f}%</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════ #
#  5. RESULTADOS                                                         #
# ══════════════════════════════════════════════════════════════════════ #
elif pagina == "🏆 Resultados":
    st.title("🏆 Resultados")

    placares = st.session_state.placares
    battle   = st.session_state.resultado_battle

    if not placares:
        st.info("Nenhuma sessão concluída ainda. Vá para **Cantar** para começar!")
        st.stop()

    if battle and st.session_state.modo_battle:
        st.markdown(
            f"<div class='banner'>🏆 Vencedor: {battle['vencedor']} — "
            f"{battle['pontuacao_vencedor']} pts</div>",
            unsafe_allow_html=True,
        )
        st.markdown("### Ranking")
        medalhas = ["🥇", "🥈", "🥉"]
        for i, linha in enumerate(battle["ranking"]):
            m = medalhas[i] if i < 3 else f"{i+1}."
            st.markdown(
                f"{m} **{linha['nome']}** — "
                f"{linha['pontuacao']} pts | Precisão: {linha['precisao']}%"
            )
    else:
        cols = st.columns(len(placares))
        for i, (jid, p) in enumerate(placares.items()):
            cols[i].markdown(
                f"<div class='card'>"
                f"<div class='card-nome'>{p['nome']}</div>"
                f"<div class='card-pts'>{p['pontuacao']:.0f}</div>"
                f"<div class='card-det'>Precisão: {p['precisao']:.1f}%</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.divider()
    if st.button("🔄 Nova Sessão"):
        for k in ("faixa", "placares", "resultado_battle", "tempo_inicio"):
            st.session_state[k] = None
        st.session_state.sessao_ativa = False
        st.rerun()
