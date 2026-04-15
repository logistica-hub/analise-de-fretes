import streamlit as st
import pandas as pd
import math
import sqlite3
import json
import io
from datetime import datetime

# 1. Configuração de Layout (Ocupar a tela toda)
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide", initial_sidebar_state="expanded")

# CSS para remover espaços brancos e estilizar tabelas
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    .stTable { width: 100%; }
    [data-testid="stSidebar"] { background-color: #f0f2f6; }
    .stMetric { background-color: #ffffff; padding: 10px; border-radius: 10px; border: 1px solid #e6e9ef; }
    </style>
    """, unsafe_allow_html=True)

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('comparativo_v4.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cotacoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, transportadora TEXT, 
                  detalhes_json TEXT, total REAL, qtd INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# --- FUNÇÕES ---
def excluir_transp(id_t):
    conn = sqlite3.connect('comparativo_v4.db')
    conn.execute("DELETE FROM transportadoras WHERE id=?", (id_t,))
    conn.commit()
    conn.close()

def excluir_cotacao(id_c):
    conn = sqlite3.connect('comparativo_v4.db')
    conn.execute("DELETE FROM cotacoes WHERE id=?", (id_c,))
    conn.commit()
    conn.close()

# --- SIDEBAR (CONSOLIDADA) ---
with st.sidebar:
    # Espaço para Logo
    logo = st.file_uploader("🖼️ Logo da Empresa", type=["png", "jpg"])
    if logo: st.image(logo, use_container_width=True)
    
    st.markdown("### 🧭 Navegação")
    menu = st.radio("Ir para:", ["📊 Dashboard", "🚛 Gestão de Tabelas", "💰 Novo Comparativo"])
    
    st.divider()
    if menu == "📊 Dashboard":
        st.markdown("### 🔍 Filtros")
        f_estado = st.multiselect("Estado", ["SP", "RJ", "MG", "PR", "SC", "RS", "BA", "GO"])
        f_transp = st.multiselect("Transportadora", []) # Preencher via DB

# --- CONTEÚDO PRINCIPAL ---

# TELA 1: DASHBOARD
if menu == "📊 Dashboard":
    st.title("📊 Painel Comparativo")
    
    # Tabela Dinâmica por Estado
    conn = sqlite3.connect('comparativo_v4.db')
    df_cot = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_cot.empty:
        # Exemplo de Dashboard
        c1, c2, c3 = st.columns(3)
        c1.metric("Cotações Realizadas", len(df_cot))
        c2.metric("Total Cotado", f"R$ {df_cot['total'].sum():,.2f}")
        
        st.write("### 📈 Frete Acumulado por Estado")
        # Aqui você pode cruzar os dados salvos para gerar o Pivot Table
        st.dataframe(df_cot, use_container_width=True)
        st.button("📥 Baixar Relatório Geral")
    else:
        st.info("Aguardando a primeira cotação ser realizada.")

# TELA 2: GESTÃO DE TABELAS (CADASTRO E LISTAGEM)
elif menu == "🚛 Gestão de Tabelas":
    st.title("🚛 Cadastro de Transportadoras")
    
    with st.expander("➕ Adicionar Nova Transportadora", expanded=False):
        t_nome = st.text_input("Nome da Transportadora (Ex: Braspress)")
        u1, u2 = st.columns(2)
        with u1: f_tabela = st.file_uploader("Tabela de Frete (Excel)", type=["xlsx"])
        with u2: f_cidades = st.file_uploader("Lista de Cidades", type=["xlsx"])
        
        if f_tabela and f_cidades:
            df_p = pd.read_excel(f_tabela).fillna(0)
            df_c = pd.read_excel(f_cidades).fillna(0)
            
            st.markdown("#### ⚖️ Mapeamento de Faixas de Peso")
            n_faixas = st.number_input("Quantas faixas de peso fixo?", 1, 20, 5)
            faixas = []
            for i in range(int(n_faixas)):
                r1, r2, r3 = st.columns([1, 1, 2])
                with r1: mi = st.number_input(f"Mín (kg)", key=f"mi{i}")
                with r2: ma = st.number_input(f"Máx (kg)", key=f"ma{i}")
                with r3: co = st.selectbox(f"Coluna na Planilha", df_p.columns, key=f"co{i}")
                faixas.append({"min": mi, "max": ma, "col": co})
            
            st.markdown("#### ➕ Peso Adicional (Excedente)")
            r_exc1, r_exc2 = st.columns(2)
            with r_exc1: exc_start = st.number_input("A partir de (kg):", value=101)
            with r_exc2: exc_col = st.selectbox("Coluna do valor por Kg adicional", df_p.columns)

            st.markdown("#### 💰 Mapeamento de Taxas")
            tx_cols = st.columns(3)
            m_taxas = {}
            lista_tx = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            for idx, tx in enumerate(lista_tx):
                with tx_cols[idx % 3]:
                    m_taxas[tx] = st.selectbox(tx, ["Não mapear"] + list(df_p.columns))

            if st.button("💾 Salvar Transportadora"):
                mapa = {"faixas": faixas, "excedente": {"start": exc_start, "col": exc_col}, "taxas": m_taxas}
                conn = sqlite3.connect('comparativo_v4.db')
                conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                             (t_nome.upper(), df_p.to_json(), df_c.to_json(), json.dumps(mapa)))
                conn.commit()
                conn.close()
                st.success("Salvo!")

    st.markdown("---")
    st.subheader("📋 Tabelas Cadastradas")
    conn = sqlite3.connect('comparativo_v4.db')
    df_t = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    conn.close()
    
    for i, r in df_t.iterrows():
        c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
        c1.write(f"🏢 **{r['nome']}**")
        c2.write("✅ Configurada")
        if c3.button("✏️", key=f"ed{r['id']}"): st.warning("Use o modo adicionar para sobrescrever")
        if c4.button("🗑️", key=f"rm{r['id']}"): 
            excluir_transp(r['id'])
            st.rerun()

# TELA 3: COMPARATIVO (COTAÇÃO)
elif menu == "💰 Novo Comparativo":
    st.title("💰 Cotação e Comparativo")
    
    f_base = st.file_uploader("1. Subir Planilha Base (Notas)", type=["xlsx"])
    
    if f_base:
        st.info("Arquivo Base carregado com sucesso.")
        conn = sqlite3.connect('comparativo_v4.db')
        lista_t = pd.read_sql_query("SELECT nome FROM transportadoras", conn)['nome'].tolist()
        conn.close()
        
        t_alvo = st.selectbox("2. Selecionar Transportadora para Cotar", lista_t)
        
        if st.button("🚀 Gerar Cotação"):
            # Lógica de cálculo seria inserida aqui
            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            conn = sqlite3.connect('comparativo_v4.db')
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd) VALUES (?,?,?,?)", 
                         (now, t_alvo, 1500.00, 10)) # Exemplo
            conn.commit()
            conn.close()
            st.success("Cotação Finalizada!")

    st.divider()
    st.subheader("📜 Histórico de Cotações")
    conn = sqlite3.connect('comparativo_v4.db')
    df_h = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    conn.close()

    for i, r in df_h.iterrows():
        with st.expander(f"📅 {r['data_hora']} | {r['transportadora']} | Total: R$ {r['total']:.2f}"):
            st.write(f"Quantidade de Notas: {r['qtd']}")
            col_b1, col_b2 = st.columns(2)
            col_b1.button("📥 Baixar Excel", key=f"dl{r['id']}")
            if col_b2.button("🗑️ Excluir Cotação", key=f"delc{r['id']}"):
                excluir_cotacao(r['id'])
                st.rerun()
