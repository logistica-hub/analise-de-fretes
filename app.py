import streamlit as st
import pandas as pd
import math
import sqlite3
import json
import io
from datetime import datetime

# Configurações de Estilo e Layout
st.set_page_config(page_title="Comparativo de Tabelas Pro", layout="wide")

# CSS para tornar o design mais moderno
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .stExpander { border: 1px solid #dee2e6; border-radius: 8px; margin-bottom: 10px; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #eee; }
    </style>
    """, unsafe_allow_html=True)

# --- BANCO DE DADOS (V3 - Estrutura SaaS) ---
def init_db():
    conn = sqlite3.connect('comparativo_v3.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cotacoes_realizadas 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, transportadora TEXT, 
                  resultado_json TEXT, resumo_total REAL, qtd_notas INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# --- SIDEBAR (MENU LATERAL) ---
with st.sidebar:
    st.title("⚙️ Configurações")
    logo_file = st.file_uploader("Subir Logo da Empresa", type=["png", "jpg"])
    menu = st.selectbox("Navegação", ["📊 Dashboard", "🚛 Cadastro de Tabelas", "💰 Comparativo (Cotação)"])
    st.divider()
    st.info("Desenvolvido para Gestão de Fretes Industrial")

# --- TOPO (LOGO) ---
col_logo_vazia, col_logo_img = st.columns([8, 1])
with col_logo_img:
    if logo_file:
        st.image(logo_file, width=100)

# --- FUNÇÕES DE AUXÍLIO ---
def salvar_transp(nome, df_p, df_c, mapa):
    conn = sqlite3.connect('comparativo_v3.db')
    conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                 (nome, df_p.to_json(orient='split'), df_c.to_json(orient='split'), json.dumps(mapa)))
    conn.commit()
    conn.close()

def listar_transp():
    conn = sqlite3.connect('comparativo_v3.db')
    df = pd.read_sql_query("SELECT id, nome, mapeamento_json FROM transportadoras", conn)
    conn.close()
    return df

# --- ABA 1: DASHBOARD ---
if menu == "📊 Dashboard":
    st.subheader("📊 Dashboard Comparativo por Estado")
    
    # Filtros
    f1, f2, f3 = st.columns(3)
    with f1: st.multiselect("Filtrar Estado", ["SP", "RJ", "MG", "BA", "PR"]) # Exemplo
    with f2: st.selectbox("Mês", ["Janeiro", "Fevereiro", "Março"])
    
    # Tabela Dinâmica (Placeholder)
    st.write("### Frete Total por UF")
    # Aqui o sistema buscaria no banco de cotações para montar o pivot
    st.info("O Dashboard será preenchido conforme as cotações forem salvas.")
    st.button("📥 Baixar Relatório Dashboard")

# --- ABA 2: CADASTRO DE TRANSPORTADORAS ---
elif menu == "🚛 Cadastro de Tabelas":
    st.subheader("🚛 Gestão de Transportadoras")
    
    with st.expander("➕ Cadastrar Nova Transportadora"):
        nome_t = st.text_input("Nome da Transportadora")
        up1, up2 = st.columns(2)
        with up1: f_precos = st.file_uploader("Tabela de Frete (Excel)", type=["xlsx"])
        with up2: f_cidades = st.file_uploader("Planilha de Cidades (Excel)", type=["xlsx"])
        
        if f_precos and f_cidades:
            df_p = pd.read_excel(f_precos).fillna(0)
            df_c = pd.read_excel(f_cidades).fillna(0)
            
            st.markdown("### ⚙️ Mapeamento de Faixas de Peso Dinâmicas")
            num_faixas = st.number_input("Quantas faixas de peso existem? (Ex: 5, 10, 20...)", min_value=1, value=5)
            faixas_map = []
            cols_f = st.columns(3)
            for i in range(int(num_faixas)):
                with cols_f[i % 3]:
                    min_w = st.number_input(f"De (kg) - Faixa {i+1}", key=f"min_{i}")
                    max_w = st.number_input(f"Até (kg) - Faixa {i+1}", key=f"max_{i}")
                    col_p = st.selectbox(f"Coluna na Tabela", df_p.columns, key=f"col_{i}")
                    faixas_map.append({"min": min_w, "max": max_w, "col": col_p})
            
            st.markdown("### 🏷️ Mapeamento de Taxas (Opcional)")
            taxas_map = {}
            t1, t2, t3 = st.columns(3)
            with t1:
                taxas_map['adv_p'] = st.selectbox("Ad Valorem %", ["Não mapear"] + list(df_p.columns))
                taxas_map['trt'] = st.selectbox("Taxa TRT", ["Não mapear"] + list(df_p.columns))
            with t2:
                taxas_map['adv_m'] = st.selectbox("Ad Valorem Mínimo", ["Não mapear"] + list(df_p.columns))
                taxas_map['tda'] = st.selectbox("Taxa TDA", ["Não mapear"] + list(df_p.columns))
            with t3:
                taxas_map['tas'] = st.selectbox("TAS", ["Não mapear"] + list(df_p.columns))
                taxas_map['seccat'] = st.selectbox("Taxa SEC-CAT", ["Não mapear"] + list(df_p.columns))

            if st.button("💾 Salvar Transportadora"):
                mapa_completo = {"faixas": faixas_map, "taxas": taxas_map, "col_sigla_f": "SIGLA", "col_cid_c": "MUNICIPIO"} # Exemplo
                salvar_transp(nome_t, df_p, df_c, mapa_completo)
                st.success("Transportadora salva!")

    st.markdown("---")
    st.subheader("📋 Transportadoras Cadastradas")
    df_lista = listar_transp()
    for _, item in df_lista.iterrows():
        c_list = st.columns([3, 2, 2, 1, 1])
        c_list[0].write(f"**{item['nome']}**")
        c_list[1].write("📁 Tabela_Frete.xlsx")
        c_list[2].write("📁 Cidades.xlsx")
        if c_list[3].button("✏️", key=f"edit_{item['id']}"): st.info("Remapeamento em breve")
        if c_list[4].button("🗑️", key=f"del_{item['id']}"): st.error("Excluído")

# --- ABA 3: COMPARATIVO (COTAÇÃO) ---
elif menu == "💰 Comparativo (Cotação)":
    st.subheader("💰 Realizar Novo Comparativo de Tabelas")
    
    # Planilha Base Fixa
    f_base = st.file_uploader("Subir Planilha Base (Sempre no mesmo formato)", type=["xlsx"])
    if f_base:
        st.success("Planilha Base carregada e fixada no topo.")
        
        # Seleção de Transportadora
        lista_t = listar_transp()
        t_alvo = st.selectbox("Selecione a Transportadora para Cotação", lista_t['nome'].tolist())
        
        if st.button("🧧 Gerar Cotação"):
            # Aqui entra a lógica de cálculo usando as faixas dinâmicas e TRT/TDA
            data_agora = datetime.now().strftime("%d/%m/%Y %H:%M")
            st.success(f"Cotação realizada em {data_agora}")
            
    st.divider()
    st.subheader("📜 Histórico de Cotações Realizadas")
    # Exemplo de listagem com expander
    with st.expander("🔽 Cotação #125 - JAMEF - 15/04/2024 10:00"):
        st.write("Qtd Notas: 150 | Valor Total: R$ 12.450,00")
        st.button("📥 Baixar Excel desta cotação")
        # Aqui viria a tabela com o botão do "olho"
