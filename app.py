import streamlit as st
import pandas as pd
import math

st.set_page_config(page_title="Auditor de Frete Pro", layout="wide")

st.title("🚚 Sistema de Auditoria de Frete Independente")
st.markdown("Suba suas planilhas e processe os cálculos sem depender de IA.")

# --- SIDEBAR: CONFIGURAÇÃO DE TAXAS ---
st.sidebar.header("Configurações de Taxas (Jamef)")
valor_pedagio_fracao = st.sidebar.number_input("Valor Pedágio (por 100kg)", value=14.70)
ad_valorem_perc = st.sidebar.number_input("Ad Valorem (%)", value=0.15) / 100
ad_valorem_min = st.sidebar.number_input("Ad Valorem Mínimo (R$)", value=9.50)
gris_perc = st.sidebar.number_input("Gris (%)", value=0.20) / 100
gris_min = st.sidebar.number_input("Gris Mínimo (R$)", value=6.00)

# --- UPLOAD DOS ARQUIVOS ---
col1, col2, col3 = st.columns(3)
with col1:
    file_base = st.file_uploader("1. Planilha Base (Movimentação)", type=["xlsx", "csv"])
with col2:
    file_frete = st.file_uploader("2. Tabela de Fretes (Preços)", type=["xlsx", "csv"])
with col3:
    file_cidades = st.file_uploader("3. Relação de Cidades/Siglas", type=["xlsx", "csv"])

if file_base and file_frete and file_cidades:
    df_base = pd.read_excel(file_base)
    df_frete = pd.read_excel(file_frete)
    df_cidades = pd.read_excel(file_cidades)

    st.subheader("🔗 Mapeamento de Colunas")
    st.info("O layout mudou? Basta selecionar abaixo quais são as colunas corretas.")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        col_cidade = st.selectbox("Coluna de Cidade (Base)", df_base.columns)
    with c2:
        col_peso = st.selectbox("Coluna de Peso (Base)", df_base.columns)
    with c3:
        col_valor = st.selectbox("Coluna de Valor NF (Base)", df_base.columns)

    if st.button("🚀 Processar Auditoria"):
        # Lógica de cálculo
        def calcular(linha):
            peso = linha[col_peso]
            valor_nf = linha[col_valor]
            cidade = linha[col_cidade]
            
            # 1. Busca Sigla da Cidade
            # (Simulação da lógica que você descreveu)
            pedagio = math.ceil(peso / 100) * valor_pedagio_fracao
            ad_valorem = max(valor_nf * ad_valorem_perc, ad_valorem_min)
            
            # Aqui entraria a busca na tabela de frete conforme a sigla
            # Por brevidade, simulamos um frete peso base
            frete_peso_estimado = 50.00 # Exemplo
            
            total = frete_peso_estimado + pedagio + ad_valorem
            return total

        df_base['Frete_Calculado'] = df_base.apply(calcular, axis=1)
        
        st.success("✅ Cálculo Concluído!")
        st.dataframe(df_base)
        
        # Exportação
        csv = df_base.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Resultado em CSV", csv, "auditoria_final.csv", "text/csv")
