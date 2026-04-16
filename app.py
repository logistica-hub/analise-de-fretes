import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json

st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")
st.title("🚛 Configuração de Transportadoras")

# Conecta à planilha
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 1. BUSCAR DADOS EXISTENTES ---
try:
    df_salvo = conn.read(worksheet="Transportadoras", ttl=0)
except:
    df_salvo = pd.DataFrame(columns=["Nome", "Mapeamento"])

# --- 2. ÁREA DE CONFIGURAÇÃO ---
with st.expander("⚙️ Configurar Nova ou Editar Existente", expanded=True):
    lista_nomes = ["NOVA TRANSPORTADORA"]
    if not df_salvo.empty and "Nome" in df_salvo.columns:
        lista_nomes += df_salvo["Nome"].dropna().tolist()
    
    escolha = st.selectbox("Selecione a Transportadora", lista_nomes)
    
    t_nome = st.text_input("Nome da Transportadora", value="" if escolha == "NOVA TRANSPORTADORA" else escolha).upper()
    
    st.info("Suba as planilhas para mapear as colunas:")
    c1, c2 = st.columns(2)
    file_tabela = c1.file_uploader("Tabela de Preços (Excel)", type=["xlsx"])
    file_cidades = c2.file_uploader("Planilha de Cidades/Regiões (Excel)", type=["xlsx"])

    if file_tabela and file_cidades:
        df_t = pd.read_excel(file_tabela).fillna(0)
        df_c = pd.read_excel(file_cidades).fillna(0)
        
        st.divider()
        st.subheader("📍 Mapeamento de Colunas")
        col1, col2 = st.columns(2)
        
        m_cidade = col1.selectbox("Coluna de CIDADE (na planilha de Cidades):", df_c.columns)
        m_regiao = col2.selectbox("Coluna de REGIÃO/SIGLA (na planilha de Cidades):", df_c.columns)
        
        if st.button("💾 Salvar Configuração Completa"):
            # Criamos a configuração em formato de texto simples
            config_str = f"Cidade:{m_cidade} | Regiao:{m_regiao}"
            
            nova_linha = pd.DataFrame([{"Nome": t_nome, "Mapeamento": config_str}])
            
            # Remove duplicados se estiver editando
            if not df_salvo.empty and escolha != "NOVA TRANSPORTADORA":
                df_atualizado = df_salvo[df_salvo["Nome"] != escolha]
            else:
                df_atualizado = df_salvo
                
            df_final = pd.concat([df_atualizado, nova_linha], ignore_index=True)
            
            # Limpa valores nulos que podem dar erro no Google
            df_final = df_final.dropna(subset=["Nome"])
            
            # Envia para o Google
            conn.update(worksheet="Transportadoras", data=df_final)
            st.success(f"✅ Configuração de {t_nome} salva!")
            st.rerun()

# --- 3. VISUALIZAÇÃO ---
st.subheader("Transportadoras no Banco de Dados")
st.dataframe(df_salvo)
