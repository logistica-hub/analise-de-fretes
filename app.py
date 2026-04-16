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

SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw2stGRESs-l0dJQEd3bKAawtUb8_zRH1i3VIb4DALNSjdjZnked9Lxs97ProouwR0/exec"
SHEET_CSV = "https://docs.google.com/spreadsheets/d/1xKSw0CXynVDJfq1_CplAHtGT9zM4aYk_pxR4NLZu0-U/export?format=csv&gid=0"

# Função de Normalização (Remove acentos, espaços e padroniza)
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
                  total REAL, qtd INTEGER, detalhes_json TEXT, estado_resumo TEXT)''')
    conn.commit()
    conn.close()

init_db()

if 'view_details' not in st.session_state:
    st.session_state.view_details = {}
if 'edit_id' not in st.session_state:
    st.session_state.edit_id = None

with st.sidebar:
    if 'logo_data' not in st.session_state: st.session_state.logo_data = None
    if st.session_state.logo_data:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Editar Logo"):
            st.session_state.logo_data = None
            st.rerun()
    else:
        up = st.file_uploader("🖼️ Subir Logo", type=["png", "jpg"])
        if up: 
            st.session_state.logo_data = up.read(); st.rerun()
    st.divider()
    menu = st.radio("MENU PRINCIPAL", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])

if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        todas_notas = []
        for _, row in df_h.iterrows():
            notas_lote = pd.read_json(io.StringIO(row['detalhes_json']))
            notas_lote['Transportadora_Ref'] = row['transportadora']
            if 'UF' not in notas_lote.columns: notas_lote['UF'] = notas_lote.iloc[:, 3]
            todas_notas.append(notas_lote)
        
        df_bi = pd.concat(todas_notas, ignore_index=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_bi['VALOR_SISTEMA'].sum():,.2f}")
        c2.metric("Notas Processadas", f"{len(df_bi)}") 
        c3.metric("Ticket Médio", f"R$ {df_bi['VALOR_SISTEMA'].mean():,.2f}" if len(df_bi) > 0 else "R$ 0,00")
        st.dataframe(df_bi.pivot_table(index="UF", columns="Transportadora_Ref", values="VALOR_SISTEMA", aggfunc="sum").fillna(0), use_container_width=True)

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

        t_nome = st.text_input("Nome", value=edit_data['nome'] if is_editing else "").upper()
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("Tabela Preços", type=["xlsx"])
        f_cid = c2.file_uploader("Planilha de Apoio (Cidades)", type=["xlsx"])
        
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.read_json(io.StringIO(edit_data['tabela_json'])) if is_editing else None)
        df_c = pd.read_excel(f_cid).fillna(0) if f_cid else (pd.read_json(io.StringIO(edit_data['cidades_json'])) if is_editing else None)

        if df_t is not None and df_c is not None:
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_c = ["Não mapear"] + [str(c) for c in df_c.columns]
            
            st.subheader("📍 Mapeamento de Colunas")
            m1, m2 = st.columns(2)
            m_col_cid = m1.selectbox("Coluna da Cidade", cols_c, index=cols_c.index(str(mapa_previo.get('col_cid'))) if str(mapa_previo.get('col_cid')) in cols_c else 0)
            m_col_sigla = m2.selectbox("Coluna da Sigla", cols_c, index=cols_c.index(str(mapa_previo.get('col_sigla'))) if str(mapa_previo.get('col_sigla')) in cols_c else 0)

            st.subheader("⚖️ Pesos e Taxas")
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
                try:
                    payload = {"Nome": t_nome, "Mapeamento": f"Cidade:{m_col_cid} | Sigla:{m_col_sigla}"}
                    requests.post(SCRIPT_URL, data=json.dumps(payload))
                except: pass
                conn = sqlite3.connect(DB_NAME)
                if is_editing:
                    conn.execute("UPDATE transportadoras SET nome=?, tabela_json=?, cidades_json=?, mapeamento_json=? WHERE id=?", (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa), st.session_state.edit_id))
                else:
                    conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)", (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa)))
                conn.commit(); conn.close(); st.session_state.edit_id = None; st.rerun()

    st.markdown("### 📋 Lista")
    conn = sqlite3.connect(DB_NAME); ts = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn); conn.close()
    for _, row in ts.iterrows():
        c1, c2, c3 = st.columns([7, 1.5, 1.5])
        c1.write(f"**{row['nome']}**")
        if c2.button("✏️", key=f"ed_{row['id']}"): st.session_state.edit_id = row['id']; st.rerun()
        if c3.button("🗑️", key=f"dl_{row['id']}"):
            conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM transportadoras WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()

elif menu == "💰 Comparativo":
    st.title("💰 Novo Cálculo")
    f_base = st.file_uploader("📥 Notas Fiscais", type=["xlsx"])
    conn = sqlite3.connect(DB_NAME); ts = pd.read_sql_query("SELECT * FROM transportadoras", conn); conn.close()
    
    if not ts.empty:
        t_alvo = st.selectbox("Transportadora", ts['nome'].tolist())
        if f_base and st.button("🚀 Calcular"):
            df_b = pd.read_excel(f_base).fillna(0); t_row = ts[ts['nome'] == t_alvo].iloc[0]
            df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
            df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
            mapa = json.loads(t_row['mapeamento_json'])
            
            c_cid = mapa.get('col_cid'); c_sig = mapa.get('col_sigla')
            if c_cid == "Não mapear" or c_sig == "Não mapear":
                st.error("Configure o mapeamento na aba Transportadoras."); st.stop()

            # 1. Normaliza as colunas de busca (Cidades)
            df_b['BUSCA_NF'] = df_b.iloc[:, 2].apply(normalizar)
            df_cid_ref['BUSCA_REF'] = df_cid_ref[c_cid].apply(normalizar)
            
            # 2. Faz o cruzamento para achar a sigla
            df_proc = pd.merge(df_b, df_cid_ref[['BUSCA_REF', c_sig]], left_on='BUSCA_NF', right_on='BUSCA_REF', how='left')
            
            # 3. Importante: Limpa e normaliza a coluna de siglas da TABELA DE PREÇOS
            # Usamos .iloc[:, 2] para a sigla na tabela Jamef conforme o arquivo enviado
            df_tab['SIGLA_CHAVE'] = df_tab.iloc[:, 2].apply(normalizar)

            res = []
            for _, nf in df_proc.iterrows():
                try:
                    peso_nf = float(nf.iloc[6]); valor_nf = float(nf.iloc[7])
                    sigla_encontrada = str(nf[c_sig])
                    sigla_norm = normalizar(sigla_encontrada)
                    
                    # Busca a linha do preço pela sigla normalizada
                    linha_preco = df_tab[df_tab['SIGLA_CHAVE'] == sigla_norm].iloc[0]
                    
                    f_peso = 0.0; u_max = 0; u_col = ""; d = False
                    for f in mapa['faixas']:
                        u_max, u_col = f['max'], f['col']
                        if peso_nf <= f['max'] and f['col'] != "Não mapear":
                            f_peso = float(linha_preco[f['col']]); d = True; break
                    if not d and mapa.get('kg_extra') != "Não mapear":
                        f_peso = float(linha_preco[u_col]) + ((peso_nf - u_max) * float(linha_preco[mapa['kg_extra']]))
                    
                    def gv(n): return float(linha_preco[mapa['taxas'][n]]) if n in mapa['taxas'] and mapa['taxas'][n] != "Não mapear" else 0.0
                    total = f_peso + max(valor_nf * gv("Ad Valorem %"), gv("Ad Valorem Min")) + max(valor_nf * gv("Gris %"), gv("Gris Min")) + (math.ceil(peso_nf/100)*gv("Pedagio")) + gv("TAS") + gv("CTRC") + gv("TRT") + gv("TDA") + gv("SEC-CAT")
                    nf['VALOR_SISTEMA'] = total
                    nf['MEMORIA_CALCULO'] = f"Sigla: {sigla_encontrada} | Frete Peso: {f_peso:.2f}"
                except Exception as e:
                    nf['VALOR_SISTEMA'] = 0.0; nf['MEMORIA_CALCULO'] = "Erro: Cidade ou Sigla não mapeada na Tabela de Preços."
                res.append(nf.to_dict())

            df_res = pd.DataFrame(res)
            st.dataframe(df_res, use_container_width=True)
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer: df_res.to_excel(writer, index=False)
            st.download_button("📥 Baixar Resultados", out.getvalue(), "resultado.xlsx")
