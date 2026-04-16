import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

st.title("🚛 Cadastro de Transportadoras")

# Conecta à planilha
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FORMULÁRIO DE CADASTRO ---
with st.form("novo_cadastro"):
    nome_transp = st.text_input("Nome da Transportadora")
    botao_salvar = st.form_submit_button("Salvar na Planilha")

    if botao_salvar:
        if nome_transp:
            # 1. Primeiro, lemos o que já existe na planilha
            df_atual = conn.read(worksheet="Transportadoras", ttl=0)
            
            # 2. Criamos uma nova linha
            nova_linha = pd.DataFrame([{"Nome": nome_transp.upper()}])
            
            # 3. Juntamos o antigo com o novo
            df_atualizado = pd.concat([df_atual, nova_linha], ignore_index=True)
            
            # 4. Enviamos de volta para o Google Sheets
            conn.update(worksheet="Transportadoras", data=df_atualizado)
            
            st.success(f"✅ {nome_transp} salva com sucesso!")
        else:
            st.warning("Digite um nome antes de salvar.")

# --- EXIBIÇÃO ---
st.subheader("Lista de Transportadoras Cadastradas")
# Recarrega a lista atualizada
df_exibir = conn.read(worksheet="Transportadoras", ttl=0)
st.dataframe(df_exibir)
