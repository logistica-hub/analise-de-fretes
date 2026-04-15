import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math

# CONFIGURAÇÃO DE LAYOUT E ESTILO BI
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide")

st.markdown("""
    <style>
    /* CSS PARA O BI - REMOVER TRANSPARÊNCIA */
    [data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #D1D1D1;
        padding: 15px;
        border-radius: 8px;
    }
    [data-testid="stMetricLabel"] p {
        color: #000000 !important; /* Títulos em Preto */
        font-weight: bold !important;
        opacity: 1 !important;
    }
    [data-testid="stMetricValue"] div {
        color: #1E88E5 !important; /* Números em Azul */
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'comparativo_v18.db'

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
    st.title("Menu")
    menu = st.radio("Navegação", ["📊 Dashboard", "🚛 Gestão de Tabelas", "💰 Novo Comparativo"])

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
        
        st.subheader("📋 Consolidado por UF")
        st.dataframe(df_full.pivot_table(index="UF", columns="Transportadora", values="Valor", aggfunc="sum").fillna(0), use_container_width=True)

# --- GESTÃO DE TABELAS ---
elif menu == "🚛 Gestão de Tabelas":
    st.title("🚛 Gestão de Transportadoras")
    with st.expander("Cadastrar Nova"):
        t_nome = st.text_input("Nome").upper()
        f_tab = st.file_uploader("Tabela", type=["xlsx"])
        f_cid = st.file_uploader("Cidades", type=["xlsx"])
        
        if f_tab:
            df_t = pd.read_excel(f_tab).fillna(0)
            cols = ["Não mapear"] + list(df_t.columns)
            
            st.write("Mapeie as taxas conforme a JAMEF:")
            col1, col2 = st.columns(2)
            m_taxas = {}
            taxas = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min"]
            for i, tx in enumerate(taxas):
                with (col1 if i % 2 == 0 else col2):
                    m_taxas[tx] = st.selectbox(tx, cols, key=f"map_{tx}")
            
            # Faixas de Peso (Simplificado para 6 faixas)
            faixas = []
            st.write("Faixas de Peso:")
            for i in range(6):
                r = st.columns(3)
                mi = r[0].number_input(f"De_{i}", key=f"mi{i}")
                ma = r[1].number_input(f"Até_{i}", key=f"ma{i}")
                co = r[2].selectbox(f"Coluna_{i}", cols, key=f"co{i}")
                faixas.append({"min": mi, "max": ma, "col": co})

            if st.button("Salvar"):
                mapa = {"faixas": faixas, "taxas": m_taxas}
                conn = sqlite3.connect(DB_NAME)
                conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                             (t_nome, df_t.to_json(), pd.read_excel(f_cid).to_json(), json.dumps(mapa)))
                conn.commit(); st.rerun()

# --- COMPARATIVO (MOTOR DE CÁLCULO CORRIGIDO) ---
elif menu == "💰 Novo Comparativo":
    st.title("💰 Comparativo de Fretes")
    f_base = st.file_uploader("Subir Planilha Base", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        conn = sqlite3.connect(DB_NAME)
        ts = pd.read_sql_query("SELECT * FROM transportadoras", conn)
        conn.close()
        
        if not ts.empty:
            t_alvo = st.selectbox("Transportadora", ts['nome'].tolist())
            if st.button("Executar Cálculo JAMEF"):
                t_row = ts[ts['nome'] == t_alvo].iloc[0]
                df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
                df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
                mapa = json.loads(t_row['mapeamento_json'])
                
                res_final = []
                resumo_uf = {}

                for _, nf in df_b.iterrows():
                    try:
                        cidade_nf = str(nf.iloc[2]).upper().strip() # Coluna 2: Cidade
                        peso_nf = float(nf.iloc[6])                # Coluna 6: Peso
                        valor_nf = float(nf.iloc[7])               # Coluna 7: Valor NF
                        
                        sigla = df_cid_ref[df_cid_ref.iloc[:,0].astype(str).str.upper() == cidade_nf].iloc[0, 2]
                        precos = df_tab[df_tab.iloc[:,2] == sigla].iloc[0]
                        
                        # 1. FRETE PESO
                        f_peso = 0.0
                        for f in mapa['faixas']:
                            if peso_nf <= f['max'] and f['col'] != "Não mapear":
                                f_peso = float(precos[f['col']])
                                break
                        
                        # 2. TAXAS SOBRE VALOR DA NF (Ad Valorem e Emex)
                        def calc_min(pct_col, min_col):
                            if mapa['taxas'][pct_col] == "Não mapear": return 0.0
                            v = valor_nf * (float(precos[mapa['taxas'][pct_col]]) / 100)
                            if mapa['taxas'][min_col] != "Não mapear":
                                v = max(v, float(precos[mapa['taxas'][min_col]]))
                            return v

                        v_advalorem = calc_min("Ad Valorem %", "Ad Valorem Min")
                        v_emex = calc_min("Emex %", "Emex Min")
                        
                        # 3. TAXAS FIXAS (TAS e CTRC)
                        v_tas = float(precos[mapa['taxas']['TAS']]) if mapa['taxas']['TAS'] != "Não mapear" else 0.0
                        v_ctrc = float(precos[mapa['taxas']['CTRC']]) if mapa['taxas']['CTRC'] != "Não mapear" else 0.0
                        
                        # 4. PEDÁGIO (A cada 100kg ou fração)
                        v_pedagio = 0.0
                        if mapa['taxas']['Pedagio'] != "Não mapear":
                            fração = math.ceil(peso_nf / 100)
                            v_pedagio = fração * float(precos[mapa['taxas']['Pedagio']])
                        
                        # 5. GRIS (CÁLCULO SOBRE O FRETE)
                        # O Gris da Jamef geralmente é sobre (Frete Peso + Ad Valorem + Taxas)
                        subtotal_para_gris = f_peso + v_advalorem + v_tas + v_ctrc + v_pedagio
                        v_gris = 0.0
                        if mapa['taxas']['Gris %'] != "Não mapear":
                            v_gris = subtotal_para_gris * (float(precos[mapa['taxas']['Gris %']]) / 100)
                            if mapa['taxas']['Gris Min'] != "Não mapear":
                                v_gris = max(v_gris, float(precos[mapa['taxas']['Gris Min']]))

                        v_total = subtotal_para_gris + v_gris + v_emex
                        nf['TOTAL_COTADO'] = round(v_total, 5)
                        
                    except:
                        nf['TOTAL_COTADO'] = 0.0
                    
                    res_final.append(nf.to_dict())
                    uf = nf.iloc[3] # Coluna 3: UF
                    resumo_uf[uf] = resumo_uf.get(uf, 0) + nf['TOTAL_COTADO']

                df_res = pd.DataFrame(res_final)
                # Salvar no Banco... (mesmo processo anterior)
                st.success("Cálculo Finalizado!"); st.dataframe(df_res)
