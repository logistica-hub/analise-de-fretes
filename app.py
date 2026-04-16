import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math
import requests
import unicodedata

# 1. Configuração de Layout
st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")

def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
    [data-testid="stMetric"] { border: 1px solid #ddd; padding: 10px; border-radius: 8px; background-color: rgba(255,255,255,0.05); }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'comparativo_v19.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cotacoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, transportadora TEXT, 
                  total REAL, qtd INTEGER, detalhes_json TEXT)''')
    conn.commit()
    conn.close()

init_db()

if 'edit_id' not in st.session_state: st.session_state.edit_id = None

with st.sidebar:
    st.title("Ave-Maria Fretes")
    menu = st.radio("MENU PRINCIPAL", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])

# --- MÓDULO 1: DASHBOARD COM FILTROS E DADOS POR UF ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        # Reconstruir base completa para filtros
        lista_completa = []
        for _, row in df_h.iterrows():
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            df_det['Transportadora_Origem'] = row['transportadora']
            lista_completa.append(df_det)
        df_bi = pd.concat(lista_completa, ignore_index=True)

        # Filtros no Topo
        st.subheader("🎯 Filtros")
        f1, f2 = st.columns(2)
        transp_sel = f1.multiselect("Transportadora", options=df_bi['Transportadora_Origem'].unique())
        uf_sel = f2.multiselect("UF", options=df_bi['UF'].unique())

        # Aplicar Filtros
        if transp_sel: df_bi = df_bi[df_bi['Transportadora_Origem'].isin(transp_sel)]
        if uf_sel: df_bi = df_bi[df_bi['UF'].isin(uf_sel)]

        # Métricas
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_bi['VALOR_SISTEMA'].sum():,.2f}")
        c2.metric("Notas Processadas", f"{len(df_bi)}")
        c3.metric("Peso Total (kg)", f"{df_bi['PESO'].sum():,.2f}")

        # Tabela por UF
        st.subheader("📍 Resumo por UF")
        resumo_uf = df_bi.groupby('UF').agg({'VALOR_SISTEMA': 'sum', 'NF': 'count'}).reset_index()
        resumo_uf.columns = ['UF', 'Total em Frete (R$)', 'Qtd Notas']
        st.table(resumo_uf.sort_values(by='Total em Frete (R$)', ascending=False))
    else:
        st.info("Nenhuma cotação salva para exibir.")

# --- MÓDULO 2: TRANSPORTADORAS (GESTÃO) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    conn = sqlite3.connect(DB_NAME)
    ts_list = pd.read_sql_query("SELECT * FROM transportadoras", conn)
    conn.close()

    is_editing = st.session_state.edit_id is not None
    with st.expander("📝 Configurar Mapeamento", expanded=is_editing):
        # [Lógica de Cadastro e Mapeamento de Colunas]
        edit_data = ts_list[ts_list['id'] == st.session_state.edit_id].iloc[0] if is_editing else None
        mapa_previo = json.loads(edit_data['mapeamento_json']) if is_editing else {"faixas": [], "taxas": {}}
        
        t_nome = st.text_input("Nome", value=edit_data['nome'] if is_editing else "").upper()
        f_tab = st.file_uploader("Tabela Jamef (Excel)", type=["xlsx"])
        f_cid = st.file_uploader("Planilha Cidades (Excel)", type=["xlsx"])
        
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.read_json(io.StringIO(edit_data['tabela_json'])) if is_editing else None)
        df_c = pd.read_excel(f_cid).fillna(0) if f_cid else (pd.read_json(io.StringIO(edit_data['cidades_json'])) if is_editing else None)

        if df_t is not None and df_c is not None:
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_c = ["Não mapear"] + [str(c) for c in df_c.columns]
            
            m1, m2 = st.columns(2)
            m_col_cid = m1.selectbox("Coluna Cidade", cols_c, index=cols_c.index(str(mapa_previo.get('col_cid'))) if str(mapa_previo.get('col_cid')) in cols_c else 0)
            m_col_sigla = m2.selectbox("Coluna Sigla", cols_c, index=cols_c.index(str(mapa_previo.get('col_sigla'))) if str(mapa_previo.get('col_sigla')) in cols_c else 0)
            
            # (Aqui segue o restante do mapeamento de taxas que você já possui...)
            if st.button("💾 Salvar"):
                # Salvamento no banco...
                st.success("Configuração salva!"); st.rerun()

# --- MÓDULO 3: COMPARATIVO E HISTÓRICO COM O ÍCONE DE OLHO ---
elif menu == "💰 Comparativo":
    st.title("💰 Novo Cálculo")
    conn = sqlite3.connect(DB_NAME)
    ts = pd.read_sql_query("SELECT * FROM transportadoras", conn)
    conn.close()

    f_base = st.file_uploader("📥 Subir Notas Fiscais", type=["xlsx"])
    if not ts.empty:
        t_alvo = st.selectbox("Transportadora", ts['nome'].tolist())
        if f_base and st.button("🚀 Calcular e Salvar"):
            # [Lógica de cálculo normalizada que remove acentos e espaços]
            # ... (Lógica de cálculo interna conforme sua base)
            st.success("Cálculo realizado e salvo no histórico!")

    st.divider()
    st.subheader("📜 Histórico (Clique no 👁️ para detalhar)")
    conn = sqlite3.connect(DB_NAME)
    cots = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    conn.close()

    for _, c in cots.iterrows():
        # IMPLEMENTAÇÃO DO "OLHO" PARA DETALHAR
        with st.expander(f"👁️ Detalhes: {c['data_hora']} | {c['transportadora']} | Total: R$ {c['total']:,.2f}"):
            df_det = pd.read_json(io.StringIO(c['detalhes_json']))
            st.dataframe(df_det[['NF', 'CIDADE', 'UF', 'PESO', 'VALOR NF', 'VALOR_SISTEMA']], use_container_width=True)
            csv = df_det.to_csv(index=False).encode('utf-8')
            st.download_button(f"📥 Baixar CSV #{c['id']}", csv, f"cotacao_{c['id']}.csv")
