import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math

# 1. Configuração de Estilo (BI Nítido)
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #D1D1D1;
        padding: 15px;
        border-radius: 10px;
    }
    [data-testid="stMetricLabel"] p {
        color: #000000 !important;
        font-weight: bold !important;
        opacity: 1 !important;
    }
    [data-testid="stMetricValue"] div {
        color: #1E88E5 !important;
    }
    [data-testid="stSidebar"] { background-color: #F8F9FA !important; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'comparativo_v20.db'

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

# --- SIDEBAR (Logo e Navegação) ---
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
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_full['Valor'].sum():,.2f}")
        c2.metric("Notas Processadas", f"{int(df_h['qtd'].sum())}")
        c3.metric("Ticket Médio", f"R$ {df_full['Valor'].mean():,.2f}")
        st.dataframe(df_full.pivot_table(index="UF", columns="Transportadora", values="Valor", aggfunc="sum").fillna(0), use_container_width=True)

# --- TRANSPORTADORAS (MAPEAMENTO COMPLETO REESTABELECIDO) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    with st.expander("📝 Configurar Tabela de Frete", expanded=True):
        t_nome = st.text_input("Nome da Empresa").upper()
        u1, u2 = st.columns(2)
        with u1: f_tab = st.file_uploader("Excel Tabela", type=["xlsx"])
        with u2: f_cid = st.file_uploader("Excel Cidades", type=["xlsx"])
        
        if f_tab:
            df_t = pd.read_excel(f_tab).fillna(0)
            cols_t = ["Não mapear"] + list(df_t.columns)
            
            st.markdown("### ⚖️ Faixas de Peso e Kg Adicional")
            col_adicional = st.selectbox("Coluna Kg Adicional (Excedente)", cols_t)
            n_f = st.number_input("Quantidade de Faixas", 1, 50, 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3)
                mi = r[0].number_input(f"De (kg)", key=f"mi{i}")
                ma = r[1].number_input(f"Até (kg)", key=f"ma{i}")
                co = r[2].selectbox(f"Coluna Tabela", cols_t, key=f"co{i}")
                faixas.append({"min": mi, "max": ma, "col": co})
            
            st.markdown("### 💰 Taxas e Pedágio")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min"]
            m_taxas = {}
            t_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                with t_cols[idx % 3]:
                    m_taxas[tx] = st.selectbox(tx, cols_t, key=f"tx_{tx}")

            if st.button("💾 Salvar Transportadora"):
                mapa = {"faixas": faixas, "taxas": m_taxas, "kg_extra": col_adicional}
                conn = sqlite3.connect(DB_NAME)
                conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                             (t_nome, df_t.to_json(), pd.read_excel(f_cid).to_json(), json.dumps(mapa)))
                conn.commit(); st.success("Salvo!"); st.rerun()

# --- COMPARATIVO (CÁLCULO JAMEF COM KG ADICIONAL E PEDÁGIO FRACIONADO) ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo de Fretes")
    f_base = st.file_uploader("📥 Subir Planilha Base", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        conn = sqlite3.connect(DB_NAME); ts = pd.read_sql_query("SELECT * FROM transportadoras", conn); conn.close()
        
        if not ts.empty:
            t_alvo = st.selectbox("Selecione a Transportadora", ts['nome'].tolist())
            if st.button("🚀 Calcular"):
                t_row = ts[ts['nome'] == t_alvo].iloc[0]
                df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
                df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
                mapa = json.loads(t_row['mapeamento_json'])
                
                res_final = []
                resumo_uf = {}

                for _, nf in df_b.iterrows():
                    try:
                        cidade_nf = str(nf.iloc[2]).upper().strip()
                        peso_nf = float(nf.iloc[6])
                        valor_nf = float(nf.iloc[7])
                        
                        sigla = df_cid_ref[df_cid_ref.iloc[:,0].astype(str).str.upper() == cidade_nf].iloc[0, 2]
                        precos = df_tab[df_tab.iloc[:,2] == sigla].iloc[0]
                        
                        # 1. Frete Peso + Kg Adicional
                        f_peso = 0.0
                        max_faixa = 0
                        col_max = ""
                        for f in mapa['faixas']:
                            max_faixa = f['max']
                            col_max = f['col']
                            if peso_nf <= f['max'] and f['col'] != "Não mapear":
                                f_peso = float(precos[f['col']]); break
                        
                        if peso_nf > max_faixa and mapa.get('kg_extra') != "Não mapear":
                            f_peso = float(precos[col_max]) + ((peso_nf - max_faixa) * float(precos[mapa['kg_extra']]))
                        
                        # 2. Taxas
                        def g(n): return float(precos[mapa['taxas'][n]]) if mapa['taxas'][n] != "Não mapear" else 0.0
                        
                        v_adv = max(valor_nf * (g("Ad Valorem %")/100), g("Ad Valorem Min"))
                        v_emex = max(valor_nf * (g("Emex %")/100), g("Emex Min"))
                        v_tas, v_ctrc = g("TAS"), g("CTRC")
                        
                        # Pedágio (fração de 100kg)
                        v_pedagio = math.ceil(peso_nf / 100) * g("Pedagio")
                        
                        # Gris (sobre o frete)
                        subtotal = f_peso + v_adv + v_tas + v_ctrc + v_pedagio
                        v_gris = max(subtotal * (g("Gris %")/100), g("Gris Min"))
                        
                        nf['VALOR_SISTEMA'] = subtotal + v_gris + v_emex
                    except: nf['VALOR_SISTEMA'] = 0.0
                    
                    res_final.append(nf.to_dict())
                    resumo_uf[nf.iloc[3]] = resumo_uf.get(nf.iloc[3], 0) + nf['VALOR_SISTEMA']

                st.success("Calculado!"); st.dataframe(pd.DataFrame(res_final))
