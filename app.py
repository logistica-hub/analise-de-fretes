import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math

# CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")

# CSS PARA MELHORAR O VISUAL (BI SEM TRANSPARÊNCIA)
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
    [data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #D1D1D1;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    [data-testid="stMetricLabel"] p { color: #333333 !important; font-weight: bold !important; }
    [data-testid="stMetricValue"] div { color: #1E88E5 !important; }
    [data-testid="stSidebar"] { background-color: #F8F9FA !important; border-right: 1px solid #E0E0E0; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'comparativo_v25.db'

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
    menu = st.radio("MENU PRINCIPAL", ["📊 Dashboard BI", "🚛 Transportadoras", "💰 Comparativo"])

# --- DASHBOARD BI (COM FILTROS DE UF E TRANSPORTADORA) ---
if menu == "📊 Dashboard BI":
    st.title("📊 Painel de Indicadores (BI)")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        resumos_base = []
        for r in df_h['estado_resumo']: resumos_base.extend(json.loads(r))
        df_base_filtros = pd.DataFrame(resumos_base)

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            filtro_t = st.multiselect("Filtrar Transportadora", df_h['transportadora'].unique())
        with col_f2:
            filtro_uf = st.multiselect("Filtrar Estado (UF)", sorted(df_base_filtros['UF'].unique()))
        
        df_final_bi = df_base_filtros.copy()
        if filtro_t:
            df_final_bi = df_final_bi[df_final_bi['Transportadora'].isin(filtro_t)]
        if filtro_uf:
            df_final_bi = df_final_bi[df_final_bi['UF'].isin(filtro_uf)]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_final_bi['Valor'].sum():,.2f}")
        c2.metric("Notas Processadas", f"{len(df_final_bi)}")
        c3.metric("Ticket Médio", f"R$ {df_final_bi['Valor'].mean():,.2f}" if not df_final_bi.empty else "0.00")

        st.subheader("📋 Resumo Consolidado por Estado")
        if not df_final_bi.empty:
            pivot = df_final_bi.pivot_table(index="UF", columns="Transportadora", values="Valor", aggfunc="sum").fillna(0)
            st.dataframe(pivot, use_container_width=True)
    else:
        st.info("Nenhuma cotação realizada ainda.")

# --- TRANSPORTADORAS ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    with st.expander("📝 Configurar Nova Tabela (Jamef/Padrão)"):
        t_nome = st.text_input("Nome da Transportadora").upper()
        u1, u2 = st.columns(2)
        with u1: f_tab = st.file_uploader("Excel Tabela Frete", type=["xlsx"])
        with u2: f_cid = st.file_uploader("Excel Cidades/Siglas", type=["xlsx"])
        
        if f_tab:
            df_t = pd.read_excel(f_tab).fillna(0)
            cols_t = ["Não mapear"] + list(df_t.columns)
            
            st.markdown("### ⚖️ Faixas de Peso")
            col_kg_extra = st.selectbox("Coluna Kg Adicional (Excedente)", cols_t)
            n_f = st.number_input("Qtd Faixas de Peso", 1, 50, 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3)
                faixas.append({"min": r[0].number_input(f"De (kg)", key=f"mi{i}"),
                               "max": r[1].number_input(f"Até (kg)", key=f"ma{i}"),
                               "col": r[2].selectbox(f"Coluna na Tabela", cols_t, key=f"co{i}")})
            
            st.markdown("### 💰 Taxas e Impostos")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}
            t_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                with t_cols[idx % 3]:
                    m_taxas[tx] = st.selectbox(tx, cols_t, key=f"tx_{tx}")

            if st.button("💾 Salvar Configuração"):
                mapa = {"faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_extra}
                conn = sqlite3.connect(DB_NAME)
                conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                             (t_nome, df_t.to_json(), pd.read_excel(f_cid).to_json(), json.dumps(mapa)))
                conn.commit(); conn.close(); st.success("Salvo!"); st.rerun()

    st.markdown("### 📋 Transportadoras Ativas")
    conn = sqlite3.connect(DB_NAME)
    ts = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    for _, row in ts.iterrows():
        c1, c2 = st.columns([8, 2])
        c1.write(f"🏢 **{row['nome']}**")
        if c2.button("🗑️ Excluir", key=f"del_t_{row['id']}"):
            conn.execute("DELETE FROM transportadoras WHERE id=?", (row['id'],))
            conn.commit(); conn.close(); st.rerun()
    conn.close()

# --- COMPARATIVO ---
elif menu == "💰 Comparativo":
    st.title("💰 Simulação de Frete")
    f_base = st.file_uploader("📥 Subir Planilha de Notas (Base)", type=["xlsx"])
    
    conn = sqlite3.connect(DB_NAME)
    ts = pd.read_sql_query("SELECT * FROM transportadoras", conn)
    
    if not ts.empty:
        t_alvo = st.selectbox("Selecione a Transportadora", ts['nome'].tolist())
        if f_base and st.button("🚀 Iniciar Cálculo"):
            df_b = pd.read_excel(f_base).fillna(0)
            t_row = ts[ts['nome'] == t_alvo].iloc[0]
            df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
            df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
            mapa = json.loads(t_row['mapeamento_json'])
            
            res_final = []
            resumo_uf = {}
            
            for _, nf in df_b.iterrows():
                try:
                    # Dados da NF
                    cidade_nf = str(nf.iloc[2]).upper().strip()
                    peso_nf = float(nf.iloc[6])
                    valor_nf = float(nf.iloc[7])
                    uf_nf = str(nf.iloc[3]).upper().strip()

                    # Busca Sigla
                    sigla = df_cid_ref[df_cid_ref.iloc[:,0].astype(str).str.upper() == cidade_nf].iloc[0, 2]
                    precos = df_tab[df_tab.iloc[:,2] == sigla].iloc[0]
                    
                    # 1. Frete Peso (Base)
                    f_base_v = 0.0
                    u_max = 0; u_col = ""; dentro = False
                    for f in mapa['faixas']:
                        u_max = f['max']; u_col = f['col']
                        if peso_nf <= f['max'] and f['col'] != "Não mapear":
                            f_base_v = float(precos[f['col']]); dentro = True; break
                    
                    if not dentro and mapa.get('kg_extra') != "Não mapear":
                        f_base_v = float(precos[u_col]) + ((peso_nf - u_max) * float(precos[mapa['kg_extra']]))
                    
                    # Função auxiliar para pegar valor das colunas mapeadas
                    def get_v(n): 
                        col = mapa['taxas'].get(n, "Não mapear")
                        return float(precos[col]) if col != "Não mapear" else 0.0

                    # 2. Cálculo das Taxas Variáveis (Regra Jamef)
                    v_adv = max(valor_nf * (get_v("Ad Valorem %") / 100), get_v("Ad Valorem Min"))
                    v_gris = max(valor_nf * (get_v("Gris %") / 100), get_v("Gris Min"))
                    v_emex = max(valor_nf * (get_v("Emex %") / 100), get_v("Emex Min"))
                    v_pedagio = math.ceil(peso_nf / 100) * get_v("Pedagio") # Fração de 100kg sempre arredonda p/ cima

                    # 3. Cálculo das Taxas Fixas
                    v_fixas = get_v("TAS") + get_v("CTRC") + get_v("TRT") + get_v("TDA") + get_v("SEC-CAT")

                    # Soma Final
                    nf['VALOR_SISTEMA'] = f_base_v + v_adv + v_gris + v_emex + v_pedagio + v_fixas
                except Exception as e:
                    nf['VALOR_SISTEMA'] = 0.0
                
                res_final.append(nf.to_dict())
                resumo_uf[uf_nf] = resumo_uf.get(uf_nf, 0) + nf['VALOR_SISTEMA']
            
            df_res = pd.DataFrame(res_final)
            res_json = [{"UF": k, "Transportadora": t_alvo, "Valor": v} for k, v in resumo_uf.items()]
            
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json, estado_resumo) VALUES (?,?,?,?,?,?)",
                         (datetime.now().strftime("%d/%m %H:%M"), t_alvo, df_res['VALOR_SISTEMA'].sum(), len(df_res), df_res.to_json(), json.dumps(res_json)))
            conn.commit(); st.success("Cálculo Finalizado!"); st.dataframe(df_res)

    st.markdown("### 📄 Histórico de Cotações")
    df_h = pd.read_sql_query("SELECT id, data_hora, transportadora, total, qtd FROM cotacoes ORDER BY id DESC", conn)
    for _, row in df_h.iterrows():
        c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
        c1.write(f"📅 {row['data_hora']} - **{row['transportadora']}**")
        c2.write(f"📦 Notas: **{row['qtd']}**")
        c3.write(f"💰 **R$ {row['total']:,.2f}**")
        
        btn_c = c4.columns(2)
        # Download
        det = pd.read_sql_query(f"SELECT detalhes_json FROM cotacoes WHERE id={row['id']}", conn).iloc[0]['detalhes_json']
        df_dl = pd.read_json(io.StringIO(det))
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as wr: df_dl.to_excel(wr, index=False)
        btn_c[0].download_button("📂 Exportar", out.getvalue(), f"frete_{row['id']}.xlsx", key=f"dl_{row['id']}")
        # Excluir
        if btn_c[1].button("🗑️ Excluir", key=f"del_c_{row['id']}"):
            conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],))
            conn.commit(); conn.close(); st.rerun()
    conn.close()
