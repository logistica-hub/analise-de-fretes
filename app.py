import streamlit as st
import pandas as pd
import math
import sqlite3
import json
import io
from datetime import datetime

# 1. Configuração de Layout
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide", initial_sidebar_state="expanded")

# CSS para Design Moderno e Barra Lateral
st.markdown("""
    <style>
    [data-testid="stSidebar"] { background-color: #F0F2F6 !important; border-right: 1px solid #D1D5DB; }
    [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label, [data-testid="stSidebar"] p {
        color: #000000 !important; font-weight: 700 !important;
    }
    .filter-container { background-color: #FFFFFF; padding: 1.5rem; border-radius: 10px; border: 1px solid #E2E8F0; margin-bottom: 2rem; }
    .stMetric { background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; }
    </style>
    """, unsafe_allow_html=True)

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('comparativo_v8.db')
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
if 'edit_logo' not in st.session_state: st.session_state.edit_logo = False
if 'logo_data' not in st.session_state: st.session_state.logo_data = None

with st.sidebar:
    if st.session_state.logo_data is None or st.session_state.edit_logo:
        uploaded_logo = st.file_uploader("🖼️ Logo da Empresa", type=["png", "jpg", "jpeg"])
        if uploaded_logo:
            st.session_state.logo_data = uploaded_logo.read()
            st.session_state.edit_logo = False
            st.rerun()
    else:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Editar Logo"):
            st.session_state.edit_logo = True
            st.rerun()
    
    st.divider()
    menu = st.radio("Selecione:", ["📊 Dashboard", "🚛 Gestão de Tabelas", "💰 Comparativo"])

# --- TELAS ---

if menu == "📊 Dashboard":
    st.title("📊 Dashboard de Cotações")
    
    conn = sqlite3.connect('comparativo_v8.db')
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        # Filtros baseados em dados REAIS
        st.markdown('<div class="filter-container">', unsafe_allow_html=True)
        f1, f2, f3 = st.columns(3)
        with f1: 
            lista_t = ["Todas"] + sorted(df_h['transportadora'].unique().tolist())
            t_filtro = st.selectbox("🚛 Transportadora", lista_t)
        with f2:
            # Extraindo meses das datas
            df_h['Mes'] = df_h['data_hora'].apply(lambda x: x.split('/')[1])
            m_filtro = st.multiselect("📅 Mês (Número)", sorted(df_h['Mes'].unique().tolist()))
        st.markdown('</div>', unsafe_allow_html=True)

        # Lógica de Filtro
        df_filtered = df_h.copy()
        if t_filtro != "Todas":
            df_filtered = df_filtered[df_filtered['transportadora'] == t_filtro]
        if m_filtro:
            df_filtered = df_filtered[df_filtered['Mes'].isin(m_filtro)]

        # Métricas
        m1, m2, m3 = st.columns(3)
        m1.metric("Cotações", len(df_filtered))
        m2.metric("Total Cotado", f"R$ {df_filtered['total'].sum():,.2f}")
        m3.metric("Qtd Notas", int(df_filtered['qtd'].sum()))

        st.write("### 🌍 Comparativo por Estado (Total Acumulado)")
        # Consolidação por Estado (Parseando o JSON salvo)
        resumo_estados = []
        for j in df_filtered['estado_resumo']:
            resumo_estados.append(json.loads(j))
        
        if resumo_estados:
            df_est = pd.DataFrame([item for sublist in resumo_estados for item in sublist])
            pivot = df_est.groupby(['UF', 'Transportadora'])['Valor'].sum().unstack().fillna(0)
            st.dataframe(pivot, use_container_width=True)
    else:
        st.info("Nenhuma cotação realizada. Vá em 'Comparativo' para começar.")

elif menu == "🚛 Gestão de Tabelas":
    st.title("🚛 Gestão de Transportadoras")
    
    with st.expander("➕ Cadastrar Nova Transportadora"):
        t_nome = st.text_input("Nome da Transportadora").upper()
        c_u1, c_u2 = st.columns(2)
        with c_u1: f_tab = st.file_uploader("Tabela Frete", type=["xlsx"], key="tab")
        with c_u2: f_cid = st.file_uploader("Planilha Cidades", type=["xlsx"], key="cid")
        
        if f_tab and f_cid and t_nome:
            df_t = pd.read_excel(f_tab).fillna(0)
            df_c = pd.read_excel(f_cid).fillna(0)
            
            st.markdown("#### ⚖️ Mapeamento de Faixas de Peso")
            n_faixas = st.number_input("Qtd Faixas", 1, 30, 7)
            faixas = []
            for i in range(int(n_faixas)):
                r = st.columns([1, 1, 3])
                with r[0]: mi = st.number_input("Min", key=f"min{i}")
                with r[1]: ma = st.number_input("Max", key=f"max{i}")
                with r[2]: co = st.selectbox("Coluna", df_t.columns, key=f"col{i}")
                faixas.append({"min": mi, "max": ma, "col": co})
            
            st.markdown("#### ➕ Peso Adicional (Excedente)")
            r_ex = st.columns([1, 2])
            with r_ex[0]: ex_start = st.number_input("A partir de (kg):", value=101)
            with r_ex[1]: ex_col = st.selectbox("Coluna Kg Adicional", df_t.columns)

            st.markdown("#### 💰 Mapeamento de Taxas")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}
            t_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                with t_cols[idx % 3]:
                    m_taxas[tx] = st.selectbox(tx, ["Não mapear"] + list(df_t.columns))

            if st.button("💾 Salvar Transportadora"):
                mapa = {"faixas": faixas, "excedente": {"start": ex_start, "col": ex_col}, "taxas": m_taxas}
                conn = sqlite3.connect('comparativo_v8.db')
                conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                             (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa)))
                conn.commit()
                conn.close()
                st.success(f"{t_nome} salva!")
                st.rerun()

    st.divider()
    conn = sqlite3.connect('comparativo_v8.db')
    df_l = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    conn.close()
    for _, r in df_l.iterrows():
        c = st.columns([5, 1])
        c[0].write(f"🏢 **{r['nome']}**")
        if c[1].button("🗑️", key=f"del_{r['id']}"):
            conn = sqlite3.connect('comparativo_v8.db')
            conn.execute("DELETE FROM transportadoras WHERE id=?", (r['id'],))
            conn.commit()
            conn.close()
            st.rerun()

elif menu == "💰 Comparativo":
    st.title("💰 Comparativo de Fretes")
    
    f_base = st.file_uploader("📥 1. Subir Planilha Base", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        with st.expander("📌 Mapear Colunas da Planilha Base", expanded=True):
            bc1, bc2, bc3, bc4 = st.columns(4)
            with bc1: b_cid = st.selectbox("Cidade Destino", df_b.columns)
            with bc2: b_uf = st.selectbox("UF", df_b.columns)
            with bc3: b_peso = st.selectbox("Peso Real", df_b.columns)
            with bc4: b_val = st.selectbox("Valor NF", df_b.columns)

        conn = sqlite3.connect('comparativo_v8.db')
        transp_df = pd.read_sql_query("SELECT id, nome, tabela_json, cidades_json, mapeamento_json FROM transportadoras", conn)
        conn.close()

        if not transp_df.empty:
            t_alvo = st.selectbox("2. Selecionar Transportadora para Cálculo", transp_df['nome'].tolist())
            
            if st.button("🚀 Iniciar Cotação"):
                # Carregar dados da transportadora
                t_row = transp_df[transp_df['nome'] == t_alvo].iloc[0]
                df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
                df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
                mapa_t = json.loads(t_row['mapeamento_json'])
                
                res_lista = []
                total_geral = 0
                resumo_por_uf = []

                for _, nf in df_b.iterrows():
                    try:
                        c_dest = str(nf[b_cid]).upper().strip()
                        p_real = float(nf[b_peso])
                        v_nf = float(nf[b_val])
                        uf_nf = str(nf[b_uf]).upper().strip()

                        # 1. Busca Sigla
                        # Assumindo colunas fixas MUNICIPIO e SIGLA na planilha de cidades do cadastro
                        sigla = df_cid_ref[df_cid_ref.iloc[:,0].astype(str).str.upper() == c_dest].iloc[0, 2]
                        # 2. Busca Preços na Tabela
                        precos = df_tab[df_tab.iloc[:,2] == sigla].iloc[0]
                        
                        # Cálculo Peso
                        f_peso = 0
                        if p_real <= mapa_t['excedente']['start']:
                            for f in mapa_t['faixas']:
                                if p_real <= f['max']:
                                    f_peso = float(precos[f['col']])
                                    break
                        else:
                            base_100 = float(precos[mapa_t['faixas'][-1]['col']])
                            exc = float(precos[mapa_t['excedente']['col']])
                            f_peso = base_100 + ((p_real - 100) * exc)

                        total_geral += f_peso
                        resumo_por_uf.append({"UF": uf_nf, "Transportadora": t_alvo, "Valor": f_peso})
                    except: continue

                # Salvar no Banco
                now = datetime.now().strftime("%d/%m/%Y %H:%M")
                conn = sqlite3.connect('comparativo_v8.db')
                conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json, estado_resumo) VALUES (?,?,?,?,?,?)",
                             (now, t_alvo, total_geral, len(df_b), "{}", json.dumps(resumo_por_uf)))
                conn.commit()
                conn.close()
                st.success("Cotação Finalizada e Salva no Dashboard!")
                st.rerun()

    st.divider()
    st.subheader("📜 Histórico de Cotações")
    conn = sqlite3.connect('comparativo_v8.db')
    df_hist = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    conn.close()
    for _, h in df_hist.iterrows():
        with st.expander(f"📦 {h['transportadora']} | {h['data_hora']} | Total: R$ {h['total']:.2f}"):
            st.write(f"Notas: {h['qtd']}")
            if st.button("🗑️ Excluir", key=f"del_c_{h['id']}"):
                conn = sqlite3.connect('comparativo_v8.db')
                conn.execute("DELETE FROM cotacoes WHERE id=?", (h['id'],))
                conn.commit()
                conn.close()
                st.rerun()
