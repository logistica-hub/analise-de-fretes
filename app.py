import streamlit as st
import pandas as pd
import math
import sqlite3
import json
import io
from datetime import datetime

# 1. Configuração de Layout e Tema Forçado
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide", initial_sidebar_state="expanded")

# CSS Avançado para corrigir o visual da barra lateral e tabelas
st.markdown("""
    <style>
    /* Força cor do texto na barra lateral para Preto (Contraste total) */
    [data-testid="stSidebar"] {
        background-color: #f1f3f6 !important;
        border-right: 1px solid #d1d5db;
    }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label, [data-testid="stSidebar"] p {
        color: #111827 !important;
        font-weight: 600 !important;
    }
    /* Estilização dos inputs na lateral */
    [data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background-color: white !important;
        border: 1px solid #9ca3af !important;
    }
    /* Remove padding excessivo */
    .block-container { padding-top: 1rem; }
    /* Botão de excluir */
    .btn-del { color: #ef4444; cursor: pointer; }
    </style>
    """, unsafe_allow_html=True)

# --- BANCO DE DADOS (V5) ---
def init_db():
    conn = sqlite3.connect('comparativo_v5.db')
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

# --- SIDEBAR FIXA E ESCURA ---
with st.sidebar:
    logo = st.file_uploader("🖼️ Logo da Empresa", type=["png", "jpg"])
    if logo: st.image(logo, use_container_width=True)
    
    st.markdown("### 🧭 MENU PRINCIPAL")
    menu = st.radio("Escolha uma opção:", ["📊 Dashboard", "🚛 Gestão de Tabelas", "💰 Novo Comparativo"])
    
    st.divider()
    if menu == "📊 Dashboard":
        st.markdown("### 🔍 FILTROS")
        st.multiselect("Estado (UF)", ["SP", "RJ", "MG", "PR", "SC", "RS", "BA", "GO", "PE"])
        st.multiselect("Mês", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho"])

# --- NAVEGAÇÃO ---

if menu == "📊 Dashboard":
    st.title("📊 Dashboard Comparativo")
    # Busca dados reais para o Dashboard
    conn = sqlite3.connect('comparativo_v5.db')
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()
    
    if not df_h.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Cotações Totais", len(df_h))
        c2.metric("Volume Financeiro", f"R$ {df_h['total'].sum():,.2f}")
        c3.metric("Notas Processadas", int(df_h['qtd'].sum()))
        
        st.subheader("📁 Histórico de Cotações Realizadas")
        for i, r in df_h.iterrows():
            with st.expander(f"📦 {r['transportadora']} | {r['data_hora']} | R$ {r['total']:.2f}"):
                st.write(f"Notas: {r['qtd']}")
                st.button("🗑️ Excluir esta Cotação", key=f"del_c_{r['id']}")
    else:
        st.info("Nenhuma cotação salva no banco de dados.")

elif menu == "🚛 Gestão de Tabelas":
    st.title("🚛 Gestão de Transportadoras")
    
    with st.expander("➕ Adicionar / Remapear Transportadora"):
        t_nome = st.text_input("Nome da Transportadora").upper()
        u1, u2 = st.columns(2)
        with u1: f_t = st.file_uploader("Subir Tabela Frete", type=["xlsx"])
        with u2: f_c = st.file_uploader("Subir Planilha Cidades", type=["xlsx"])
        
        if f_t and f_c and t_nome:
            df_t = pd.read_excel(f_t).fillna(0)
            df_c = pd.read_excel(f_c).fillna(0)
            
            st.markdown("#### ⚖️ Mapeamento de Faixas de Peso (Lista Compacta)")
            n_f = st.number_input("Qtd de Faixas Fixas", 1, 30, 5)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns([1, 1, 2])
                with r[0]: mi = st.number_input("Kg Min", key=f"mi{i}")
                with r[1]: ma = st.number_input("Kg Máx", key=f"ma{i}")
                with r[2]: co = st.selectbox("Coluna Tabela", df_t.columns, key=f"co{i}")
                faixas.append({"min": mi, "max": ma, "col": co})
            
            st.markdown("#### ➕ Peso Adicional (Excedente)")
            r_ex = st.columns([1, 2])
            with r_ex[0]: ex_start = st.number_input("A partir de (kg):", value=101)
            with r_ex[1]: ex_col = st.selectbox("Coluna do Kg Adicional", df_t.columns)

            st.markdown("#### 💰 Todas as Taxas (Opcionais)")
            m_taxas = {}
            list_taxas = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            t_cols = st.columns(3)
            for idx, tx in enumerate(list_taxas):
                with t_cols[idx % 3]:
                    m_taxas[tx] = st.selectbox(tx, ["Não mapear"] + list(df_t.columns))

            if st.button("💾 SALVAR CONFIGURAÇÃO"):
                mapa = {"faixas": faixas, "excedente": {"start": ex_start, "col": ex_col}, "taxas": m_taxas}
                conn = sqlite3.connect('comparativo_v5.db')
                conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                             (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa)))
                conn.commit()
                conn.close()
                st.success("Configuração Salva!")

    st.markdown("---")
    st.subheader("📋 Transportadoras Ativas")
    conn = sqlite3.connect('comparativo_v5.db')
    df_lista = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    conn.close()
    
    for i, r in df_lista.iterrows():
        c = st.columns([5, 1, 1])
        c[0].write(f"🏢 **{r['nome']}**")
        if c[1].button("✏️", key=f"ed{r['id']}"): st.info("Remapeie acima")
        if c[2].button("🗑️", key=f"rm{r['id']}"):
            conn = sqlite3.connect('comparativo_v5.db')
            conn.execute("DELETE FROM transportadoras WHERE id=?", (r['id'],))
            conn.commit()
            conn.close()
            st.rerun()

elif menu == "💰 Novo Comparativo":
    st.title("💰 Realizar Comparativo")
    f_base = st.file_uploader("📥 Subir Planilha Base (Sempre visível aqui)", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base)
        st.write("### 🗂️ Arquivo Base")
        st.dataframe(df_b.head(3), use_container_width=True) # Janela compacta no topo
        
        conn = sqlite3.connect('comparativo_v5.db')
        lista_t = pd.read_sql_query("SELECT nome FROM transportadoras", conn)['nome'].tolist()
        conn.close()
        
        if lista_t:
            t_sel = st.selectbox("Escolha a Transportadora", lista_t)
            if st.button("🚀 Iniciar Cotação"):
                # Lógica de salvar cotação
                now = datetime.now().strftime("%d/%m/%Y %H:%M")
                conn = sqlite3.connect('comparativo_v5.db')
                conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd) VALUES (?,?,?,?)",
                             (now, t_sel, 0.00, len(df_b)))
                conn.commit()
                conn.close()
                st.success(f"Cotação para {t_sel} realizada com sucesso!")
        else:
            st.warning("Cadastre uma transportadora antes de cotar.")
