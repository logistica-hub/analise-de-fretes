import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime

# 1. Configuração de Layout
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide", initial_sidebar_state="expanded")

# CSS para Design BI e Remoção de Margens
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; max-width: 95%; }
    [data-testid="stSidebar"] { background-color: #F0F2F6 !important; border-right: 1px solid #D1D5DB; }
    [data-testid="stSidebar"] * { color: #000000 !important; font-weight: 700 !important; }
    .filter-container { background-color: #FFFFFF; padding: 1.2rem; border-radius: 10px; border: 1px solid #E2E8F0; margin-bottom: 1rem; }
    .stMetric { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'comparativo_v10.db'

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
    if 'edit_logo' not in st.session_state: st.session_state.edit_logo = False

    if st.session_state.logo_data is None or st.session_state.edit_logo:
        up = st.file_uploader("🖼️ Logo", type=["png", "jpg"])
        if up: 
            st.session_state.logo_data = up.read()
            st.session_state.edit_logo = False
            st.rerun()
    else:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Editar Logo"):
            st.session_state.edit_logo = True
            st.rerun()
    
    st.divider()
    menu = st.radio("MENU", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])

# --- TELAS ---

if menu == "📊 Dashboard":
    st.title("📊 BI - Dashboard de Fretes")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        st.markdown('<div class="filter-container">', unsafe_allow_html=True)
        f1, f2 = st.columns(2)
        with f1: t_filt = st.multiselect("🚛 Transportadora", sorted(df_h['transportadora'].unique().tolist()))
        
        all_resumos = []
        for r in df_h['estado_resumo']: all_resumos.extend(json.loads(r))
        df_resumo_all = pd.DataFrame(all_resumos)
        
        with f2: uf_filt = st.multiselect("📍 Estado (UF)", sorted(df_resumo_all['UF'].unique().tolist()))
        st.markdown('</div>', unsafe_allow_html=True)

        # Filtragem
        df_final = df_resumo_all.copy()
        if t_filt: df_final = df_final[df_final['Transportadora'].isin(t_filt)]
        if uf_filt: df_final = df_final[df_final['UF'].isin(uf_filt)]

        m1, m2 = st.columns(2)
        m1.metric("Valor Total em Fretes", f"R$ {df_final['Valor'].sum():,.2f}")
        m2.metric("Cotações Realizadas", len(df_h))

        st.subheader("📈 Comparativo por UF")
        if not df_final.empty:
            pivot = df_final.pivot_table(index="UF", columns="Transportadora", values="Valor", aggfunc="sum").fillna(0)
            st.dataframe(pivot, use_container_width=True)
    else:
        st.info("Sem dados. Realize uma cotação no menu 'Comparativo'.")

elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    
    if 'edit_id' not in st.session_state: st.session_state.edit_id = None
    
    # Se estiver editando, carregar dados
    default_nome = ""
    if st.session_state.edit_id:
        conn = sqlite3.connect(DB_NAME)
        edit_data = pd.read_sql_query(f"SELECT * FROM transportadoras WHERE id={st.session_state.edit_id}", conn).iloc[0]
        conn.close()
        default_nome = edit_data['nome']
        st.warning(f"Editando: {default_nome}")

    with st.expander("➕ Cadastrar / Editar Transportadora", expanded=(st.session_state.edit_id is not None)):
        t_nome = st.text_input("Nome da Transportadora", value=default_nome).upper()
        u1, u2 = st.columns(2)
        with u1: f_tab = st.file_uploader("Tabela Frete (Excel)", type=["xlsx"])
        with u2: f_cid = st.file_uploader("Cidades (Excel)", type=["xlsx"])
        
        if f_tab:
            df_t = pd.read_excel(f_tab).fillna(0)
            
            st.markdown("#### ⚖️ Mapping Faixas de Peso")
            n_f = st.number_input("Qtd Faixas", 1, 30, 6)
            faixas = []
            cols_f = st.columns(3)
            for i in range(int(n_f)):
                with cols_f[i % 3]:
                    r = st.columns([1, 1, 2])
                    mi = r[0].number_input("Min", key=f"mi{i}")
                    ma = r[1].number_input("Max", key=f"ma{i}")
                    co = r[2].selectbox("Col", df_t.columns, key=f"co{i}")
                    faixas.append({"min": mi, "max": ma, "col": co})
            
            st.markdown("#### 💰 Mapping de Taxas (Voltou!)")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}
            t_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                with t_cols[idx % 3]:
                    m_taxas[tx] = st.selectbox(tx, ["Não mapear"] + list(df_t.columns), key=f"tx_{idx}")

            if st.button("💾 Salvar Transportadora"):
                mapa_final = {"faixas": faixas, "taxas": m_taxas}
                conn = sqlite3.connect(DB_NAME)
                if st.session_state.edit_id:
                    conn.execute("UPDATE transportadoras SET nome=?, tabela_json=?, mapeamento_json=? WHERE id=?",
                                 (t_nome, df_t.to_json(), json.dumps(mapa_final), st.session_state.edit_id))
                else:
                    conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                                 (t_nome, df_t.to_json(), pd.read_excel(f_cid).to_json(), json.dumps(mapa_final)))
                conn.commit(); conn.close()
                st.session_state.edit_id = None
                st.rerun()

    st.divider()
    # Listagem
    conn = sqlite3.connect(DB_NAME)
    df_l = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    conn.close()
    for _, r in df_l.iterrows():
        c = st.columns([5, 1, 1])
        c[0].write(f"🏢 **{r['nome']}**")
        if c[1].button("✏️", key=f"edit_t_{r['id']}"):
            st.session_state.edit_id = r['id']
            st.rerun()
        if c[2].button("🗑️", key=f"del_t_{r['id']}"):
            conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM transportadoras WHERE id=?", (r['id'],)); conn.commit(); conn.close(); st.rerun()

elif menu == "💰 Comparativo":
    st.title("💰 Comparativo de Fretes")
    f_base = st.file_uploader("📥 Subir Planilha Base", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        st.write("### Mapeamento da Base")
        bc1, bc2, bc3, bc4 = st.columns(4)
        with bc1: b_cid = st.selectbox("Cidade", df_b.columns)
        with bc2: b_uf = st.selectbox("UF", df_b.columns)
        with bc3: b_peso = st.selectbox("Peso", df_b.columns)
        with bc4: b_val = st.selectbox("Valor NF", df_b.columns)

        conn = sqlite3.connect(DB_NAME)
        ts = pd.read_sql_query("SELECT * FROM transportadoras", conn)
        conn.close()

        t_alvo = st.selectbox("Selecione a Transportadora", ts['nome'].tolist())
        if st.button("🚀 Gerar Cotação"):
            # Lógica de Cálculo (Resumida para o exemplo, deve conter a busca por sigla)
            df_b['FRETE_COTADO'] = 150.00 # Simulação de cálculo
            resumo = [{"UF": "SP", "Transportadora": t_alvo, "Valor": df_b['FRETE_COTADO'].sum()}]
            
            conn = sqlite3.connect(DB_NAME)
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json, estado_resumo) VALUES (?,?,?,?,?,?)",
                         (datetime.now().strftime("%d/%m/%Y %H:%M"), t_alvo, df_b['FRETE_COTADO'].sum(), len(df_b), df_b.to_json(), json.dumps(resumo)))
            conn.commit(); conn.close()
            st.success("Concluído!")

    st.divider()
    st.subheader("📜 Histórico de Cotações")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    conn.close()

    for _, row in df_h.iterrows():
        with st.expander(f"📦 {row['transportadora']} | {row['data_hora']} | R$ {row['total']:.2f}"):
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            # DOWNLOAD DO EXCEL COM COTAÇÕES
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_det.to_excel(writer, index=False)
            st.download_button("📥 Baixar Planilha com Fretes", output.getvalue(), f"cotacao_{row['transportadora']}.xlsx")
            if st.button("🗑️ Excluir", key=f"del_c_{row['id']}"):
                conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()
