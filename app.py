import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.title("🔍 Teste de Conexão com Link Completo")

try:
    # Cria a conexão
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # Lê os dados (ttl=0 para não usar cache e ler em tempo real)
    df = conn.read(ttl=0)
    
    st.success("✅ AGORA SIM! Conectado com o link correto.")
    st.write("Dados encontrados na planilha:")
    st.dataframe(df)

except Exception as e:
    st.error("❌ Erro de conexão.")
    st.write(f"Detalhe: {e}")
