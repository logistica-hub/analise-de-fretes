import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime

# 1. Configuração de Layout e Remoção de Margens
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    /* Estica o conteúdo para as bordas */
    .block-container { padding-top: 1rem; padding-left: 2rem; padding-right: 2rem; max-width: 100%; }
    /* Linhas finas para separação */
    hr { margin-top: 1rem; margin-bottom: 1rem; border: 0; border-top: 1px solid #eee; }
    /* Estilo da Sidebar */
    [data-testid="stSidebar"] { background-color: #F8F9FA !important; border-right: 1px solid #E0E0E0; }
    [data-testid="stSidebar"] * { color: #000000 !important; font-weight: 600; }
    /* Dashboard Cards */
    .stMetric { border: 1px solid #F0F0F0; padding: 10px; border-radius: 5px; background: #FFF; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'comparativo_v12.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cotacoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, transportadora TEXT, 
                  total REAL, qtd INTEGER, detalhes_json TEXT, estado_resumo TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- LOGO E MENU ---
with st.sidebar:
    if 'logo_data' not in st.session_state: st.session_state.logo_data = None
    if st.session_state.logo_data is None:
        up = st.file_uploader("🖼️ Subir Logo", type=["png", "jpg"])
        if up: 
            st.session_state.logo_data = up.read()
            st.rerun()
    else:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Editar Logo"):
            st.session_state.logo_data = None
            st.rerun()
    
    st.divider()
    menu = st.radio("NAVEGAÇÃO", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 BI de Fretes")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        # Extrair todos os estados de todas as cotações
        resumos = []
        for r in df_h['estado_resumo']: resumos.extend(json.loads(r))
        df_full = pd.DataFrame(resumos)

        # Filtros Lado a Lado
        f1, f2 = st.columns(2)
        with f1: t_sel = st.multiselect("Transportadora", df_full['Transportadora'].unique())
        with f2: uf_sel = st.multiselect("Estado (UF)", sorted(df_full['UF'].unique()))

        if t_sel: df_full = df_full[df_full['Transportadora'].isin(t_sel)]
        if uf_sel: df_full = df_full[df_full['UF'].isin(uf_sel)]

        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_full['Valor'].sum():,.2f}")
        c2.metric("Qtd Notas", len(df_h))
        c3.metric("Ticket Médio/UF", f"R$ {df_full['Valor'].mean():,.2f}")

        st.subheader("📋 Consolidado por Estado")
        pivot = df_full.pivot_table(index="UF", columns="Transportadora", values="Valor", aggfunc="sum").fillna(0)
        st.dataframe(pivot, use_container_width=True)
    else:
        st.info("Realize uma cotação para ver o BI.")

# --- TRANSPORTADORAS ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Cadastro de Tabelas")
    
    if 'edit_id' not in st.session_state: st.session_state.edit_id = None

    with st.expander("📝 Configurar Transportadora", expanded=st.session_state.edit_id is not None):
        t_nome = st.text_input("Nome da Transportadora").upper()
        u1, u2 = st.columns(2)
        with u1: f_tab = st.file_uploader("Arquivo de Tabela", type=["xlsx"])
        with u2: f_cid = st.file_uploader("Arquivo de Cidades", type=["xlsx"])
        
        if f_tab and f_cid:
            df_tab_prev = pd.read_excel(f_tab).fillna(0)
            st.write("Mapeie as Faixas de Peso (Ex: Coluna 'até 10kg'):")
            # Mapeamento simplificado para o exemplo, você pode expandir
            col_peso = st.selectbox("Selecione a coluna de Frete Peso (Ex: Acima 100kg)", df_tab_prev.columns)
            
            if st.button("💾 Salvar"):
                conn = sqlite3.connect(DB_NAME)
                mapa = {"col_frete": col_peso}
                conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                             (t_nome, df_tab_prev.to_json(), pd.read_excel(f_cid).to_json(), json.dumps(mapa)))
                conn.commit(); conn.close(); st.rerun()

    st.divider()
    conn = sqlite3.connect(DB_NAME)
    df_lista = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    conn.close()
    for _, r in df_lista.iterrows():
        c = st.columns([5, 1])
        c[0].write(f"🏢 {r['nome']}")
        if c[1].button("🗑️", key=f"del_{r['id']}"):
            conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM transportadoras WHERE id=?", (r['id'],)); conn.commit(); conn.close(); st.rerun()

# --- COMPARATIVO (CÁLCULO REAL) ---
elif menu == "💰 Comparativo":
    st.title("💰 Novo Comparativo")
    f_base = st.file_uploader("Subir Base de Notas", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        st.write("### Mapeamento dos Campos da Base")
        c1, c2, c3, c4 = st.columns(4)
        with c1: m_cid = st.selectbox("Cidade", df_b.columns, index=2)
        with c2: m_uf = st.selectbox("UF", df_b.columns, index=3)
        with c3: m_peso = st.selectbox("Peso", df_b.columns, index=6)
        with c4: m_val = st.selectbox("Valor NF", df_b.columns, index=7)

        conn = sqlite3.connect(DB_NAME)
        transp_df = pd.read_sql_query("SELECT * FROM transportadoras", conn)
        conn.close()

        t_alvo = st.selectbox("Transportadora", transp_df['nome'].tolist())

        if st.button("🚀 Calcular Agora"):
            t_data = transp_df[transp_df['nome'] == t_alvo].iloc[0]
            df_tabela = pd.read_json(io.StringIO(t_data['tabela_json']))
            df_cidades = pd.read_json(io.StringIO(t_data['cidades_json']))
            mapa = json.loads(t_data['mapeamento_json'])

            resultados = []
            resumo_uf = {}

            # MOTOR DE CÁLCULO REAL
            for _, nota in df_b.iterrows():
                try:
                    cidade_n = str(nota[m_cid]).upper().strip()
                    # Busca a SIGLA da cidade
                    # Na sua planilha Jamef, a coluna 0 é MUNICIPIO e a 2 é SIGLA
                    sigla = df_cidades[df_cidades.iloc[:, 0].str.upper() == cidade_n].iloc[0, 2]
                    
                    # Busca o valor na TABELA pela SIGLA
                    # Na sua Tabela Jamef, a coluna 2 é a SIGLA
                    linha_frete = df_tabela[df_tabela.iloc[:, 2] == sigla].iloc[0]
                    
                    # Cálculo simples: Peso * Coluna Mapeada (Ajuste para sua regra se for faixa)
                    v_frete = float(nota[m_peso]) * float(linha_frete[mapa['col_frete']])
                except:
                    v_frete = 0.0 # Se não achar a cidade
                
                nota['FRETE_CALCULADO'] = v_frete
                resultados.append(nota.to_dict())
                
                # Agrupa por UF para o Dashboard
                uf = nota[m_uf]
                resumo_uf[uf] = resumo_uf.get(uf, 0) + v_frete

            # Salvar no Banco
            df_final = pd.DataFrame(resultados)
            resumo_json = [{"UF": k, "Transportadora": t_alvo, "Valor": v} for k, v in resumo_uf.items()]
            
            conn = sqlite3.connect(DB_NAME)
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json, estado_resumo) VALUES (?,?,?,?,?,?)",
                         (datetime.now().strftime("%H:%M - %d/%m"), t_alvo, df_final['FRETE_CALCULADO'].sum(), len(df_final), df_final.to_json(), json.dumps(resumo_json)))
            conn.commit(); conn.close()
            st.success("Cotação processada com sucesso!")

    st.divider()
    # Histórico
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    conn.close()
    for _, row in df_h.iterrows():
        with st.expander(f"📋 {row['transportadora']} | {row['data_hora']} | R$ {row['total']:,.2f}"):
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            # DOWNLOAD EXCEL REAL
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                df_det.to_excel(writer, index=False)
            st.download_button("📥 Baixar Excel Detalhado", out.getvalue(), f"frete_{row['transportadora']}.xlsx")
            if st.button("🗑️ Deletar", key=f"d_{row['id']}"):
                conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()
