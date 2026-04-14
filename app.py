import streamlit as st
import pandas as pd
import math
import sqlite3
import json
import io

st.set_page_config(page_title="Gestor de Fretes Pro", layout="wide")

# --- BANCO DE DADOS (SQLite Local) ---
def init_db():
    conn = sqlite3.connect('dados_frete.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (nome TEXT PRIMARY KEY, tabela_json TEXT, mapeamento_json TEXT, cidades_json TEXT)''')
    conn.commit()
    conn.close()

def salvar_transportadora(nome, df_tabela, df_cidades, mapeamento):
    conn = sqlite3.connect('dados_frete.db')
    tabela_json = df_tabela.to_json(orient='split')
    cidades_json = df_cidades.to_json(orient='split')
    mapeamento_json = json.dumps(mapeamento)
    conn.execute("INSERT OR REPLACE INTO transportadoras VALUES (?, ?, ?, ?)", 
                 (nome.upper(), tabela_json, mapeamento_json, cidades_json))
    conn.commit()
    conn.close()

def listar_transportadoras():
    try:
        conn = sqlite3.connect('dados_frete.db')
        df = pd.read_sql_query("SELECT nome FROM transportadoras", conn)
        conn.close()
        return df['nome'].tolist()
    except: return []

def carregar_transp(nome):
    conn = sqlite3.connect('dados_frete.db')
    cur = conn.cursor()
    cur.execute("SELECT tabela_json, mapeamento_json, cidades_json FROM transportadoras WHERE nome=?", (nome,))
    res = cur.fetchone()
    conn.close()
    # Correção do FileNotFoundError: usando io.StringIO para ler o JSON como string
    df_t = pd.read_json(io.StringIO(res[0]), orient='split')
    df_c = pd.read_json(io.StringIO(res[2]), orient='split')
    return df_t, json.loads(res[1]), df_c

init_db()

# --- NAVEGAÇÃO ---
st.title("🛡️ Sistema de Auditoria de Fretes")

aba1, aba2, aba3 = st.tabs(["📊 Dashboard Geral", "🚛 Cadastro de Transportadora", "📝 Auditoria de Notas"])

# --- ABA 1: DASHBOARD ---
with aba1:
    st.subheader("Painel de Controle")
    transp_ativas = listar_transportadoras()
    
    c_m1, c_m2 = st.columns(2)
    c_m1.metric("Transportadoras Cadastradas", len(transp_ativas))
    
    if transp_ativas:
        st.write("### Comparativo por Região (Tabela Dinâmica)")
        dados_resumo = []
        for t in transp_ativas:
            df_t, map_t, _ = carregar_transp(t)
            # Busca a primeira coluna de peso mapeada para o dash
            col_exemplo = map_t['c_faixas'][0]
            for _, row in df_t.iterrows():
                dados_resumo.append({
                    "Região/Sigla": row[map_t['c_sigla_f']],
                    "Transportadora": t,
                    "Vlr. Frete Base": row[col_exemplo]
                })
        
        df_dash = pd.DataFrame(dados_resumo)
        pivot = df_dash.pivot_table(index="Região/Sigla", columns="Transportadora", values="Vlr. Frete Base")
        st.dataframe(pivot.style.highlight_max(axis=1, color='#ffcccc').highlight_min(axis=1, color='#ccffcc'))
    else:
        st.info("Cadastre sua primeira transportadora na aba ao lado.")

# --- ABA 2: CADASTRO (Tabelas Salvas) ---
with aba2:
    st.subheader("Configurar Nova Transportadora")
    with st.expander("Passo 1: Identificação"):
        nome_transp = st.text_input("Nome da Transportadora").upper()

    col_u1, col_u2 = st.columns(2)
    with col_u1:
        st.markdown("**📁 Planilha de CIDADES**")
        f_cidades = st.file_uploader("Suba a lista de cidades/siglas desta transportadora", type=["xlsx"], key="up_cid")
    with col_u2:
        st.markdown("**📁 Planilha de PREÇOS**")
        f_frete = st.file_uploader("Suba a tabela de preços (E até K) desta transportadora", type=["xlsx"], key="up_pre")

    if f_frete and f_cidades and nome_transp:
        df_f = pd.read_excel(f_frete).fillna(0)
        df_c = pd.read_excel(f_cidades).fillna(0)

        st.divider()
        st.subheader(f"⚙️ Mapeamento para {nome_transp}")
        
        m1, m2 = st.columns(2)
        with m1:
            st.markdown(f"**[PLANILHA CIDADES]** - Mapeie as colunas de origem")
            c_cid_ref = st.selectbox("Coluna da CIDADE", df_c.columns)
            c_sigla_ref = st.selectbox("Coluna da SIGLA/TARIFA", df_c.columns)
            
            st.markdown(f"**[TABELA PREÇOS]** - Localização")
            c_sigla_f = st.selectbox("Coluna que contém a SIGLA na Tabela de Preços", df_f.columns)
            c_faixas = st.multiselect("Selecione as Colunas de PESO (Ex: 10, 20... até 100)", df_f.columns)
            c_exc = st.selectbox("Coluna do VALOR EXCEDENTE (Acima de 100kg)", df_f.columns)

        with m2:
            st.markdown(f"**[TABELA PREÇOS]** - Taxas")
            c_adv_p = st.selectbox("Coluna AD VALOREM %", df_f.columns)
            c_adv_m = st.selectbox("Coluna AD VALOREM MÍNIMO", df_f.columns)
            c_tas = st.selectbox("Coluna TAS", df_f.columns)
            c_gris_p = st.selectbox("Coluna GRIS % (Se houver na tabela)", ["Não possui"] + list(df_f.columns))
            c_pedagio_val = st.number_input("Valor Pedágio padrão por fração 100kg", value=14.70)

        if st.button("💾 SALVAR TRANSPORTADORA DEFINITIVAMENTE"):
            mapeamento = {
                "c_cid_ref": c_cid_ref, "c_sigla_ref": c_sigla_ref, "c_sigla_f": c_sigla_f,
                "c_faixas": c_faixas, "c_exc": c_exc, "c_adv_p": c_adv_p, "c_adv_m": c_adv_m,
                "c_tas": c_tas, "c_gris_p": c_gris_p, "c_pedagio_val": c_pedagio_val
            }
            salvar_transportadora(nome_transp, df_f, df_c, mapeamento)
            st.success(f"Transportadora {nome_transp} cadastrada e salva!")

# --- ABA 3: AUDITORIA ---
with aba3:
    st.subheader("Realizar Auditoria")
    f_base = st.file_uploader("📥 Suba sua PLANILHA BASE (Notas a auditar)", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        lista_t = listar_transportadoras()
        
        if not lista_t:
            st.warning("Nenhuma transportadora salva. Vá na aba de Cadastro primeiro.")
        else:
            t_escolhida = st.selectbox("Escolha a Transportadora para cálculo", lista_t)
            df_precos, mapa, df_cidades_salva = carregar_transp(t_escolhida)

            st.write(f"**Mapeamento da Planilha Base para {t_escolhida}**")
            b1, b2, b3 = st.columns(3)
            with b1: c_cid_b = st.selectbox("Coluna Cidade Destino (Base)", df_b.columns)
            with b2: c_peso_b = st.selectbox("Coluna Peso Real (Base)", df_b.columns)
            with b3: c_val_b = st.selectbox("Coluna Valor NF (Base)", df_b.columns)

            if st.button("🔍 Calcular Fretes"):
                def calcular_completo(row):
                    try:
                        cid = str(row[c_cid_b]).strip().upper()
                        peso = float(row[c_peso_b])
                        valor_nf = float(row[c_val_b])

                        # 1. Busca Sigla na tabela de cidades salva
                        sigla = df_cidades_salva[df_cidades_salva[mapa['c_cid_ref']].str.upper() == cid][mapa['c_sigla_ref']].values[0]
                        
                        # 2. Busca Linha de Preço
                        f_row = df_precos[df_precos[mapa['c_sigla_f']] == sigla].iloc[0]

                        # 3. Lógica de Peso (Conforme sua fórmula)
                        if peso <= 100:
                            # Encontra a faixa correta
                            faixas_nomes = mapa['c_faixas']
                            faixas_num = sorted([int(''.join(filter(str.isdigit, str(c)))) for c in faixas_nomes])
                            col_escolhida = faixas_nomes[-1]
                            for n in faixas_num:
                                if peso <= n:
                                    col_escolhida = [c for c in faixas_nomes if str(n) in str(c)][0]
                                    break
                            frete_peso = float(f_row[col_escolhida])
                        else:
                            valor_100 = float(f_row[mapa['c_faixas'][-1]])
                            valor_exc = float(f_row[mapa['c_exc']])
                            frete_peso = valor_100 + ((peso - 100) * valor_exc)

                        # 4. Taxas Dinâmicas
                        taxa_adv = max(valor_nf * (float(f_row[mapa['c_adv_p']]) / 100), float(f_row[mapa['c_adv_m']]))
                        taxa_tas = float(f_row[mapa['c_tas']])
                        taxa_pedagio = math.ceil(peso / 100) * mapa['c_pedagio_val']
                        taxa_fixa_excel = 7.41 # Valor fixo da sua fórmula

                        total = frete_peso + taxa_adv + taxa_tas + taxa_pedagio + taxa_fixa_excel
                        
                        detalhes = f"Peso: {peso}kg | Frete Peso: {frete_peso} | AdVal: {taxa_adv} | TAS: {taxa_tas} | Pedágio: {taxa_pedagio}"
                        return pd.Series([sigla, frete_peso, taxa_adv, taxa_pedagio, total, detalhes])
                    except:
                        return pd.Series(["Não encontrado", 0, 0, 0, 0, "Verifique se a cidade existe na planilha de cidades"])

                df_b[['Sigla', 'F. Peso', 'AdVal', 'Pedágio', 'TOTAL', 'DETALHES']] = df_b.apply(calcular_completo, axis=1)
                
                # Exibição com o "Olho"
                for i, row in df_b.iterrows():
                    res_col1, res_col2, res_col3 = st.columns([6, 2, 1])
                    res_col1.write(f"📍 {row[c_cid_b]} | {row['Sigla']}")
                    res_col2.write(f"**R$ {row['TOTAL']:.2f}**")
                    if res_col3.button("👁️", key=f"olho_{i}"):
                        st.info(row['DETALHES'])

                csv = df_b.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Baixar Planilha Auditada", csv, "auditoria_final.csv")
