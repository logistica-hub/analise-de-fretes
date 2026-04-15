import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math

# 1. Layout e CSS
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide")

st.markdown("""
    <style>
    .block-container { padding-top: 0.5rem; }
    [data-testid="stMetric"] { background-color: #FFFFFF !important; border: 1px solid #D1D1D1; padding: 15px; border-radius: 10px; }
    [data-testid="stMetricLabel"] p { color: #000000 !important; font-weight: bold !important; }
    [data-testid="stMetricValue"] div { color: #1E88E5 !important; }
    [data-testid="stSidebar"] { background-color: #F8F9FA !important; }
    [data-testid="stSidebar"] * { color: #000000 !important; font-weight: 600; }
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
        if up: 
            st.session_state.logo_data = up.read()
            st.rerun()
    st.divider()
    menu = st.radio("NAVEGAÇÃO", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])

# --- DASHBOARD DINÂMICO ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        resumos_all = []
        for _, row in df_h.iterrows():
            items = json.loads(row['estado_resumo'])
            resumos_all.extend(items)
        df_base_filtros = pd.DataFrame(resumos_all)

        st.markdown("### 🔍 Filtros do BI")
        f1, f2 = st.columns(2)
        filtro_t = f1.multiselect("Filtrar Transportadora", df_h['transportadora'].unique())
        filtro_uf = f2.multiselect("Filtrar Estado (UF)", sorted(df_base_filtros['UF'].unique()))
        
        df_final_bi = df_base_filtros.copy()
        if filtro_t: df_final_bi = df_final_bi[df_final_bi['Transportadora'].isin(filtro_t)]
        if filtro_uf: df_final_bi = df_final_bi[df_final_bi['UF'].isin(filtro_uf)]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_final_bi['Valor'].sum():,.2f}")
        # Quantidade real baseada na soma da coluna 'qtd' filtrada (ou contagem de linhas do detalhe)
        c2.metric("Notas Processadas", f"{len(df_final_bi)}") 
        c3.metric("Ticket Médio", f"R$ {df_final_bi['Valor'].mean():,.2f}" if not df_final_bi.empty else "R$ 0.00")

        st.subheader("📋 Consolidado por UF")
        if not df_final_bi.empty:
            st.dataframe(df_final_bi.pivot_table(index="UF", columns="Transportadora", values="Valor", aggfunc="sum").fillna(0), use_container_width=True)

# --- TRANSPORTADORAS ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    
    # Lógica de Edição
    if 'edit_id' not in st.session_state: st.session_state.edit_id = None
    
    with st.expander("📝 Configurar Tabela JAMEF", expanded=st.session_state.edit_id is not None):
        edit_data = None
        if st.session_state.edit_id:
            conn = sqlite3.connect(DB_NAME)
            edit_data = pd.read_sql_query(f"SELECT * FROM transportadoras WHERE id={st.session_state.edit_id}", conn).iloc[0]
            conn.close()
            mapa_edit = json.loads(edit_data['mapeamento_json'])

        t_nome = st.text_input("Nome da Empresa", value=edit_data['nome'] if edit_data is not None else "").upper()
        u1, u2 = st.columns(2)
        with u1: f_tab = st.file_uploader("Excel Tabela", type=["xlsx"])
        with u2: f_cid = st.file_uploader("Excel Cidades", type=["xlsx"])
        
        if f_tab:
            df_t = pd.read_excel(f_tab).fillna(0)
            cols_t = ["Não mapear"] + list(df_t.columns)
            
            st.markdown("### ⚖️ Faixas de Peso")
            sel_kg = mapa_edit['kg_extra'] if edit_data and mapa_edit['kg_extra'] in cols_t else cols_t[0]
            col_kg_extra = st.selectbox("Coluna Kg Adicional (Excedente)", cols_t, index=cols_t.index(sel_kg))
            
            n_f_val = len(mapa_edit['faixas']) if edit_data else 6
            n_f = st.number_input("Qtd Faixas", 1, 50, n_f_val)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3)
                v_mi = mapa_edit['faixas'][i]['min'] if edit_data and i < len(mapa_edit['faixas']) else 0.0
                v_ma = mapa_edit['faixas'][i]['max'] if edit_data and i < len(mapa_edit['faixas']) else 0.0
                v_co = mapa_edit['faixas'][i]['col'] if edit_data and i < len(mapa_edit['faixas']) else cols_t[0]
                
                faixas.append({
                    "min": r[0].number_input(f"De (kg)", value=float(v_mi), key=f"mi{i}"),
                    "max": r[1].number_input(f"Até (kg)", value=float(v_ma), key=f"ma{i}"),
                    "col": r[2].selectbox(f"Coluna Tabela", cols_t, index=cols_t.index(v_co) if v_co in cols_t else 0, key=f"co{i}")
                })
            
            st.markdown("### 💰 Taxas Adicionais")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}
            t_cols = st.columns(3) # Volta para o layout original lado a lado
            for idx, tx in enumerate(taxas_nomes):
                with t_cols[idx % 3]:
                    v_tax = mapa_edit['taxas'][tx] if edit_data and tx in mapa_edit['taxas'] else cols_t[0]
                    m_taxas[tx] = st.selectbox(tx, cols_t, index=cols_t.index(v_tax) if v_tax in cols_t else 0, key=f"tx_{tx}")

            if st.button("💾 Salvar Configuração"):
                mapa = {"faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_extra}
                conn = sqlite3.connect(DB_NAME)
                if st.session_state.edit_id:
                    conn.execute("UPDATE transportadoras SET nome=?, tabela_json=?, cidades_json=?, mapeamento_json=? WHERE id=?",
                                 (t_nome, df_t.to_json(), pd.read_excel(f_cid).to_json(), json.dumps(mapa), st.session_state.edit_id))
                else:
                    conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                                 (t_nome, df_t.to_json(), pd.read_excel(f_cid).to_json(), json.dumps(mapa)))
                conn.commit(); conn.close()
                st.session_state.edit_id = None
                st.rerun()

    st.markdown("### 📋 Transportadoras Cadastradas")
    conn = sqlite3.connect(DB_NAME)
    ts = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    for _, row in ts.iterrows():
        c1, c2, c3 = st.columns([7, 1.5, 1.5])
        c1.write(f"**{row['nome']}**")
        if c2.button("✏️ Editar", key=f"ed_t_{row['id']}"):
            st.session_state.edit_id = row['id']
            st.rerun()
        if c3.button("🗑️ Excluir", key=f"del_t_{row['id']}"):
            conn.execute("DELETE FROM transportadoras WHERE id=?", (row['id'],))
            conn.commit(); conn.close(); st.rerun()
    conn.close()

# --- COMPARATIVO (MANTIDO CONFORME PEDIDO) ---
elif menu == "💰 Comparativo":
    st.title("💰 Novo Comparativo")
    f_base = st.file_uploader("📥 Subir Planilha de Notas", type=["xlsx"])
    
    conn = sqlite3.connect(DB_NAME)
    ts = pd.read_sql_query("SELECT * FROM transportadoras", conn)
    
    if not ts.empty:
        t_alvo = st.selectbox("Transportadora", ts['nome'].tolist())
        if f_base and st.button("🚀 Calcular Cotação"):
            df_b = pd.read_excel(f_base).fillna(0)
            t_row = ts[ts['nome'] == t_alvo].iloc[0]
            df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
            df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
            mapa = json.loads(t_row['mapeamento_json'])
            
            res_final = []; resumo_uf = {}
            for _, nf in df_b.iterrows():
                try:
                    cidade_nf = str(nf.iloc[2]).upper().strip()
                    peso_nf = float(nf.iloc[6]); valor_nf = float(nf.iloc[7])
                    sigla = df_cid_ref[df_cid_ref.iloc[:,0].astype(str).str.upper() == cidade_nf].iloc[0, 2]
                    precos = df_tab[df_tab.iloc[:,2] == sigla].iloc[0]
                    
                    f_peso = 0.0; u_max = 0; u_col = ""; d = False
                    for f in mapa['faixas']:
                        u_max, u_col = f['max'], f['col']
                        if peso_nf <= f['max'] and f['col'] != "Não mapear":
                            f_peso = float(precos[f['col']]); d = True; break
                    if not d and mapa.get('kg_extra') != "Não mapear":
                        f_peso = float(precos[u_col]) + ((peso_nf - u_max) * float(precos[mapa['kg_extra']]))
                    
                    def gv(n): return float(precos[mapa['taxas'][n]]) if n in mapa['taxas'] and mapa['taxas'][n] != "Não mapear" else 0.0
                    
                    v_adv = max(valor_nf * (gv("Ad Valorem %")), gv("Ad Valorem Min"))
                    v_gris = max(valor_nf * (gv("Gris %")), gv("Gris Min"))
                    v_emex = max(valor_nf * (gv("Emex %")), gv("Emex Min"))
                    v_pedagio = math.ceil(peso_nf / 100) * gv("Pedagio")
                    v_fixas = gv("TAS") + gv("CTRC") + gv("TRT") + gv("TDA") + gv("SEC-CAT")
                    
                    nf['VALOR_SISTEMA'] = f_peso + v_adv + v_gris + v_emex + v_pedagio + v_fixas
                    nf['MEMORIA_CALCULO'] = f"Frete Peso: {f_peso:.2f} | AdVal: {v_adv:.2f} | Gris: {v_gris:.2f} | Pedágio: {v_pedagio:.2f} | Taxas Fixas: {v_fixas:.2f}"
                except: nf['VALOR_SISTEMA'] = 0.0; nf['MEMORIA_CALCULO'] = "Erro"
                res_final.append(nf.to_dict()); uf = nf.iloc[3]
                resumo_uf[uf] = resumo_uf.get(uf, 0) + nf['VALOR_SISTEMA']
            
            df_res = pd.DataFrame(res_final)
            res_j = [{"UF": k, "Transportadora": t_alvo, "Valor": v} for k, v in resumo_uf.items()]
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json, estado_resumo) VALUES (?,?,?,?,?,?)",
                         (datetime.now().strftime("%d/%m %H:%M"), t_alvo, df_res['VALOR_SISTEMA'].sum(), len(df_res), df_res.to_json(), json.dumps(res_j)))
            conn.commit(); st.success("Cálculo Finalizado!"); st.dataframe(df_res)

    st.markdown("### 📄 Histórico de Cotações")
    df_h = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    for _, row in df_h.iterrows():
        with st.expander(f"🔽 {row['data_hora']} - {row['transportadora']} | Notas: {row['qtd']} | R$ {row['total']:,.2f}"):
            c_h = st.columns([8, 2])
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as wr: df_det.to_excel(wr, index=False)
            c_h[0].download_button("📥 Baixar Excel", out.getvalue(), f"cot_{row['id']}.xlsx", key=f"dl_{row['id']}")
            if c_h[1].button("🗑️ Excluir", key=f"del_c_{row['id']}"):
                conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],))
                conn.commit(); conn.close(); st.rerun()
            
            st.divider()
            for idx, n_row in df_det.iterrows():
                cn1, cn2, cn3 = st.columns([5, 2, 3])
                cn1.write(f"📄 NF: {n_row.iloc[0]} - {n_row.iloc[2]}")
                cn2.write(f"**R$ {n_row['VALOR_SISTEMA']:,.2f}**")
                if cn3.button("👁️", key=f"vw_{row['id']}_{idx}"):
                    st.info(n_row.get('MEMORIA_CALCULO', 'Sem dados'))
    conn.close()
