import streamlit as st
import pandas as pd
import sqlite3
import json
import io
import os
from datetime import datetime
import math
import requests
import unicodedata

# 1. Configuração de Layout
st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")

SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw2stGRESs-l0dJQEd3bKAawtUb8_zRH1i3VIb4DALNSjdjZnked9Lxs97ProouwR0/exec"

def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def formata_br(valor):
    try:
        if pd.isna(valor): return "0,00"
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"

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

# --- SIDEBAR ---
with st.sidebar:
    if 'logo_data' not in st.session_state: st.session_state.logo_data = None
    if st.session_state.logo_data:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Editar Logo"):
            st.session_state.logo_data = None
            st.rerun()
    else:
        up = st.file_uploader("🖼️ Subir Logo", type=["png", "jpg"])
        if up: st.session_state.logo_data = up.read(); st.rerun()
    
    st.divider()
    menu = st.radio("MENU PRINCIPAL", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])
    
    st.divider()
    st.subheader("💾 Gestão de Dados")
    try:
        if os.path.exists(DB_NAME):
            with open(DB_NAME, "rb") as f:
                st.download_button("📥 Baixar Backup Atual", f, f"backup_fretes_{datetime.now().strftime('%d_%m_%H%M')}.db", "application/x-sqlite3")
    except: pass
    restore_file = st.file_uploader("📤 Restaurar Backup (.db)", type=["db"])
    if restore_file and st.button("✅ Confirmar Restauração"):
        with open(DB_NAME, "wb") as f: f.write(restore_file.getbuffer())
        st.success("Dados restaurados!"); st.rerun()

# --- DASHBOARD (RESTURADO COM FILTROS) ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()
    
    if not df_h.empty:
        all_data = []
        for _, row in df_h.iterrows():
            temp_df = pd.read_json(io.StringIO(row['detalhes_json']))
            # Garante que a coluna de transportadora do histórico seja levada para o dashboard
            if 'T_NOME' not in temp_df.columns:
                temp_df['T_NOME'] = row['transportadora']
            all_data.append(temp_df)
        df_full = pd.concat(all_data, ignore_index=True)

        # RESTAURAÇÃO DOS FILTROS APROVADOS
        st.subheader("🎯 Filtros")
        f1, f2 = st.columns(2)
        sel_t = f1.multiselect("Transportadora", options=df_full['T_NOME'].unique())
        sel_uf = f2.multiselect("UF", options=df_full['UF'].unique() if 'UF' in df_full.columns else ["N/A"])

        if sel_t: df_full = df_full[df_full['T_NOME'].isin(sel_t)]
        if sel_uf: df_full = df_full[df_full['UF'].isin(sel_uf)]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {formata_br(df_full['VALOR_SISTEMA'].sum())}")
        c2.metric("Notas Processadas", f"{len(df_full)}")
        c3.metric("Peso Total", f"{formata_br(df_full['PESO'].sum())} kg")
        
        st.subheader("📍 Resumo por UF e Transportadora")
        if 'UF' in df_full.columns:
            pivot_uf = df_full.pivot_table(index='UF', columns='T_NOME', values='VALOR_SISTEMA', aggfunc='sum', fill_value=0)
            st.dataframe(pivot_uf.map(formata_br), use_container_width=True)
    else:
        st.info("Nenhuma cotação no histórico.")

# --- TRANSPORTADORAS ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    is_editing = st.session_state.edit_id is not None
    
    with st.expander("📝 Configurar Mapeamento", expanded=is_editing):
        edit_data = None
        mapa_previo = {"faixas": [], "taxas": {}, "kg_extra": "Não mapear", "col_cid": "Não mapear", "col_sigla": "Não mapear"}
        if is_editing:
            conn = sqlite3.connect(DB_NAME)
            edit_data = pd.read_sql_query(f"SELECT * FROM transportadoras WHERE id={st.session_state.edit_id}", conn).iloc[0]
            conn.close()
            mapa_previo = json.loads(edit_data['mapeamento_json'])

        t_nome = st.text_input("Nome da Transportadora", value=edit_data['nome'] if is_editing else "").upper()
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("Tabela de Preços (Excel)", type=["xlsx"])
        f_cid = c2.file_uploader("Planilha de Apoio (Cidades)", type=["xlsx"])
        
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.read_json(io.StringIO(edit_data['tabela_json'])) if is_editing else None)
        df_c = pd.read_excel(f_cid).fillna(0) if f_cid else (pd.read_json(io.StringIO(edit_data['cidades_json'])) if is_editing else None)

        if df_t is not None and df_c is not None:
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_c = ["Não mapear"] + [str(c) for c in df_c.columns]
            
            st.subheader("📍 Mapeamento")
            m1, m2 = st.columns(2)
            m_col_cid = m1.selectbox("Coluna Cidade", cols_c, index=cols_c.index(str(mapa_previo.get('col_cid'))) if str(mapa_previo.get('col_cid')) in cols_c else 0)
            m_col_sigla = m2.selectbox("Coluna Sigla", cols_c, index=cols_c.index(str(mapa_previo.get('col_sigla'))) if str(mapa_previo.get('col_sigla')) in cols_c else 0)

            st.subheader("⚖️ Regras")
            col_kg_extra = st.selectbox("Kg Adicional", cols_t, index=cols_t.index(str(mapa_previo.get('kg_extra'))) if str(mapa_previo.get('kg_extra')) in cols_t else 0)
            n_f = st.number_input("Qtd Faixas", 1, 50, len(mapa_previo['faixas']) if is_editing else 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3)
                f_ini = mapa_previo['faixas'][i] if is_editing and i < len(mapa_previo['faixas']) else {}
                faixas.append({"min": r[0].number_input(f"De", value=float(f_ini.get('min', 0.0)), key=f"mi{i}"), "max": r[1].number_input(f"Até", value=float(f_ini.get('max', 0.0)), key=f"ma{i}"), "col": r[2].selectbox(f"Coluna", cols_t, index=cols_t.index(str(f_ini.get('col'))) if str(f_ini.get('col')) in cols_t else 0, key=f"co{i}")})
            
            taxas_n = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_n):
                s_tx = str(mapa_previo.get('taxas', {}).get(tx, "Não mapear"))
                m_taxas[tx] = tx_cols[idx % 3].
