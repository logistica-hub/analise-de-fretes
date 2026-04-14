import streamlit as st
import pandas as pd
import math

st.set_page_config(page_title="Auditor de Frete Profissional", layout="wide")

st.title("🚚 Auditor de Frete Universal")
st.info("O sistema agora utiliza a lógica exata da sua fórmula de Excel.")

# --- UPLOAD ---
c1, c2, c3 = st.columns(3)
with c1: f_base = st.file_uploader("1. Planilha Base", type=["xlsx"])
with c2: f_frete = st.file_uploader("2. Tabela de Frete", type=["xlsx"])
with c3: f_cidades = st.file_uploader("3. Relação Cidades", type=["xlsx"])

if f_base and f_frete and f_cidades:
    df_base = pd.read_excel(f_base).fillna(0)
    df_frete = pd.read_excel(f_frete).fillna(0)
    df_cidades = pd.read_excel(f_cidades).fillna(0)

    st.divider()
    st.subheader("🔗 Mapeamento de Colunas")
    
    m1, m2, m3 = st.columns(3)
    with m1:
        st.write("**Dados da Movimentação**")
        c_cid = st.selectbox("Cidade Destino", df_base.columns)
        c_uf = st.selectbox("UF Destino", df_base.columns)
        c_tipo = st.selectbox("Tipo (Capital/Interior)", df_base.columns)
        c_peso = st.selectbox("Peso Real", df_base.columns)
        c_val = st.selectbox("Valor NF", df_base.columns)
    
    with m2:
        st.write("**Referência de Cidades**")
        c_cid_ref = st.selectbox("Cidade (Planilha Cidades)", df_cidades.columns)
        c_sigla_ref = st.selectbox("Sigla/Região (Planilha Cidades)", df_cidades.columns)
    
    with m3:
        st.write("**Tabela de Preços (Jamef)**")
        c_sigla_f = st.selectbox("Coluna Sigla (Tabela Frete)", df_frete.columns)
        c_faixas = st.multiselect("Colunas de Faixas (E até J na Jamef)", df_frete.columns)
        c_exc = st.selectbox("Coluna Excedente (K na Jamef)", df_frete.columns)

    if st.button("🚀 Executar Auditoria"):
        def auditoria(row):
            try:
                # Dados da linha
                cid = str(row[c_cid]).strip().upper()
                uf = str(row[c_uf]).strip().upper()
                tipo = str(row[c_tipo]).strip().upper()
                peso = float(row[c_peso])
                valor_nf = float(row[c_val])

                # 1. Busca Sigla
                sigla = df_cidades[df_cidades[c_cid_ref].str.upper() == cid][c_sigla_ref].values[0]
                
                # 2. Busca Dados na Tabela Frete
                f_row = df_frete[df_frete[c_sigla_f] == sigla].iloc[0]

                # --- LÓGICA DO FRETE PESO (Sua fórmula Excel) ---
                if peso <= 100:
                    # CORRESP aproximado para faixas
                    faixas_num = sorted([int(''.join(filter(str.isdigit, str(c)))) for c in c_faixas])
                    col_nome = c_faixas[-1]
                    for n in faixas_num:
                        if peso <= n:
                            col_nome = [c for c in c_faixas if str(n) in str(c)][0]
                            break
                    frete_peso = float(f_row[col_nome])
                else:
                    # Valor de 100kg + (Peso - 100) * Excedente
                    valor_100kg = float(f_row[c_faixas[-1]])
                    valor_exc = float(f_row[c_exc])
                    frete_peso = valor_100kg + ((peso - 100) * valor_exc)

                # --- TAXAS (CONFORME SUA FÓRMULA) ---
                # Ad Valorem (Coluna L e M da sua Jamef)
                adv_p = float(f_row.iloc[11]) # Coluna L
                adv_m = float(f_row.iloc[12]) # Coluna M
                taxa_advalorem = max(valor_nf * adv_p, adv_m)

                # Pedágio (Fração 100kg * 14.7)
                taxa_pedagio = math.ceil(peso / 100) * 14.7

                # TAS (Coluna N)
                taxa_tas = float(f_row.iloc[13])

                # Taxa Fixa Adicional (O "7.41" da sua fórmula)
                taxa_fixa = 7.41

                # Gris Especial (O "0,0016" ou Mínimo da sua fórmula)
                taxa_gris = max(valor_nf * 0.0016, 4.36)

                # REGRA RIO DE JANEIRO (EMEX/TDA)
                taxa_rj_extra = 0
                if uf == "RJ":
                    # Regra Capital
                    if "CAPITAL" in tipo:
                        taxa_rj_extra += max(valor_nf * 0.0031, 28.48)
                    # Regra Geral RJ
                    taxa_rj_extra += max(valor_nf * 0.0021, 6.87)

                total = frete_peso + taxa_advalorem + taxa_pedagio + taxa_tas + taxa_fixa + taxa_gris + taxa_rj_extra
                
                return pd.Series([sigla, frete_peso, taxa_pedagio, taxa_advalorem, taxa_gris, taxa_rj_extra, total])

            except Exception as e:
                return pd.Series(["Erro", 0, 0, 0, 0, 0, 0])

        colunas_fim = ['Sigla', 'Frete Peso', 'Pedágio', 'Ad Valorem', 'Gris', 'Extras RJ', 'Total Calculado']
        df_base[colunas_fim] = df_base.apply(auditoria, axis=1)
        
        st.success("✅ Processado com sucesso!")
        st.dataframe(df_base)
        
        csv = df_base.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Baixar Excel Auditado", csv, "auditoria_jamef.csv", "text/csv")
