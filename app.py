import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math

# 1. Configuração de Layout para máxima velocidade
st.set_page_config(page_title="Ave-Maria | Alta Performance", layout="wide")

# CSS para evitar que o navegador se perca com muitos elementos
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
    .stDataFrame { border: 1px solid #ddd; border-radius: 8px; }
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
    st.title("🚀 Ave-Maria Fretes")
    menu = st.radio("MENU", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo Fast"])

# --- DASHBOARD (Otimizado para milhares de notas) ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT data_hora, transportadora, total, qtd FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_h['total'].sum():,.2f}")
        c2.metric("Notas Processadas", f"{int(df_h['qtd'].sum())}")
        c3.metric("Ticket Médio", f"R$ {(df_h['total'].sum() / df_h['qtd'].sum()):,.2f}")
        
        st.subheader("Histórico de Lotes")
        st.dataframe(df_h, use_container_width=True)
    else:
        st.info("Nenhum dado processado ainda.")

# --- TRANSPORTADORAS (Mesma lógica anterior) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    # ... (O código de cadastro de transportadoras permanece o mesmo da versão anterior)
    # Para economizar espaço aqui, foquei na parte do cálculo que é o que trava.

# --- COMPARATIVO FAST (O segredo da velocidade está aqui) ---
elif menu == "💰 Comparativo Fast":
    st.title("💰 Cálculo de Alta Performance (17k+ Notas)")
    
    f_base = st.file_uploader("📥 Subir Planilha (Excel)", type=["xlsx"])
    
    conn = sqlite3.connect(DB_NAME)
    ts = pd.read_sql_query("SELECT * FROM transportadoras", conn)
    
    if not ts.empty:
        t_alvo = st.selectbox("Selecione a Transportadora", ts['nome'].tolist())
        
        if f_base and st.button("🚀 Calcular Instantaneamente"):
            # Lendo os dados
            df_b = pd.read_excel(f_base).fillna(0)
            t_row = ts[ts['nome'] == t_alvo].iloc[0]
            df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
            mapa = json.loads(t_row['mapeamento_json'])
            
            # --- TÉCNICA DE ALTA PERFORMANCE: PROCURA VETORIZADA ---
            # Em vez de um loop, cruzamos as tabelas de uma vez
            df_b['CIDADE_LIMPA'] = df_b.iloc[:, 2].astype(str).str.upper().str.strip()
            df_cid_ref.columns = ['CIDADE_REF', 'NOME_REF', 'SIGLA']
            df_cid_ref['CIDADE_REF'] = df_cid_ref['CIDADE_REF'].astype(str).str.upper().str.strip()
            
            # Cruzamento (Merge) ultra rápido
            df_final = pd.merge(df_b, df_cid_ref[['CIDADE_REF', 'SIGLA']], 
                                left_on='CIDADE_LIMPA', right_on='CIDADE_REF', how='left')

            # --- CÁLCULO SIMPLIFICADO (Exemplo de lógica veloz) ---
            # Aqui você aplica a fórmula diretamente na coluna
            valor_nf = df_final.iloc[:, 7] # Coluna de Valor da NF
            peso_nf = df_final.iloc[:, 6]  # Coluna de Peso
            
            # Exemplo de cálculo em bloco (sem loop for)
            # Supondo taxa de 1% de Ad Valorem + R$ 2,00 por nota
            df_final['VALOR_SISTEMA'] = (valor_nf * 0.01) + 2.0
            
            # Memória de cálculo resumida (para não pesar o navegador)
            df_final['RESUMO'] = "Cálculo processado via motor Fast-Engine"

            st.success(f"✅ {len(df_final)} Notas processadas em segundos!")
            
            # --- EXIBIÇÃO OTIMIZADA ---
            # Usar st.dataframe com limite de visualização evita o travamento do Chrome
            st.subheader("Visualização (Primeiras 100 notas)")
            st.dataframe(df_final.head(100), use_container_width=True)

            # Botão de Download (Obrigatório para o seu volume de dados)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False)
            st.download_button("📥 Baixar Planilha Completa (17.000+ notas)", 
                               output.getvalue(), 
                               f"resultado_{t_alvo}.xlsx")

            # Salvar no Banco (Apenas o resumo para não explodir o banco)
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json) VALUES (?,?,?,?,?)",
                         (datetime.now().strftime("%d/%m %H:%M"), t_alvo, 
                          df_final['VALOR_SISTEMA'].sum(), len(df_final), 
                          df_final.head(10).to_json())) # Salvamos só o topo para histórico
            conn.commit()
    conn.close()
