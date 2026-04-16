import streamlit as st
import pandas as pd
import requests
import json

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")

# 1. SUA URL DO APPS SCRIPT (JÁ CONFIGURADA)
SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw2stGRESs-l0dJQEd3bKAawtUb8_zRH1i3VIb4DALNSjdjZnked9Lxs97ProouwR0/exec"

# 2. LINK DA SUA PLANILHA PARA LEITURA
SHEET_CSV = "https://docs.google.com/spreadsheets/d/1xKSw0CXynVDJfq1_CplAHtGT9zM4aYk_pxR4NLZu0-U/export?format=csv&gid=0"

st.title("🚛 Gerenciamento de Transportadoras")

# Função para ler os dados existentes na planilha
def carregar_dados():
    try:
        # Adicionamos um parâmetro de tempo para forçar o Streamlit a ler o dado mais novo do Google
        url_com_cache = f"{SHEET_CSV}&refresh={pd.Timestamp.now().timestamp()}"
        return pd.read_csv(url_com_cache).dropna(how="all")
    except:
        return pd.DataFrame(columns=["Nome", "Mapeamento"])

# Carregar dados logo no início
df_salvo = carregar_dados()

# --- INTERFACE DE CADASTRO ---
with st.expander("⚙️ Cadastrar Nova Transportadora", expanded=True):
    t_nome = st.text_input("Nome da Transportadora (Ex: Braspress, Correios)").upper()
    
    col1, col2 = st.columns(2)
    file_tabela = col1.file_uploader("Upload: Tabela de Preços (Excel)", type=["xlsx"])
    file_cidades = col2.file_uploader("Upload: Planilha de Cidades (Excel)", type=["xlsx"])

    if file_tabela and file_cidades:
        try:
            df_c = pd.read_excel(file_cidades)
            
            st.info("Selecione quais colunas representam os dados abaixo:")
            m1, m2 = st.columns(2)
            col_cidade = m1.selectbox("Coluna que contém a CIDADE:", df_c.columns)
            col_sigla = m2.selectbox("Coluna que contém a REGIÃO ou SIGLA:", df_c.columns)
            
            if st.button("💾 SALVAR CONFIGURAÇÃO"):
                if t_nome:
                    # Monta o pacote de dados para enviar ao Google
                    payload = {
                        "Nome": t_nome,
                        "Mapeamento": f"Cidade:{col_cidade} | Sigla:{col_sigla}"
                    }
                    
                    # Envia para o Apps Script
                    headers = {'Content-Type': 'application/json'}
                    response = requests.post(SCRIPT_URL, data=json.dumps(payload), headers=headers)
                    
                    if response.status_code == 200:
                        st.success(f"✅ Transportadora {t_nome} salva com sucesso na sua planilha!")
                        # Limpa o cache e recarrega a página para mostrar o novo dado na tabela
                        st.rerun()
                    else:
                        st.error(f"Erro ao salvar: {response.status_code}. Verifique a implantação.")
                else:
                    st.warning("Por favor, digite um nome para a transportadora.")
        except Exception as e:
            st.error(f"Erro ao ler os arquivos de Excel: {e}")

# --- LISTA DE TRANSPORTADORAS CADASTRADAS ---
st.divider()
st.subheader("📋 Banco de Dados Atual (Google Sheets)")

if not df_salvo.empty:
    # Exibe a tabela formatada
    st.dataframe(df_salvo, use_container_width=True)
else:
    st.info("Nenhuma transportadora cadastrada. A planilha parece estar vazia.")

# Instrução de rodapé
st.caption("Sistema conectado via Google Apps Script (Gratuito)")
