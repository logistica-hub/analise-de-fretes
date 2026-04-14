import streamlit as st
import pandas as pd
import math

st.set_page_config(page_title="Auditor de Frete Universal", layout="wide")

st.title("🚚 Auditor de Frete Multimalha")

# --- SIDEBAR: REGRAS DE TAXAS ---
st.sidebar.header("⚙️ Configuração de Taxas")
p_pedagio = st.sidebar.number_input("Pedágio (por fração 100kg)", value=14.70)
p_advalorem = st.sidebar.number_input("Ad Valorem (%)", value=0.15) / 100
p_advalorem_min = st.sidebar.number_input("Ad Valorem Mínimo (R$)", value=9.50)
p_gris = st.sidebar.number_input("Gris (%)", value=0.20) / 100
p_gris_min = st.sidebar.number_input("Gris Mínimo (R$)", value=6.00)

# --- UPLOAD ---
c1, c2, c3 = st.columns(3)
with c1: f_base = st.file_uploader("1. Planilha Base", type=["xlsx", "csv"])
with c2: f_frete = st.file_uploader("2. Tabela de Frete", type=["xlsx", "csv"])
with c3: f_cidades = st.file_uploader("3. Relação Cidades", type=["xlsx", "csv"])

if f_base and f_frete and f_cidades:
    df_base = pd.read_excel(f_base) if "xlsx" in f_base.name else pd.read_csv(f_base)
    df_frete = pd.read_excel(f_frete) if "xlsx" in f_frete.name else pd.read_csv(f_frete)
    df_cidades = pd.read_excel(f_cidades) if "xlsx" in f_cidades.name else pd.read_csv(f_cidades)

    st.divider()
    st.subheader("🔗 Mapeamento Universal")
    
    m1, m2, m3 = st.columns(3)
    with m1:
        col_cidade_base = st.selectbox("Coluna Cidade (Base)", df_base.columns)
        col_peso_base = st.selectbox("Coluna Peso (Base)", df_base.columns)
        col_valor_base = st.selectbox("Coluna Valor NF (Base)", df_base.columns)
    with m2:
        col_cidade_ref = st.selectbox("Coluna Cidade (Planilha Cidades)", df_cidades.columns)
        col_sigla_ref = st.selectbox("Coluna Sigla/Região (Planilha Cidades)", df_cidades.columns)
    with m3:
        col_sigla_frete = st.selectbox("Coluna Sigla (Tabela Frete)", df_frete.columns)
        col_excedente = st.selectbox("Coluna Preço KG Excedente (>100kg)", df_frete.columns)

    # Seleção múltipla para as faixas de peso (Ex: 10kg, 20kg, 30kg...)
    col_faixas = st.multiselect("Selecione TODAS as colunas de faixas de peso (ex: 10kg, 20kg...)", df_frete.columns)

    if st.button("🚀 Processar Auditoria") and col_faixas:
        def calcular_row(row):
            try:
                cidade = str(row[col_cidade_base]).strip().upper()
                peso = float(row[col_peso_base])
                valor_nf = float(row[col_valor_base])

                # 1. Busca Sigla
                sigla = df_cidades[df_cidades[col_cidade_ref].str.upper() == cidade][col_sigla_ref].values[0]
                
                # 2. Busca Linha de Preço
                linha_preco = df_frete[df_frete[col_sigla_frete] == sigla].iloc[0]

                # 3. Lógica de Frete Peso
                if peso > 100:
                    frete_peso = peso * float(linha_preco[col_excedente])
                else:
                    # Encontra a menor faixa que atende ao peso
                    # Supõe que os nomes das colunas de faixa sejam números ou contenham números (ex: "10", "20")
                    faixas_numeros = [int(''.join(filter(str.isdigit, c))) for c in col_faixas]
                    faixas_ordenadas = sorted(zip(faixas_numeros, col_faixas))
                    
                    col_escolhida = col_faixas[-1] # Default última
                    for num, nome_col in faixas_ordenadas:
                        if peso <= num:
                            col_escolhida = nome_col
                            break
                    frete_peso = float(linha_preco[col_escolhida])

                # 4. Taxas
                pedagio = math.ceil(peso / 100) * p_pedagio
                adval = max(valor_nf * p_advalorem, p_advalorem_min)
                gris = max(frete_peso * p_gris, p_gris_min)
                
                total = frete_peso + pedagio + adval + gris
                return pd.Series([sigla, frete_peso, pedagio, adval, gris, total])
            except:
                return pd.Series(["Erro", 0, 0, 0, 0, 0])

        cols_result = ['Sigla', 'Frete Peso', 'Pedágio', 'Ad Valorem', 'Gris', 'Total Calculado']
        df_base[cols_result] = df_base.apply(calcular_row, axis=1)
        
        st.success("Auditoria Finalizada!")
        st.dataframe(df_base)
        
        csv = df_base.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Baixar Resultado", csv, "auditoria_final.csv", "text/csv")
