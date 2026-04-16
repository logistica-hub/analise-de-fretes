import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math
import unicodedata

# 1. Configuração de Layout
st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")

def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

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
        lista_completa = []
        for _, row in df_h.iterrows():
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            df_det['Transportadora_Origem'] = row['transportadora']
            lista_completa.append(df_det)
        df_bi = pd.concat(lista_completa, ignore_index=True)

        st.subheader("🎯 Filtros")
        f1, f2 = st.columns(2)
        transp_sel = f1.multiselect("Transportadora", options=df_bi['Transportadora_Origem'].unique())
        uf_sel = f2.multiselect("UF", options=df_bi['UF'].unique())

        if transp_sel: df_bi = df_bi[df_bi['Transportadora_Origem'].isin(transp_sel)]
        if uf_sel: df_bi = df_bi[df_bi['UF'].isin(uf_sel)]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_bi['VALOR_SISTEMA'].sum():,.2f}")
        c2.metric("Notas Processadas", f"{len(df_bi)}")
        c3.metric("Peso Total (kg)", f"{df_bi['PESO'].sum():,.2f}")

        st.subheader("📍 Resumo por UF")
        resumo_uf = df_bi.groupby('UF').agg({'VALOR_SISTEMA': 'sum', 'NF': 'count'}).reset_index()
        resumo_uf.columns = ['UF', 'Total em Frete (R$)', 'Qtd Notas']
        st.table(resumo_uf.sort_values(by='Total em Frete (R$)', ascending=False))
    else:
        st.info("Nenhuma cotação salva para exibir.")

# --- MÓDULO 3: COMPARATIVO COM OLHO NOTA A NOTA ---
elif menu == "💰 Comparativo":
    st.title("💰 Novo Cálculo e Histórico")
    
    # ... (Parte de upload e cálculo mantida igual à anterior) ...

    st.divider()
    st.subheader("📜 Histórico (Clique no 👁️ para ver as taxas da nota)")
    conn = sqlite3.connect(DB_NAME)
    cots = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    conn.close()

    for _, c in cots.iterrows():
        with st.expander(f"📅 {c['data_hora']} - {c['transportadora']} | R$ {c['total']:,.2f}"):
            df_det = pd.read_json(io.StringIO(c['detalhes_json']))
            
            # Aqui está o "Olho" nota a nota que você pediu:
            for _, nota in df_det.iterrows():
                with st.expander(f"👁️ NF: {nota['NF']} - {nota['CIDADE']} ({nota['UF']})"):
                    col_a, col_b = st.columns(2)
                    col_a.write(f"**Frete Peso:** R$ {nota.get('F_PESO', 0):,.2f}")
                    col_a.write(f"**Ad Valorem:** R$ {nota.get('AdValorem', 0):,.2f}")
                    col_b.write(f"**Pedágio:** R$ {nota.get('Pedagio', 0):,.2f}")
                    col_b.write(f"**Gris/Taxas:** R$ {nota.get('Gris', 0) + nota.get('Outros', 0):,.2f}")
                    st.subheader(f"Total desta Nota: R$ {nota['VALOR_SISTEMA']:,.2f}")
