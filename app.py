import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math

st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")

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

if 'view_details' not in st.session_state: st.session_state.view_details = {}
if 'edit_id' not in st.session_state: st.session_state.edit_id = None

with st.sidebar:
    st.title("🚀 Ave-Maria Fretes")
    menu = st.radio("MENU PRINCIPAL", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])

# --- DASHBOARD (Mantido conforme original) ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME); df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn); conn.close()
    if not df_h.empty:
        todas_notas = []
        for _, row in df_h.iterrows():
            notas_lote = pd.read_json(io.StringIO(row['detalhes_json']))
            notas_lote['Transportadora_Ref'] = row['transportadora']
            if 'UF' not in notas_lote.columns: notas_lote['UF'] = notas_lote.iloc[:, 3]
            todas_notas.append(notas_lote)
        df_bi = pd.concat(todas_notas, ignore_index=True)
        c1, c2 = st.columns(2)
        filtro_t = c1.multiselect("Transportadora", df_bi['Transportadora_Ref'].unique())
        filtro_uf = c2.multiselect("Estado (UF)", sorted(df_bi['UF'].unique()))
        df_filtrado = df_bi.copy()
        if filtro_t: df_filtrado = df_filtrado[df_filtrado['Transportadora_Ref'].isin(filtro_t)]
        if filtro_uf: df_filtrado = df_filtrado[df_filtrado['UF'].isin(filtro_uf)]
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_filtrado['VALOR_SISTEMA'].sum():,.2f}")
        c2.metric("Notas Processadas", f"{len(df_filtrado)}")
        c3.metric("Ticket Médio", f"R$ {df_filtrado['VALOR_SISTEMA'].mean():,.2f}" if len(df_filtrado)>0 else "0")
        st.dataframe(df_filtrado.pivot_table(index="UF", columns="Transportadora_Ref", values="VALOR_SISTEMA", aggfunc="sum").fillna(0), use_container_width=True)

# --- TRANSPORTADORAS (Com Novo Mapeamento) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    is_editing = st.session_state.edit_id is not None
    with st.expander("📝 Configurar Mapeamento", expanded=is_editing):
        edit_data = None
        mapa_previo = {"faixas": [], "taxas": {}, "kg_extra": "Não mapear", "col_cidade_origem": "Não mapear", "col_sigla_alvo": "Não mapear"}
        if is_editing:
            conn = sqlite3.connect(DB_NAME); edit_data = pd.read_sql_query(f"SELECT * FROM transportadoras WHERE id={st.session_state.edit_id}", conn).iloc[0]; conn.close()
            mapa_previo = json.loads(edit_data['mapeamento_json'])
        t_nome = st.text_input("Nome", value=edit_data['nome'] if is_editing else "").upper()
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("Tabela Preços (Excel)", type=["xlsx"])
        f_cid = c2.file_uploader("Cidades/Siglas (Excel)", type=["xlsx"])
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.read_json(io.StringIO(edit_data['tabela_json'])) if is_editing else None)
        df_c = pd.read_excel(f_cid).fillna(0) if f_cid else (pd.read_json(io.StringIO(edit_data['cidades_json'])) if is_editing else None)
        
        if df_t is not None and df_c is not None:
            st.subheader("📍 Mapeamento Geográfico")
            cols_c = ["Não mapear"] + [str(c) for c in df_c.columns]
            col_cid = st.selectbox("Qual coluna da planilha de cidades contém o nome da CIDADE?", cols_c, index=cols_c.index(mapa_previo.get('col_cidade_origem', "Não mapear")) if mapa_previo.get('col_cidade_origem') in cols_c else 0)
            col_sig = st.selectbox("Qual coluna da planilha de cidades contém a SIGLA/REGIÃO?", cols_c, index=cols_c.index(mapa_previo.get('col_sigla_alvo', "Não mapear")) if mapa_previo.get('col_sigla_alvo') in cols_c else 0)
            
            st.subheader("⚖️ Pesos e Taxas")
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            col_extra = st.selectbox("Coluna Kg Adicional", cols_t, index=cols_t.index(mapa_previo.get('kg_extra', "Não mapear")) if mapa_previo.get('kg_extra') in cols_t else 0)
            n_f = st.number_input("Qtd Faixas", 1, 50, len(mapa_previo['faixas']) if is_editing else 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3)
                f_i = mapa_previo['faixas'][i] if is_editing and i < len(mapa_previo['faixas']) else {}
                faixas.append({"min": r[0].number_input(f"De", value=float(f_i.get('min',0.0)), key=f"mi{i}"), "max": r[1].number_input(f"Até", value=float(f_i.get('max',0.0)), key=f"ma{i}"), "col": r[2].selectbox(f"Coluna", cols_t, index=cols_t.index(str(f_i.get('col',"Não mapear"))) if str(f_i.get('col')) in cols_t else 0, key=f"co{i}")})
            taxas_n = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_n):
                s_tx = str(mapa_previo.get('taxas', {}).get(tx, "Não mapear"))
                m_taxas[tx] = tx_cols[idx%3].selectbox(tx, cols_t, index=cols_t.index(s_tx) if s_tx in cols_t else 0, key=f"tx_{tx}")
            if st.button("💾 Salvar"):
                mapa = {"faixas": faixas, "taxas": m_taxas, "kg_extra": col_extra, "col_cidade_origem": col_cid, "col_sigla_alvo": col_sig}
                conn = sqlite3.connect(DB_NAME); conn.execute("UPDATE transportadoras SET nome=?, tabela_json=?, cidades_json=?, mapeamento_json=? WHERE id=?" if is_editing else "INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)", (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa), st.session_state.edit_id) if is_editing else (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa))); conn.commit(); conn.close(); st.session_state.edit_id = None; st.rerun()

    conn = sqlite3.connect(DB_NAME); ts = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn); conn.close()
    for _, r in ts.iterrows():
        c1, c2, c3 = st.columns([7, 1.5, 1.5])
        c1.write(f"**{r['nome']}**")
        if c2.button("✏️", key=f"e{r['id']}"): st.session_state.edit_id=r['id']; st.rerun()
        if c3.button("🗑️", key=f"d{r['id']}"): conn=sqlite3.connect(DB_NAME); conn.execute("DELETE FROM transportadoras WHERE id=?",(r['id'],)); conn.commit(); conn.close(); st.rerun()

# --- COMPARATIVO (Otimizado) ---
elif menu == "💰 Comparativo":
    st.title("💰 Novo Cálculo de Frete")
    f_base = st.file_uploader("📥 Planilha de Notas", type=["xlsx"])
    conn = sqlite3.connect(DB_NAME); ts = pd.read_sql_query("SELECT * FROM transportadoras", conn); conn.close()
    if not ts.empty:
        t_alvo = st.selectbox("Transportadora", ts['nome'].tolist())
        if f_base and st.button("🚀 Calcular"):
            df_b = pd.read_excel(f_base).fillna(0); t_row = ts[ts['nome'] == t_alvo].iloc[0]
            df_tab = pd.read_json(io.StringIO(t_row['tabela_json'])); df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json'])); mapa = json.loads(t_row['mapeamento_json'])
            
            c_nf = df_b.columns[2]; c_p = df_b.columns[6]; c_v = df_b.columns[7]
            df_b['BUSCA'] = df_b[c_nf].astype(str).str.upper().str.strip()
            
            # Mapeamento dinâmico baseado na escolha do usuário
            col_ref_cidade = mapa.get('col_cidade_origem')
            col_ref_sigla = mapa.get('col_sigla_alvo')
            
            if col_ref_cidade == "Não mapear" or col_ref_sigla == "Não mapear":
                st.error("Configure o mapeamento de cidades na aba Transportadoras!"); st.stop()

            df_cid_ref['BUSCA_REF'] = df_cid_ref[col_ref_cidade].astype(str).str.upper().str.strip()
            df_proc = pd.merge(df_b, df_cid_ref[['BUSCA_REF', col_ref_sigla]], left_on='BUSCA', right_on='BUSCA_REF', how='left')
            
            res = []
            for _, nf in df_proc.iterrows():
                try:
                    p_nf = float(nf[c_p]); v_nf = float(nf[c_v]); sigla = str(nf[col_ref_sigla])
                    precos = df_tab[df_tab.iloc[:,2].astype(str).str.upper().str.strip() == sigla.upper().strip()].iloc[0]
                    f_p = 0.0; u_m = 0; u_c = ""; d = False
                    for f in mapa['faixas']:
                        u_m, u_c = f['max'], f['col']
                        if p_nf <= f['max'] and f['col'] != "Não mapear": f_p = float(precos[f['col']]); d = True; break
                    if not d and mapa['kg_extra'] != "Não mapear": f_p = float(precos[u_c]) + ((p_nf - u_m) * float(precos[mapa['kg_extra']]))
                    def gv(n): return float(precos[mapa['taxas'][n]]) if n in mapa['taxas'] and mapa['taxas'][n] != "Não mapear" else 0.0
                    v_adv = max(v_nf * gv("Ad Valorem %"), gv("Ad Valorem Min"))
                    v_gr = max(v_nf * gv("Gris %"), gv("Gris Min"))
                    v_ex = max(v_nf * gv("Emex %"), gv("Emex Min"))
                    v_pe = math.ceil(p_nf / 100) * gv("Pedagio")
                    tot = f_p + v_adv + v_gr + v_ex + v_pe + gv("TAS") + gv("CTRC") + gv("TRT") + gv("TDA") + gv("SEC-CAT")
                    nf['VALOR_SISTEMA'] = tot
                    nf['MEMORIA_CALCULO'] = f"Frete Peso: {f_p:.2f} | AdV: {v_adv:.2f} | Gris: {v_gr:.2f} | Ped: {v_pe:.2f}"
                except: nf['VALOR_SISTEMA'] = 0.0; nf['MEMORIA_CALCULO'] = "Erro no mapeamento"
                res.append(nf.to_dict())
            
            df_res = pd.DataFrame(res)
            st.success(f"✅ {len(df_res)} Notas Processadas"); st.dataframe(df_res, use_container_width=True)
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as wr: df_res.to_excel(wr, index=False)
            st.download_button("📥 Baixar Excel", out.getvalue(), "resultado.xlsx")
