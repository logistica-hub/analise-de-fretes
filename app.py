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
                st.download_button("📥 Baixar Backup", f, f"backup_fretes.db", "application/x-sqlite3")
    except: pass
    restore_file = st.file_uploader("📤 Restaurar Backup", type=["db"])
    if restore_file and st.button("✅ Confirmar"):
        with open(DB_NAME, "wb") as f: f.write(restore_file.getbuffer())
        st.success("Restaurado!"); st.rerun()

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT detalhes_json FROM cotacoes", conn)
    conn.close()
    if not df_h.empty:
        dfs = [pd.read_json(io.StringIO(r['detalhes_json'])) for _, r in df_h.iterrows()]
        df_full = pd.concat(dfs, ignore_index=True)
        st.metric("Total Cotado", f"R$ {formata_br(df_full['VALOR_SISTEMA'].sum())}")
        st.dataframe(df_full.head(100))
    else:
        st.info("Sem dados.")

# --- TRANSPORTADORAS (MAPEAMENTO DINÂMICO TOTAL) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Configuração Dinâmica")
    is_editing = st.session_state.edit_id is not None
    
    with st.expander("📝 Cadastro Completo", expanded=is_editing):
        edit_data = None
        # Mapa inicial vazio ou carregado
        mapa = {"faixas": [], "taxas": {}, "kg_extra": "Não mapear", 
                "ap_cidade": "Não mapear", "ap_sigla": "Não mapear",
                "tab_sigla": "Não mapear", "tab_uf": "Não mapear"}
        
        if is_editing:
            conn = sqlite3.connect(DB_NAME)
            edit_data = pd.read_sql_query(f"SELECT * FROM transportadoras WHERE id={st.session_state.edit_id}", conn).iloc[0]
            conn.close()
            mapa.update(json.loads(edit_data['mapeamento_json']))

        t_nome = st.text_input("Nome da Transportadora", value=edit_data['nome'] if is_editing else "").upper()
        
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("Tabela de Preços", type=["xlsx"])
        f_cid = c2.file_uploader("Planilha de Abrangência", type=["xlsx"])
        
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.read_json(io.StringIO(edit_data['tabela_json'])) if is_editing else None)
        df_c = pd.read_excel(f_cid).fillna(0) if f_cid else (pd.read_json(io.StringIO(edit_data['cidades_json'])) if is_editing else None)

        if df_t is not None and df_c is not None:
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_c = ["Não mapear"] + [str(c) for c in df_c.columns]
            
            st.subheader("🔗 Ligações entre Planilhas")
            col_l1, col_l2 = st.columns(2)
            
            with col_l1:
                st.info("Planilha de Abrangência")
                m_ap_cid = st.selectbox("Coluna com Nome da Cidade", cols_c, index=cols_c.index(str(mapa.get('ap_cidade'))) if str(mapa.get('ap_cidade')) in cols_c else 0)
                m_ap_sig = st.selectbox("Coluna com a Sigla (Chave)", cols_c, index=cols_c.index(str(mapa.get('ap_sigla'))) if str(mapa.get('ap_sigla')) in cols_c else 0)
            
            with col_l2:
                st.info("Tabela de Preços")
                m_tab_sig = st.selectbox("Coluna com a Sigla (Para Match)", cols_t, index=cols_t.index(str(mapa.get('tab_sigla'))) if str(mapa.get('tab_sigla')) in cols_t else 0)
                m_tab_uf = st.selectbox("Coluna com a UF", cols_t, index=cols_t.index(str(mapa.get('tab_uf'))) if str(mapa.get('tab_uf')) in cols_t else 0)

            st.subheader("⚖️ Regras de Peso")
            col_kg_extra = st.selectbox("Preço Kg Adicional", cols_t, index=cols_t.index(str(mapa.get('kg_extra'))) if str(mapa.get('kg_extra')) in cols_t else 0)
            n_f = st.number_input("Quantidade de Faixas de Peso", 1, 50, len(mapa['faixas']) if mapa['faixas'] else 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3)
                f_ini = mapa['faixas'][i] if i < len(mapa['faixas']) else {}
                faixas.append({
                    "min": r[0].number_input(f"De kg", value=float(f_ini.get('min', 0.0)), key=f"mi{i}"),
                    "max": r[1].number_input(f"Até kg", value=float(f_ini.get('max', 0.0)), key=f"ma{i}"),
                    "col": r[2].selectbox(f"Coluna na Tabela", cols_t, index=cols_t.index(str(f_ini.get('col'))) if str(f_ini.get('col')) in cols_t else 0, key=f"co{i}")
                })
            
            st.subheader("💰 Taxas Adicionais")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT", "Suframa (Fixo)", "Fluvial %", "Redespacho Fluvial %"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                s_tx = str(mapa.get('taxas', {}).get(tx, "Não mapear"))
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(s_tx) if s_tx in cols_t else 0, key=f"tx_{tx}")

            if st.button("💾 Salvar Mapeamento"):
                novo_mapa = {
                    "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_extra,
                    "ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig,
                    "tab_sigla": m_tab_sig, "tab_uf": m_tab_uf
                }
                conn = sqlite3.connect(DB_NAME)
                conn.execute("INSERT OR REPLACE INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)", (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(novo_mapa)))
                conn.commit(); conn.close(); st.session_state.edit_id = None; st.rerun()

    ts = pd.read_sql_query("SELECT id, nome FROM transportadoras", sqlite3.connect(DB_NAME))
    for _, row in ts.iterrows():
        c1, c2, c3 = st.columns([7, 1.5, 1.5])
        c1.write(f"**{row['nome']}**")
        if c2.button("✏️", key=f"ed_{row['id']}"): st.session_state.edit_id = row['id']; st.rerun()
        if c3.button("🗑️", key=f"dl_{row['id']}"):
            sqlite3.connect(DB_NAME).execute("DELETE FROM transportadoras WHERE id=?", (row['id'],)).connection.commit(); st.rerun()

# --- COMPARATIVO (BLINDADO) ---
elif menu == "💰 Comparativo":
    st.title("💰 Cálculo Vetorizado")
    f_base = st.file_uploader("📥 Planilha de Notas", type=["xlsx"])
    ts_db = pd.read_sql_query("SELECT * FROM transportadoras", sqlite3.connect(DB_NAME))
    
    if not ts_db.empty and f_base:
        selecionadas = st.multiselect("Transportadoras", ts_db['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular"):
            df_b = pd.read_excel(f_base).fillna(0)
            result_final = []
            
            for t_nome in selecionadas:
                t_row = ts_db[ts_db['nome'] == t_nome].iloc[0]
                df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
                df_ap = pd.read_json(io.StringIO(t_row['cidades_json']))
                m = json.loads(t_row['mapeamento_json'])
                
                # 1. Normalização das Chaves
                df_calc = df_b.copy()
                df_calc['KEY_CIDADE'] = df_calc.iloc[:, 2].astype(str).apply(normalizar) # Coluna 3 da base (Cidade)
                df_ap['KEY_REF'] = df_ap[m['ap_cidade']].astype(str).apply(normalizar)
                df_tab['KEY_TAB'] = df_tab[m['tab_sigla']].astype(str).apply(normalizar)
                
                # 2. Merge Abrangência -> Base
                df_step1 = pd.merge(df_calc, df_ap[[m['ap_sigla'], 'KEY_REF']], left_on='KEY_CIDADE', right_on='KEY_REF', how='left')
                df_step1['KEY_SIGLA_B'] = df_step1[m['ap_sigla']].astype(str).apply(normalizar)
                
                # 3. Merge Tabela -> Resultado
                df_final = pd.merge(df_step1, df_tab, left_on='KEY_SIGLA_B', right_on='KEY_TAB', how='left')
                
                # 4. Cálculos Numéricos
                peso = pd.to_numeric(df_final.iloc[:, 6], errors='coerce').fillna(0)
                valor = pd.to_numeric(df_final.iloc[:, 7], errors='coerce').fillna(0)
                
                df_final['F_PESO'] = 0.0
                for f in m['faixas']:
                    if f['col'] in df_final.columns:
                        mask = (peso <= f['max']) & (df_final['F_PESO'] == 0.0)
                        df_final.loc[mask, 'F_PESO'] = pd.to_numeric(df_final.loc[mask, f['col']], errors='coerce').fillna(0)
                
                # Kg Extra
                if m['kg_extra'] in df_final.columns:
                    u_max, u_col = m['faixas'][-1]['max'], m['faixas'][-1]['col']
                    mask_ex = (peso > u_max)
                    base_p = pd.to_numeric(df_final.loc[mask_ex, u_col], errors='coerce').fillna(0)
                    adicional = pd.to_numeric(df_final.loc[mask_ex, m['kg_extra']], errors='coerce').fillna(0)
                    df_final.loc[mask_ex, 'F_PESO'] = base_p + ((peso[mask_ex] - u_max) * adicional)

                def gv(name):
                    col = m['taxas'].get(name, "Não mapear")
                    return pd.to_numeric(df_final[col], errors='coerce').fillna(0) if col in df_final.columns else 0.0

                df_final['ADVAL'] = np.maximum(valor * gv("Ad Valorem %"), gv("Ad Valorem Min"))
                df_final['GRIS'] = np.maximum(valor * gv("Gris %"), gv("Gris Min"))
                df_final['PEDAGIO'] = np.ceil(peso / 100) * gv("Pedagio")
                df_final['VALOR_SISTEMA'] = df_final[['F_PESO','ADVAL','GRIS','PEDAGIO']].sum(axis=1) + gv("TAS") + gv("CTRC") + gv("TRT") + gv("TDA") + gv("SEC-CAT")
                
                df_final['T_NOME'] = t_nome
                result_final.append(df_final)

            df_res = pd.concat(result_final, ignore_index=True)
            conn = sqlite3.connect(DB_NAME)
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json) VALUES (?,?,?,?,?)",
                         (datetime.now().strftime("%d/%m %H:%M"), "LOTE", df_res['VALOR_SISTEMA'].sum(), len(df_b), df_res.to_json()))
            conn.commit(); st.success("Cálculo pronto!"); st.rerun()

    # Histórico simplificado
    st.divider()
    conn = sqlite3.connect(DB_NAME); hist = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn); conn.close()
    for _, r in hist.iterrows():
        with st.expander(f"Lote {r['data_hora']} - R$ {formata_br(r['total'])}"):
            st.dataframe(pd.read_json(io.StringIO(r['detalhes_json'])))
