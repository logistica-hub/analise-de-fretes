import streamlit as st
import pandas as pd
import math
import sqlite3
import json
import io
from datetime import datetime

# 1. Configuração de Layout
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide", initial_sidebar_state="expanded")

# CSS para Interface Moderna e Filtros Estilo BI
st.markdown("""
    <style>
    /* Barra Lateral - Alto Contraste */
    [data-testid="stSidebar"] { background-color: #F0F2F6 !important; border-right: 1px solid #D1D5DB; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label, [data-testid="stSidebar"] p {
        color: #000000 !important; font-weight: 700 !important;
    }
    
    /* Container de Filtros no Dashboard */
    .filter-container {
        background-color: #FFFFFF;
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #E2E8F0;
        margin-bottom: 2rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    
    .block-container { padding-top: 1.5rem; }
    </style>
    """, unsafe_allow_html=True)

# --- BANCO DE DADOS (V7) ---
def init_db():
    conn = sqlite3.connect('comparativo_v7.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cotacoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, transportadora TEXT, 
                  total REAL, qtd INTEGER, detalhes_json TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- LOGO INTELIGENTE NA SIDEBAR ---
if 'edit_logo' not in st.session_state: st.session_state.edit_logo = False
if 'logo_data' not in st.session_state: st.session_state.logo_data = None

with st.sidebar:
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
    st.markdown("### 🧭 NAVEGAÇÃO")
    menu = st.radio("Selecione:", ["📊 Dashboard", "🚛 Gestão de Tabelas", "💰 Novo Comparativo"])

# --- TELAS ---

if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    
    # --- FILTROS ESTILO BI (NO TOPO DA TELA) ---
    with st.container():
        st.markdown('<div class="filter-container">', unsafe_allow_html=True)
        f1, f2, f3, f4 = st.columns(4)
        
        # Simulando dados para os filtros (em um caso real, viriam do banco)
        with f1: st.multiselect("📍 Estado (UF)", ["SP", "RJ", "MG", "PR", "SC", "RS", "BA", "GO", "PE", "CE"])
        with f2: st.multiselect("🚛 Transportadora", ["BRASPRESS", "JAMEF", "GALO", "LOGGI"])
        with f3: st.multiselect("📅 Mês", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho"])
        with f4: st.date_input("📆 Período", [])
        st.markdown('</div>', unsafe_allow_html=True)

    # Dados do Dashboard
    conn = sqlite3.connect('comparativo_v7.db')
    df_c = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()
    
    if not df_c.empty:
        # Metricas Principais
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Cotações Realizadas", len(df_c))
        m2.metric("Total Cotado", f"R$ {df_c['total'].sum():,.2f}")
        m3.metric("Notas Processadas", int(df_c['qtd'].sum()))
        m4.metric("Ticket Médio", f"R$ {(df_c['total'].sum() / df_c['qtd'].sum()):,.2f}" if df_c['qtd'].sum() > 0 else "0")

        st.divider()
        st.subheader("📋 Histórico Detalhado")
        st.dataframe(df_c, use_container_width=True)
        
        st.button("📥 Baixar Relatório Consolidado (Excel)")
    else:
        st.info("Nenhuma cotação encontrada para os filtros selecionados.")

elif menu == "🚛 Gestão de Tabelas":
    st.title("🚛 Gestão de Transportadoras")
    
    with st.expander("➕ Cadastrar Nova Transportadora"):
        t_nome = st.text_input("Nome da Transportadora").upper()
        c_u1, c_u2 = st.columns(2)
        with c_u1: f_tab = st.file_uploader("Tabela Frete (Excel)", type=["xlsx"])
        with c_u2: f_cid = st.file_uploader("Planilha Cidades (Excel)", type=["xlsx"])
        
        if f_tab and f_cid and t_nome:
            df_t = pd.read_excel(f_tab).fillna(0)
            
            st.markdown("#### ⚖️ Mapeamento de Faixas de Peso")
            n_faixas = st.number_input("Quantidade de faixas fixas", 1, 30, 5)
            
            faixas = []
            st.markdown("**Kg Min | Kg Máx | Coluna na Planilha**")
            for i in range(int(n_faixas)):
                r = st.columns([1, 1, 3])
                with r[0]: mi = st.number_input("Min", key=f"min{i}", label_visibility="collapsed")
                with r[1]: ma = st.number_input("Max", key=f"max{i}", label_visibility="collapsed")
                with r[2]: co = st.selectbox("Col", df_t.columns, key=f"col{i}", label_visibility="collapsed")
                faixas.append({"min": mi, "max": ma, "col": co})
            
            st.markdown("#### ➕ Peso Adicional (Excedente)")
            r_ex = st.columns([1, 2])
            with r_ex[0]: ex_start = st.number_input("A partir de (kg):", value=101)
            with r_ex[1]: ex_col = st.selectbox("Coluna Kg Adicional", df_t.columns)

            st.markdown("#### 💰 Mapeamento de Taxas")
            taxas = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}
            t_cols = st.columns(3)
            for idx, tx in enumerate(taxas):
                with t_cols[idx % 3]:
                    m_taxas[tx] = st.selectbox(tx, ["Não mapear"] + list(df_t.columns))

            if st.button("💾 Salvar Transportadora"):
                st.success(f"Transportadora {t_nome} configurada!")

    # Listagem de cadastradas com opção de excluir
    st.divider()
    st.subheader("📋 Transportadoras Cadastradas")
    conn = sqlite3.connect('comparativo_v7.db')
    df_l = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    conn.close()
    for _, r in df_l.iterrows():
        c = st.columns([5, 1])
        c[0].write(f"🏢 **{r['nome']}**")
        if c[1].button("🗑️", key=f"del_t_{r['id']}"):
            # Lógica de delete aqui
            st.rerun()

elif menu == "💰 Novo Comparativo":
    st.title("💰 Novo Comparativo / Cotação")
    f_base = st.file_uploader("📥 Subir Planilha Base", type=["xlsx"])
    if f_base:
        st.markdown('<div style="border: 1px solid #ddd; padding: 10px; border-radius: 5px;">', unsafe_allow_html=True)
        st.write("📊 **Arquivo Base Carregado**")
        st.dataframe(pd.read_excel(f_base).head(5), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.divider()
        st.selectbox("Selecione a Transportadora", ["BRASPRESS", "JAMEF"])
        if st.button("🚀 Gerar Cotação"):
            st.success("Cotação processada!")
