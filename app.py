import streamlit as st
import pandas as pd
import sqlite3
import json
import io
import os
from datetime import datetime
import math
import unicodedata
import numpy as np

# 1. Configuração de Layout
st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")

def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def formata_br(valor):
    try:
        if pd.isna(valor) or valor == 0: return "0,00"
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

# --- SIDEBAR (Mantida igual) ---
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

# --- DASHBOARD (Mantido igual) ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()
    
    if not df_h.empty:
        all_data = []
        for _, row in df_h.iterrows():
            try:
                temp_df = pd.read_json(io.StringIO(row['detalhes_json']))
                if 'T_NOME' not in temp_df.columns: temp_df['T_NOME'] = row['transportadora']
                all_data.append(temp_df)
            except: continue
        
        if all_data:
            df_full = pd.concat(all_data, ignore_index=True)
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

            st.subheader("⚖️ Regras de Peso")
            col_kg_extra = st.selectbox("Kg Adicional", cols_t, index=cols_t.index(str(mapa_previo.get('kg_extra'))) if str(mapa_previo.get('kg_extra')) in cols_t else 0)
            n_f = st.number_input("Qtd Faixas", 1, 50, len(mapa_previo['faixas']) if is_editing else 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3)
                f_ini = mapa_previo['faixas'][i] if is_editing and i < len(mapa_previo['faixas']) else {}
                faixas.append({"min": r[0].number_input(f"De", value=float(f_ini.get('min', 0.0)), key=f"mi{i}"), "max": r[1].number_input(f"Até", value=float(f_ini.get('max', 0.0)), key=f"ma{i}"), "col": r[2].selectbox(f"Coluna", cols_t, index=cols_t.index(str(f_ini.get('col'))) if str(f_ini.get('col')) in cols_t else 0, key=f"co{i}")})
            
            st.subheader("💰 Taxas Adicionais")
            taxas_n = [
                "Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", 
                "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", 
                "SEC-CAT", "Suframa (Fixo)", "Fluvial %", "Redespacho Fluvial %"
            ]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_n):
                s_tx = str(mapa_previo.get('taxas', {}).get(tx, "Não mapear"))
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(s_tx) if s_tx in cols_t else 0, key=f"tx_{tx}")

            if st.button("💾 Salvar"):
                mapa = {"faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_extra, "col_cid": m_col_cid, "col_sigla": m_col_sigla}
                conn = sqlite3.connect(DB_NAME)
                if is_editing:
                    conn.execute("UPDATE transportadoras SET nome=?, tabela_json=?, cidades_json=?, mapeamento_json=? WHERE id=?", (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa), st.session_state.edit_id))
                else:
                    conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)", (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa)))
                conn.commit(); conn.close(); st.session_state.edit_id = None; st.rerun()

    ts = pd.read_sql_query("SELECT id, nome FROM transportadoras", sqlite3.connect(DB_NAME))
    for _, row in ts.iterrows():
        c1, c2, c3 = st.columns([7, 1.5, 1.5])
        c1.write(f"**{row['nome']}**")
        if c2.button("✏️", key=f"ed_{row['id']}"): st.session_state.edit_id = row['id']; st.rerun()
        if c3.button("🗑️", key=f"dl_{row['id']}"):
            conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM transportadoras WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()

# --- COMPARATIVO (OTIMIZADO PARA 18K LINHAS) ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo de Fretes Otimizado")
    f_base = st.file_uploader("📥 Subir Planilha de Notas Fiscais (Base)", type=["xlsx"])
    
    conn = sqlite3.connect(DB_NAME)
    ts_db = pd.read_sql_query("SELECT * FROM transportadoras", conn)
    conn.close()
    
    if not ts_db.empty:
        opcoes = ts_db['nome'].tolist()
        selecionadas = st.multiselect("Selecione as Transportadoras", options=opcoes)
        
        if f_base and selecionadas and st.button("🚀 Calcular"):
            with st.spinner("Processando milhares de linhas... aguarde."):
                df_b_original = pd.read_excel(f_base).fillna(0)
                consolidado_historico = []
                
                # Identifica colunas fixas da base (NF, Cidade, UF, Peso, Valor)
                # Assumindo: 2=NF, 5=Cidade, 6=Peso, 7=Valor (baseado no código anterior)
                
                for t_nome in selecionadas:
                    t_row = ts_db[ts_db['nome'] == t_nome].iloc[0]
                    df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
                    df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
                    mapa = json.loads(t_row['mapeamento_json'])
                    
                    df_calc = df_b_original.copy()
                    df_calc['BUSCA_NF'] = df_calc.iloc[:, 2].apply(normalizar)
                    df_cid_ref['BUSCA_REF'] = df_cid_ref[mapa['col_cid']].apply(normalizar)
                    
                    # Merge para pegar a Sigla de uma vez
                    df_proc = pd.merge(df_calc, df_cid_ref[['BUSCA_REF', mapa['col_sigla']]], left_on='BUSCA_NF', right_on='BUSCA_REF', how='left')
                    df_tab['SIGLA_CHAVE'] = df_tab.iloc[:, 2].apply(normalizar)
                    
                    # Merge para pegar os preços da tabela
                    df_final_t = pd.merge(df_proc, df_tab, left_on=mapa['col_sigla'], right_on='SIGLA_CHAVE', how='left')
                    
                    # --- CÁLCULO VETORIZADO (SEM LOOP) ---
                    peso = df_final_t.iloc[:, 6].astype(float)
                    valor_nf = df_final_t.iloc[:, 7].astype(float)
                    
                    # Cálculo Frete Peso por Faixa
                    df_final_t['F_PESO'] = 0.0
                    for f in mapa['faixas']:
                        mask = (peso <= f['max']) & (df_final_t['F_PESO'] == 0.0) & (f['col'] != "Não mapear")
                        if f['col'] in df_final_t.columns:
                            df_final_t.loc[mask, 'F_PESO'] = df_final_t.loc[mask, f['col']].astype(float)
                    
                    # Kg Extra (Vetorizado)
                    if mapa.get('kg_extra') != "Não mapear" and mapa.get('kg_extra') in df_final_t.columns:
                        u_max = mapa['faixas'][-1]['max']
                        u_col = mapa['faixas'][-1]['col']
                        mask_extra = (peso > u_max)
                        df_final_t.loc[mask_extra, 'F_PESO'] = df_final_t.loc[mask_extra, u_col].astype(float) + \
                            ((peso[mask_extra] - u_max) * df_final_t.loc[mask_extra, mapa['kg_extra']].astype(float))

                    # Taxas (Vetorizado)
                    def get_v(name):
                        col = mapa['taxas'].get(name, "Não mapear")
                        return df_final_t[col].astype(float) if col in df_final_t.columns else 0.0

                    df_final_t['ADVAL'] = np.maximum(valor_nf * get_v("Ad Valorem %"), get_v("Ad Valorem Min"))
                    df_final_t['GRIS'] = np.maximum(valor_nf * get_v("Gris %"), get_v("Gris Min"))
                    df_final_t['PEDAGIO'] = np.ceil(peso / 100) * get_v("Pedagio")
                    df_final_t['TAS'] = get_v("TAS")
                    df_final_t['CTRC'] = get_v("CTRC")
                    df_final_t['TRT'] = get_v("TRT")
                    df_final_t['TDA'] = get_v("TDA")
                    df_final_t['SECCAT'] = get_v("SEC-CAT")
                    df_final_t['EMEX'] = np.maximum(valor_nf * get_v("Emex %"), get_v("Emex Min"))
                    df_final_t['SUFRAMA'] = get_v("Suframa (Fixo)")
                    df_final_t['FLUVIAL'] = valor_nf * get_v("Fluvial %")
                    df_final_t['RED_FLUVIAL'] = valor_nf * get_v("Redespacho Fluvial %")
                    
                    # Total
                    cols_total = ['F_PESO', 'ADVAL', 'GRIS', 'PEDAGIO', 'TAS', 'CTRC', 'TRT', 'TDA', 'SECCAT', 'EMEX', 'SUFRAMA', 'FLUVIAL', 'RED_FLUVIAL']
                    df_final_t['VALOR_SISTEMA'] = df_final_t[cols_total].sum(axis=1)
                    df_final_t['T_NOME'] = t_nome
                    
                    # Manter apenas colunas necessárias para o histórico (economiza memória)
                    cols_to_keep = list(df_b_original.columns) + cols_total + ['VALOR_SISTEMA', 'T_NOME']
                    consolidado_historico.append(df_final_t[cols_to_keep])
                
                df_storage = pd.concat(consolidado_historico)
                nome_label = "LOTE_" + datetime.now().strftime("%H%M")
                
                conn = sqlite3.connect(DB_NAME)
                conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json) VALUES (?,?,?,?,?)",
                             (datetime.now().strftime("%d/%m/%Y %H:%M"), nome_label, df_storage['VALOR_SISTEMA'].sum(), len(df_b_original), df_storage.to_json()))
                conn.commit(); conn.close()
                st.success("Calculado com sucesso!")
                st.rerun()

    st.divider()
    st.subheader("🕒 Histórico")
    conn = sqlite3.connect(DB_NAME); df_h = pd.read_sql_query("SELECT id, data_hora, transportadora, total FROM cotacoes ORDER BY id DESC", conn); conn.close()
    
    for _, row in df_h.iterrows():
        with st.expander(f"📅 {row['data_hora']} | {row['transportadora']} | R$ {formata_br(row['total'])}"):
            c1, c2 = st.columns(2)
            if c1.button("🗑️ Excluir", key=f"del_{row['id']}"):
                conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()
            
            if c2.button("👁️ Ver Detalhes (Pode demorar se for grande)", key=f"view_{row['id']}"):
                conn = sqlite3.connect(DB_NAME)
                detalhes = pd.read_sql_query(f"SELECT detalhes_json FROM cotacoes WHERE id={row['id']}", conn).iloc[0]['detalhes_json']
                conn.close()
                df_det = pd.read_json(io.StringIO(detalhes))
                st.dataframe(df_det)
