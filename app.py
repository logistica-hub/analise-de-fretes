import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math

# 1. Configuração de Layout e Visual BI
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .block-container { padding-top: 0.5rem; padding-left: 1rem; padding-right: 1rem; max-width: 100%; }
    div[data-testid="stMetricValue"] { color: #1E88E5 !important; font-weight: bold !important; }
    .stMetric { border: 1px solid #E0E0E0; padding: 15px; border-radius: 10px; background-color: #FFFFFF; }
    [data-testid="stSidebar"] { background-color: #F8F9FA !important; }
    [data-testid="stSidebar"] * { color: #000000 !important; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'comparativo_v16.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cotacoes 
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

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        resumos = []
        for r in df_h['estado_resumo']: resumos.extend(json.loads(r))
        df_full = pd.DataFrame(resumos)
        
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_full['Valor'].sum():,.2f}")
        c2.metric("Notas Processadas", int(df_h['qtd'].sum()))
        c3.metric("Média por Estado", f"R$ {df_full['Valor'].mean():,.2f}")

        st.subheader("📋 Consolidado por UF")
        pivot = df_full.pivot_table(index="UF", columns="Transportadora", values="Valor", aggfunc="sum").fillna(0)
        st.dataframe(pivot, use_container_width=True)
    else:
        st.info("Realize uma cotação primeiro.")

# --- TRANSPORTADORAS ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    
    if 'edit_id' not in st.session_state: st.session_state.edit_id = None
    edit_nome = ""
    if st.session_state.edit_id:
        conn = sqlite3.connect(DB_NAME)
        res = conn.execute("SELECT nome FROM transportadoras WHERE id=?", (st.session_state.edit_id,)).fetchone()
        conn.close()
        if res: edit_nome = res[0]

    with st.expander("📝 Configurar Mapeamento", expanded=(st.session_state.edit_id is not None)):
        t_nome = st.text_input("Nome da Empresa", value=edit_nome).upper()
        u1, u2 = st.columns(2)
        with u1: f_tab = st.file_uploader("Excel Tabela", type=["xlsx"])
        with u2: f_cid = st.file_uploader("Excel Cidades", type=["xlsx"])
        
        if f_tab:
            df_t = pd.read_excel(f_tab).fillna(0)
            cols_t = ["Não mapear"] + list(df_t.columns)
            
            st.markdown("### ⚖️ Mapeamento de Peso (Vertical)")
            n_f = st.number_input("Qtd Faixas", 1, 50, 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns([1, 1, 2])
                mi = r[0].number_input(f"De", key=f"mi{i}")
                ma = r[1].number_input(f"Até", key=f"ma{i}")
                co = r[2].selectbox(f"Coluna", cols_t, key=f"co{i}")
                faixas.append({"min": mi, "max": ma, "col": co})
            
            st.markdown("### ➕ Kg Adicional e Pedágio")
            c_extra, c_ped = st.columns(2)
            col_kg_extra = c_extra.selectbox("Coluna Kg Adicional", cols_t)
            col_pedagio = c_ped.selectbox("Coluna Pedágio (por 100kg)", cols_t)
            
            st.markdown("### 💰 Outras Taxas")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}
            t_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                with t_cols[idx % 3]:
                    m_taxas[tx] = st.selectbox(tx, cols_t, key=f"tx_{tx}")

            if st.button("💾 Salvar"):
                mapa = {"faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_extra, "pedagio": col_pedagio}
                conn = sqlite3.connect(DB_NAME)
                if st.session_state.edit_id:
                    conn.execute("UPDATE transportadoras SET nome=?, tabela_json=?, mapeamento_json=? WHERE id=?",
                                 (t_nome, df_t.to_json(), json.dumps(mapa), st.session_state.edit_id))
                else:
                    conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                                 (t_nome, df_t.to_json(), pd.read_excel(f_cid).to_json(), json.dumps(mapa)))
                conn.commit(); conn.close()
                st.session_state.edit_id = None
                st.rerun()

    st.divider()
    conn = sqlite3.connect(DB_NAME)
    df_l = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    conn.close()
    for _, r in df_l.iterrows():
        c = st.columns([6, 2])
        c[0].write(f"🏢 **{r['nome']}**")
        if c[1].button("Remover", key=f"d_{r['id']}"):
            conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM transportadoras WHERE id=?", (r['id'],)); conn.commit(); conn.close(); st.rerun()

# --- COMPARATIVO (MOTOR DE CÁLCULO) ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo de Fretes")
    f_base = st.file_uploader("📥 Subir Planilha Base", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        st.markdown("### 🔍 Mapeamento das Notas")
        bc1, bc2, bc3, bc4 = st.columns(4)
        with bc1: b_cid = st.selectbox("Cidade", df_b.columns, index=2)
        with bc2: b_uf = st.selectbox("UF", df_b.columns, index=3)
        with bc3: b_peso = st.selectbox("Peso", df_b.columns, index=6)
        with bc4: b_val = st.selectbox("Valor NF", df_b.columns, index=7)

        conn = sqlite3.connect(DB_NAME)
        ts = pd.read_sql_query("SELECT * FROM transportadoras", conn)
        conn.close()

        if not ts.empty:
            t_alvo = st.selectbox("Transportadora", ts['nome'].tolist())
            
            if st.button("🚀 Calcular"):
                t_row = ts[ts['nome'] == t_alvo].iloc[0]
                df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
                df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
                mapa = json.loads(t_row['mapeamento_json'])
                
                res_final = []
                resumo_uf = {}

                for _, nf in df_b.iterrows():
                    v_total = 0.0
                    try:
                        cidade_nf = str(nf[b_cid]).upper().strip()
                        peso_nf = float(nf[b_peso])
                        valor_nf = float(nf[b_val])
                        
                        sigla = df_cid_ref[df_cid_ref.iloc[:,0].astype(str).str.upper() == cidade_nf].iloc[0, 2]
                        precos = df_tab[df_tab.iloc[:,2] == sigla].iloc[0]
                        
                        # 1. Frete Peso
                        f_peso = 0.0
                        max_kg = 0
                        for f in mapa['faixas']:
                            max_kg = f['max']
                            if peso_nf <= f['max'] and f['col'] != "Não mapear":
                                f_peso = float(precos[f['col']])
                                break
                        if peso_nf > max_kg and mapa['kg_extra'] != "Não mapear":
                            f_peso = float(precos[mapa['faixas'][-1]['col']]) + ((peso_nf - max_kg) * float(precos[mapa['kg_extra']]))
                        
                        # 2. REGRA DO PEDÁGIO (Cálculo por fração de 100kg)
                        f_pedagio = 0.0
                        if mapa.get("pedagio") != "Não mapear":
                            f_pedagio = math.ceil(peso_nf / 100) * float(precos[mapa['pedagio']])
                        
                        # 3. Outras Taxas
                        v_taxas = 0.0
                        for tx_n, col in mapa['taxas'].items():
                            if col != "Não mapear":
                                v_tab = float(precos[col])
                                if "%" in tx_n:
                                    v_taxas += valor_nf * (v_tab / 100)
                                else:
                                    v_taxas += v_tab
                        
                        v_total = f_peso + f_pedagio + v_taxas
                    except: v_total = 0.0
                    
                    nf['VALOR_COTADO'] = v_total
                    res_final.append(nf.to_dict())
                    uf = nf[b_uf]
                    resumo_uf[uf] = resumo_uf.get(uf, 0) + v_total

                df_res = pd.DataFrame(res_final)
                res_json = [{"UF": k, "Transportadora": t_alvo, "Valor": v} for k, v in resumo_uf.items()]
                
                conn = sqlite3.connect(DB_NAME)
                conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json, estado_resumo) VALUES (?,?,?,?,?,?)",
                             (datetime.now().strftime("%d/%m %H:%M"), t_alvo, df_res['VALOR_COTADO'].sum(), len(df_res), df_res.to_json(), json.dumps(res_json)))
                conn.commit(); conn.close(); st.rerun()

    st.divider()
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    conn.close()
    for _, row in df_h.iterrows():
        with st.expander(f"📋 {row['transportadora']} | {row['data_hora']} | R$ {row['total']:,.2f}"):
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            out = io.BytesIO()
            with pd.ExcelWriter(out) as w: df_det.to_excel(w, index=False)
            st.download_button("📥 Baixar Excel", out.getvalue(), f"cota_{row['id']}.xlsx")
