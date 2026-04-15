import streamlit as st
import pandas as pd
import math
import sqlite3
import json
import io
from datetime import datetime

# 1. Configuração de Layout
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide", initial_sidebar_state="expanded")

# CSS para Interface Moderna e Barra Lateral de Alto Contraste
st.markdown("""
    <style>
    /* Estilização da Barra Lateral */
    [data-testid="stSidebar"] {
        background-color: #F0F2F6 !important;
        border-right: 1px solid #D1D5DB;
    }
    /* Forçar cor do texto na lateral (Preto) */
    [data-testid="stSidebar"] .stMarkdown, 
    [data-testid="stSidebar"] label, 
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] .stRadio > label {
        color: #000000 !important;
        font-weight: 700 !important;
        font-size: 15px !important;
    }
    /* Estilo dos Selectboxes na lateral */
    [data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        border: 1px solid #000000 !important;
        color: #000000 !important;
    }
    /* Ajustes de espaçamento central */
    .block-container { padding-top: 1rem; }
    
    /* Botão de edição do logo */
    .edit-logo-btn {
        text-align: right;
        margin-top: -10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- BANCO DE DADOS (V6) ---
def init_db():
    conn = sqlite3.connect('comparativo_v6.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cotacoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, transportadora TEXT, 
                  total REAL, qtd INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# --- ESTADO DO LOGO (Sessão) ---
if 'edit_logo' not in st.session_state:
    st.session_state.edit_logo = False

# --- SIDEBAR FIXA ---
with st.sidebar:
    # Lógica do Logo com "Canetinha"
    if 'logo_data' not in st.session_state:
        st.session_state.logo_data = None

    if st.session_state.logo_data is None or st.session_state.edit_logo:
        uploaded_logo = st.file_uploader("🖼️ Logo da Empresa", type=["png", "jpg", "jpeg"])
        if uploaded_logo:
            st.session_state.logo_data = uploaded_logo.read()
            st.session_state.edit_logo = False
            st.rerun()
    else:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Editar Logo"):
            st.session_state.edit_logo = True
            st.rerun()
    
    st.divider()
    st.markdown("### 🧭 MENU")
    menu = st.radio("Selecione a tela:", ["📊 Dashboard", "🚛 Gestão de Tabelas", "💰 Novo Comparativo"])
    
    if menu == "📊 Dashboard":
        st.divider()
        st.markdown("### 🔍 FILTROS")
        st.multiselect("Estado", ["SP", "RJ", "MG", "BA", "PR", "SC", "RS"])
        st.multiselect("Mês", ["Janeiro", "Fevereiro", "Março"])

# --- CONTEÚDO ---

if menu == "📊 Dashboard":
    st.title("📊 Painel de Comparativos")
    # Dashboard resumido
    conn = sqlite3.connect('comparativo_v6.db')
    df_c = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()
    
    if not df_c.empty:
        col1, col2 = st.columns(2)
        col1.metric("Cotações Realizadas", len(df_c))
        col2.metric("Total em Fretes", f"R$ {df_c['total'].sum():,.2f}")
        st.dataframe(df_c, use_container_width=True)
    else:
        st.info("Aguardando cotações para exibir dados.")

elif menu == "🚛 Gestão de Tabelas":
    st.title("🚛 Gestão de Transportadoras")
    
    with st.expander("➕ Nova Transportadora"):
        t_nome = st.text_input("Nome da Transportadora")
        col_u1, col_u2 = st.columns(2)
        with col_u1: f_tab = st.file_uploader("Subir Tabela", type=["xlsx"])
        with col_u2: f_cid = st.file_uploader("Subir Cidades", type=["xlsx"])
        
        if f_tab and f_cid and t_nome:
            df_t = pd.read_excel(f_tab).fillna(0)
            st.markdown("#### ⚖️ Mapeamento de Faixas de Peso")
            n_f = st.number_input("Quantidade de faixas", 1, 20, 5)
            
            # Cabeçalho da Lista de Mapeamento
            st.markdown("**Mapping | Kg Min | Kg Máx | Coluna Planilha**")
            faixas_list = []
            for i in range(int(n_f)):
                r = st.columns([1, 1, 1, 3])
                r[0].write(f"Faixa {i+1}")
                with r[1]: mi = st.number_input("Min", key=f"min{i}", label_visibility="collapsed")
                with r[2]: ma = st.number_input("Max", key=f"max{i}", label_visibility="collapsed")
                with r[3]: co = st.selectbox("Col", df_t.columns, key=f"col{i}", label_visibility="collapsed")
                faixas_list.append({"min": mi, "max": ma, "col": co})
            
            st.markdown("#### ➕ Peso Adicional (Excedente)")
            r_ex = st.columns([2, 3])
            with r_ex[0]: ex_start = st.number_input("A partir de (kg):", value=101)
            with r_ex[1]: ex_col = st.selectbox("Coluna Kg Adicional", df_t.columns)

            st.markdown("#### 💰 Mapping de Taxas")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}
            t_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                with t_cols[idx % 3]:
                    m_taxas[tx] = st.selectbox(tx, ["Não mapear"] + list(df_t.columns))

            if st.button("💾 Salvar Transportadora"):
                st.success(f"{t_nome} salva com sucesso!")

elif menu == "💰 Novo Comparativo":
    st.title("💰 Comparativo / Cotação")
    f_base = st.file_uploader("📥 Planilha Base", type=["xlsx"])
    
    if f_base:
        st.markdown("### 📑 Visualização da Base")
        st.dataframe(pd.read_excel(f_base).head(5), height=200, use_container_width=True)
        
        st.divider()
        # Aqui apareceria a lista de transportadoras salvas para selecionar e cotar
        st.selectbox("Selecione a Transportadora para comparar", ["Braspress", "Jamef", "Galo"])
        if st.button("🚀 Iniciar Processamento"):
            st.info("Calculando...")
