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

# URL do Apps Script para integração Google Sheets
SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw2stGRESs-l0dJQEd3bKAawtUb8_zRH1i3VIb4DALNSjdjZnked9Lxs97ProouwR0/exec"

def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
    [data-testid="stMetric"] { border: 1px solid #ddd; padding: 10px; border-radius: 8px; background-color: rgba(255,255,255,0.05); }
    .tax-text { font-size: 14px; margin-bottom: 2px; }
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

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()
    
    if not df_h.empty:
        all_data = []
        for _, row in df_h.iterrows():
            temp_df = pd.read_json(io.StringIO(row['detalhes_json']))
            temp_df['Transportadora_Ref'] = row['transportadora']
            all_data.append(temp_df)
        df_full = pd.concat(all_data, ignore_index=True)

        st.subheader("🎯 Filtros")
        f1, f2 = st.columns(2)
        sel_t = f1.multiselect("Transportadora", options=df_full['Transportadora_Ref'].unique())
        sel_uf = f2.multiselect("UF", options=df_full['UF'].unique() if 'UF' in df_full.columns else ["N/A"])

        if sel_t: df_full = df_full[df_full['Transportadora_Ref'].isin(sel_t)]
        if sel_uf: df_full = df_full[df_full['UF'].isin(sel_uf)]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_full['VALOR_SISTEMA'].sum():,.2f}")
        c2.metric("Notas Processadas", f"{len(df_full)}")
        c3.metric("Peso Total", f"{df_full['PESO'].sum():,.2f} kg")

        st.subheader("📍 Resumo por UF e Transportadora")
        if 'UF' in df_full.columns:
            pivot_uf = df_full.pivot_table(index='UF', columns='Transportadora_Ref', values='VALOR_SISTEMA', aggfunc='sum', fill_value=0)
            st.dataframe(pivot_uf, use_container_width=True)
        else:
            st.warning("Coluna UF não encontrada nas notas.")
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
            
            st.subheader("📍 Mapeamento (Cidades)")
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

# --- COMPARATIVO ---
elif menu == "💰 Comparativo":
    st.title("💰 Cálculo de Fretes")
    f_base = st.file_uploader("📥 Subir Planilha de Notas Fiscais", type=["xlsx"])
    conn = sqlite3.connect(DB_NAME); ts = pd.read_sql_query("SELECT * FROM transportadoras", conn); conn.close()
    
    if not ts.empty:
        t_alvo = st.selectbox("Selecione a Transportadora", ts['nome'].tolist())
        if f_base and st.button("🚀 Calcular Agora"):
            df_b = pd.read_excel(f_base).fillna(0); t_row = ts[ts['nome'] == t_alvo].iloc[0]
            df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
            df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
            mapa = json.loads(t_row['mapeamento_json'])
            
            df_b['BUSCA_NF'] = df_b.iloc[:, 2].apply(normalizar)
            df_cid_ref['BUSCA_REF'] = df_cid_ref[mapa['col_cid']].apply(normalizar)
            df_proc = pd.merge(df_b, df_cid_ref[['BUSCA_REF', mapa['col_sigla']]], left_on='BUSCA_NF', right_on='BUSCA_REF', how='left')
            df_tab['SIGLA_CHAVE'] = df_tab.iloc[:, 2].apply(normalizar)

            res = []
            for _, nf in df_proc.iterrows():
                try:
                    peso_nf = float(nf.iloc[6]); valor_nf = float(nf.iloc[7]); sigla = normalizar(str(nf[mapa['col_sigla']]))
                    linha_preco = df_tab[df_tab['SIGLA_CHAVE'] == sigla].iloc[0]
                    
                    f_peso = 0.0; u_max = 0; u_col = ""; d = False
                    for f in mapa['faixas']:
                        u_max, u_col = f['max'], f['col']
                        if peso_nf <= f['max'] and f['col'] != "Não mapear":
                            f_peso = float(linha_preco[f['col']]); d = True; break
                    if not d and mapa.get('kg_extra') != "Não mapear":
                        f_peso = float(linha_preco[u_col]) + ((peso_nf - u_max) * float(linha_preco[mapa['kg_extra']]))
                    
                    def gv(n): return float(linha_preco[mapa['taxas'][n]]) if n in mapa['taxas'] and mapa['taxas'][n] != "Não mapear" else 0.0
                    
                    tx_adval = max(valor_nf * gv("Ad Valorem %"), gv("Ad Valorem Min"))
                    tx_gris = max(valor_nf * gv("Gris %"), gv("Gris Min"))
                    tx_pedagio = (math.ceil(peso_nf/100)*gv("Pedagio"))
                    
                    # Cálculo detalhado para o histórico
                    tas = gv("TAS"); ctrc = gv("CTRC"); trt = gv("TRT"); tda = gv("TDA"); seccat = gv("SEC-CAT")
                    tx_fixas_total = tas + ctrc + trt + tda + seccat
                    
                    total = f_peso + tx_adval + tx_gris + tx_pedagio + tx_fixas_total
                    
                    nf_d = nf.to_dict()
                    nf_d.update({
                        "VALOR_SISTEMA": round(total, 2), "F_PESO": round(f_peso, 2),
                        "ADVALOREM": round(tx_adval, 2), "GRIS": round(tx_gris, 2),
                        "PEDAGIO": round(tx_pedagio, 2), "TAS": tas, "CTRC": ctrc, 
                        "TRT": trt, "TDA": tda, "SECCAT": seccat
                    })
                    res.append(nf_d)
                except:
                    nf_d = nf.to_dict(); nf_d["VALOR_SISTEMA"] = 0.0; res.append(nf_d)

            df_res = pd.DataFrame(res)
            try:
                payload = {"Nome": t_alvo, "Total": df_res['VALOR_SISTEMA'].sum(), "Qtd": len(df_res)}
                requests.post(SCRIPT_URL, data=json.dumps(payload))
            except: pass

            conn = sqlite3.connect(DB_NAME)
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json) VALUES (?,?,?,?,?)",
                         (datetime.now().strftime("%d/%m/%Y %H:%M"), t_alvo, df_res['VALOR_SISTEMA'].sum(), len(df_res), df_res.to_json()))
            conn.commit(); conn.close(); st.rerun()

    st.divider()
    st.subheader("🕒 Histórico de Cotações")
    conn = sqlite3.connect(DB_NAME); df_h = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn); conn.close()
    
    for _, row in df_h.iterrows():
        with st.expander(f"📅 {row['data_hora']} | {row['transportadora']} | Total: R$ {row['total']:,.2f}"):
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            
            c_del1, c_del2 = st.columns([8, 2])
            if c_del2.button("🗑️ Excluir Cotação", key=f"del_cot_{row['id']}"):
                conn = sqlite3.connect(DB_NAME)
                conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],))
                conn.commit(); conn.close(); st.rerun()

            st.write("**🔍 Detalhamento por Nota:**")
            for _, nota in df_det.iterrows():
                with st.expander(f"👁️ Nota: {nota['NF']} - {nota['CIDADE']} ({nota['UF']}) | R$ {nota['VALOR_SISTEMA']:,.2f}"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f"**Frete Peso:** R$ {nota.get('F_PESO', 0):,.2f}")
                        st.markdown(f"**Ad Valorem:** R$ {nota.get('ADVALOREM', 0):,.2f}")
                        st.markdown(f"**Gris:** R$ {nota.get('GRIS', 0):,.2f}")
                    with c2:
                        st.markdown(f"**Pedágio:** R$ {nota.get('PEDAGIO', 0):,.2f}")
                        st.markdown(f"**TAS:** R$ {nota.get('TAS', 0):,.2f}")
                        st.markdown(f"**CTRC:** R$ {nota.get('CTRC', 0):,.2f}")
                    with c3:
                        st.markdown(f"**TRT:** R$ {nota.get('TRT', 0):,.2f}")
                        st.markdown(f"**TDA:** R$ {nota.get('TDA', 0):,.2f}")
                        st.markdown(f"**SEC-CAT:** R$ {nota.get('SECCAT', 0):,.2f}")
                    st.divider()
                    st.subheader(f"Total: R$ {nota['VALOR_SISTEMA']:,.2f}")
