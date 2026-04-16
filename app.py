import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.title("🧪 Teste de Conexão")

try:
    # Cria a conexão usando o que você salvou no Secrets
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # Tenta ler apenas os nomes das colunas da aba Transportadoras para testar
    df = conn.read(worksheet="Transportadoras", ttl=0)
    
    st.success("✅ Conexão estabelecida com sucesso!")
    st.write("Aqui está o que encontrei na aba 'Transportadoras':")
    st.dataframe(df)

except Exception as e:
    st.error("❌ Ainda não consegui ler a planilha.")
    st.info("Verifique se:")
    st.write("1. O nome da aba na planilha é exatamente **Transportadoras** (sem espaço e com o T maiúsculo).")
    st.write("2. Você clicou em 'Share' na planilha e mudou para 'Anyone with the link'.")
    st.write(f"Erro técnico: {e}")
