import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

st.title("🧪 Diagnóstico de Conexão")

try:
    # 1. Tenta conectar
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # 2. Tenta ler a planilha inteira (sem especificar aba primeiro)
    # Isso ajuda a ver se o link do Secrets está funcionando
    df = conn.read(ttl=0)
    
    st.success("✅ O link do Secrets está correto!")
    st.write("Dados encontrados na página principal:")
    st.dataframe(df)

except Exception as e:
    st.error("❌ Erro na leitura do link.")
    st.write(f"Detalhe do erro: {e}")
    
    st.info("💡 Tente este passo técnico:")
    st.write("""
    Vá nos **Secrets** e confirme se não há espaços antes ou depois da URL. 
    Deve estar exatamente assim:
    `spreadsheet = \"https://docs.google.com/spreadsheets/d/1xKSw0CXynVDJfq1_CplAHtGT9zM4aYk_pxR4NLZu0-U\"`
    """)
