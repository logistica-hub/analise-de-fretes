import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime

# 1. Configuração de Layout Total
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide", initial_sidebar_state="expanded")

# CSS para remover margens brancas, ajustar o BI e melhorar o contraste
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-left: 1rem; padding-right: 1rem; max-width: 100%; }
    [data-testid="stSidebar"] { background-color: #F0F2F6 !important; border-right: 1px solid #D1D5DB; }
    [data-testid="stSidebar"] * { color: #000000 !important; font-weight: 700 !important; }
    .filter-container { background-color: #FFFFFF; padding: 1rem; border-radius: 10px; border: 1px solid #E2E8F0; margin-bottom: 1rem; }
    .stMetric { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px; }
    /* Ajuste para a tabela ocupar 100% da largura */
    .stDataFrame, div[data-testid="stTable"] { width: 100% !important; }
    </style>
    """, unsafe_allow_html=True)

# --- BANCO DE DADOS ---
DB_NAME = 'comparativo_v9.db'
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
        # FILTROS ESTILO BI (Apenas Transportadora e UF)
        st.markdown('<div class="filter-container">', unsafe_allow_html=True)
        f1, f2 = st.columns(2)
        with f1: t_list = st.multiselect("🚛 Filtrar Transportadora", sorted(df_h['transportadora'].unique().tolist()))
        with f2: 
            # Pegar UFs únicas dos resumos salvos
            all_ufs = []
            for item in df_h['estado_resumo']:
                all_ufs.extend([x['UF'] for x in json.loads(item)])
            uf_list = st.multiselect("📍 Filtrar UF (Estado)", sorted(list(set(all_ufs))))
        st.markdown('</div>', unsafe_allow_html=True)

        # Lógica de Filtragem (Simples)
        df_view = df_h.copy()
        if t_list: df_view = df_view[df_view['transportadora'].isin(t_list)]
        
        # Dashboard Cards
        c1, c2, c3 = st.columns(3)
        c1.metric("Cotações", len(df_view))
        c2.metric("Valor Total", f"R$ {df_view['total'].sum():,.2f}")
        c3.metric("Total Notas", int(df_view['qtd'].sum()))

        st.subheader("📈 Comparativo de Custo por Estado")
        # Reconstruir tabela dinâmica
        resumo_total = []
        for _, row in df_view.iterrows():
            ufs = json.loads(row['estado_resumo'])
            for u in ufs:
                if not uf_list or u['UF'] in uf_list:
                    resumo_total.append(u)
        
        if resumo_total:
            df_bi = pd.DataFrame(resumo_total)
            pivot = df_bi.pivot_table(index="UF", columns="Transportadora", values="Valor", aggfunc="sum").fillna(0)
            st.dataframe(pivot, use_container_width=True) # Sem margens brancas
            
            st.download_button("📥 Baixar Tabela Consolidada (CSV)", pivot.to_csv().encode('utf-8'), "bi_fretes.csv")
    else:
        st.info("Nenhuma cotação disponível.")

elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    
    # Lógica de Edição
    if 'edit_id' not in st.session_state: st.session_state.edit_id = None

    with st.expander("➕ Cadastrar / Editar Transportadora", expanded=st.session_state.edit_id is not None):
        t_nome = st.text_input("Nome da Transportadora", key="t_nome").upper()
        u1, u2 = st.columns(2)
        with u1: f_t = st.file_uploader("Tabela Frete", type=["xlsx"])
        with u2: f_c = st.file_uploader("Planilha Cidades", type=["xlsx"])
        
        if f_t and f_c and t_nome:
            df_t = pd.read_excel(f_t).fillna(0)
            st.markdown("#### Mapping Faixas de Peso")
            n_faixas = st.number_input("Qtd Faixas", 1, 30, 6)
            faixas = []
            for i in range(int(n_faixas)):
                r = st.columns([1, 1, 3])
                with r[0]: mi = st.number_input(f"Min", key=f"mi{i}")
                with r[1]: ma = st.number_input(f"Max", key=f"ma{i}")
                with r[2]: co = st.selectbox(f"Coluna", df_t.columns, key=f"co{i}")
                faixas.append({"min": mi, "max": ma, "col": co})

            if st.button("💾 Salvar Transportadora"):
                conn = sqlite3.connect(DB_NAME)
                mapa = {"faixas": faixas, "excedente": {"start": 101, "col": df_t.columns[-1]}, "taxas": {}}
                if st.session_state.edit_id:
                    conn.execute("UPDATE transportadoras SET nome=?, tabela_json=?, cidades_json=?, mapeamento_json=? WHERE id=?",
                                 (t_nome, df_t.to_json(), pd.read_excel(f_c).to_json(), json.dumps(mapa), st.session_state.edit_id))
                else:
                    conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                                 (t_nome, df_t.to_json(), pd.read_excel(f_c).to_json(), json.dumps(mapa)))
                conn.commit()
                conn.close()
                st.session_state.edit_id = None
                st.rerun()

    # Listagem com Edição e Exclusão
    conn = sqlite3.connect(DB_NAME)
    df_l = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    conn.close()
    for _, r in df_l.iterrows():
        c = st.columns([6, 1, 1])
        c[0].write(f"🏢 **{r['nome']}**")
        if c[1].button("✏️", key=f"et{r['id']}"):
            st.session_state.edit_id = r['id']
            st.rerun()
        if c[2].button("🗑️", key=f"dt{r['id']}"):
            conn = sqlite3.connect(DB_NAME)
            conn.execute("DELETE FROM transportadoras WHERE id=?", (r['id'],))
            conn.commit(); conn.close(); st.rerun()

elif menu == "💰 Comparativo":
    st.title("💰 Cotação e Comparativo")
    
    f_base = st.file_uploader("📥 Subir Planilha Base", type=["xlsx"])
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        st.write("### 🗂️ Arquivo Carregado")
        st.dataframe(df_b.head(3), use_container_width=True)

        conn = sqlite3.connect(DB_NAME)
        lista_t = pd.read_sql_query("SELECT nome FROM transportadoras", conn)['nome'].tolist()
        conn.close()

        t_alvo = st.selectbox("Selecione Transportadora", lista_t)
        if st.button("🚀 Gerar Cotação"):
            # (Lógica de cálculo aqui - simplificada para o exemplo)
            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            conn = sqlite3.connect(DB_NAME)
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json, estado_resumo) VALUES (?,?,?,?,?,?)",
                         (now, t_alvo, 1250.50, len(df_b), df_b.to_json(), json.dumps([{"UF":"SP", "Transportadora":t_alvo, "Valor":1250.50}])))
            conn.commit(); conn.close()
            st.success("Calculado!")

    st.divider()
    st.subheader("📜 Histórico de Cotações (Expandível)")
    
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    conn.close()

    # Opção de baixar múltiplas
    if not df_h.empty:
        selecionadas = st.multiselect("Selecionar múltiplas para baixar", df_h['id'].tolist(), format_func=lambda x: f"Cotação #{x}")
        if st.button("📥 Baixar Selecionadas (JSON/ZIP)"):
            st.info("Função de ZIP sendo preparada...")

    for _, row in df_h.iterrows():
        with st.expander(f"📦 {row['transportadora']} - {row['data_hora']} - R$ {row['total']:.2f}"):
            st.write(f"Quantidade de Itens: {row['qtd']}")
            c1, c2, c3 = st.columns(3)
            with c1: 
                # Botão para baixar esta cotação específica em CSV
                df_detalhe = pd.read_json(io.StringIO(row['detalhes_json']))
                st.download_button("📥 Baixar Excel", df_detalhe.to_csv().encode('utf-8'), f"cotacao_{row['id']}.csv")
            with c2:
                if st.button("✏️ Editar", key=f"edit_c_{row['id']}"): st.warning("Edição de cotação reabre o mapeamento")
            with c3:
                if st.button("🗑️ Excluir", key=f"del_c_{row['id']}"):
                    conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()
