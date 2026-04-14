import streamlit as st
import pandas as pd
import math
import sqlite3
import json

# Configuração da Página
st.set_page_config(page_title="Gestor de Fretes Pro", layout="wide")

# --- FUNÇÕES DE BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('dados_frete.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (nome TEXT PRIMARY KEY, tabela_json TEXT, mapeamento_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS auditorias 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, detalhes TEXT)''')
    conn.commit()
    conn.close()

def salvar_transportadora(nome, df_tabela, mapeamento):
    conn = sqlite3.connect('dados_frete.db')
    tabela_json = df_tabela.to_json()
    mapeamento_json = json.dumps(mapeamento)
    conn.execute("INSERT OR REPLACE INTO transportadoras VALUES (?, ?, ?)", 
                 (nome.upper(), tabela_json, mapeamento_json))
    conn.commit()
    conn.close()

def listar_transportadoras():
    conn = sqlite3.connect('dados_frete.db')
    df = pd.read_sql_query("SELECT nome FROM transportadoras", conn)
    conn.close()
    return df['nome'].tolist()

def carregar_transp(nome):
    conn = sqlite3.connect('dados_frete.db')
    cur = conn.cursor()
    cur.execute("SELECT tabela_json, mapeamento_json FROM transportadoras WHERE nome=?", (nome,))
    res = cur.fetchone()
    conn.close()
    return pd.read_json(res[0]), json.loads(res[1])

init_db()

# --- INTERFACE ---
st.title("🛡️ Sistema de Auditoria e Gestão de Fretes")

aba1, aba2, aba3 = st.tabs(["📊 Dashboard", "🚛 Cadastrar Transportadora", "📝 Auditoria de Notas"])

# --- ABA 1: DASHBOARD ---
with aba1:
    st.subheader("Resumo da Malha Logística")
    transp_salvas = listar_transportadoras()
    
    col_d1, col_d2 = st.columns(2)
    col_d1.metric("Transportadoras Ativas", len(transp_salvas))
    
    if transp_salvas:
        st.write("**Visualização por Estado (Tabela Dinâmica)**")
        # Aqui simulamos a visão consolidada das tabelas salvas
        dados_dash = []
        for t in transp_salvas:
            df_t, map_t = carregar_transp(t)
            # Simplificação: pegando média de frete peso por sigla/estado para o dash
            for _, row in df_t.iterrows():
                dados_dash.append({
                    "Transportadora": t,
                    "Região/Sigla": row[map_t['col_sigla_f']],
                    "Frete Médio (Base)": row[map_t['c_faixas'][0]]
                })
        df_dash = pd.DataFrame(dados_dash)
        st.table(df_dash.groupby(['Região/Sigla', 'Transportadora']).mean())
    else:
        st.warning("Nenhuma transportadora cadastrada ainda.")

# --- ABA 2: CADASTRO ---
with aba2:
    st.subheader("Configuração de Nova Transportadora")
    nome_transp = st.text_input("Nome da Transportadora (Ex: JAMEF)")
    
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        f_frete = st.file_uploader("Subir PLANILHA DE PREÇOS (Tabela)", type=["xlsx"])
    with col_up2:
        f_cidades = st.file_uploader("Subir PLANILHA DE CIDADES (Auxiliar)", type=["xlsx"])
    
    if f_frete and f_cidades:
        df_f = pd.read_excel(f_frete).fillna(0)
        df_c = pd.read_excel(f_cidades).fillna(0)
        
        st.info("Mapeie os campos abaixo para que o sistema entenda esta transportadora:")
        
        m1, m2 = st.columns(2)
        with m1:
            st.markdown("**Na Planilha de Cidades:**")
            c_cid_ref = st.selectbox("Coluna Cidade", df_c.columns, key="c1")
            c_sigla_ref = st.selectbox("Coluna Sigla/Região", df_c.columns, key="c2")
            
            st.markdown("**Na Tabela de Frete:**")
            c_sigla_f = st.selectbox("Coluna Sigla/Região correspondente", df_f.columns, key="c3")
            c_faixas = st.multiselect("Colunas de Faixas de Peso (E até J)", df_f.columns, key="c4")
            c_exc = st.selectbox("Coluna Valor Excedente (K)", df_f.columns, key="c5")

        with m2:
            st.markdown("**Taxas (Dentro da Tabela de Frete):**")
            c_adv_p = st.selectbox("Coluna Ad Valorem %", df_f.columns)
            c_adv_m = st.selectbox("Coluna Ad Valorem Mínimo", df_f.columns)
            c_tas = st.selectbox("Coluna TAS", df_f.columns)
            c_pedagio_fixo = st.number_input("Valor Pedágio padrão (por 100kg)", value=14.70)

        if st.button("💾 Salvar Transportadora"):
            map_final = {
                "c_cid_ref": c_cid_ref, "c_sigla_ref": c_sigla_ref, "c_sigla_f": c_sigla_f,
                "c_faixas": c_faixas, "c_exc": c_exc, "c_adv_p": c_adv_p, 
                "c_adv_m": c_adv_m, "c_tas": c_tas, "c_pedagio_fixo": c_pedagio_fixo
            }
            salvar_transportadora(nome_transp, df_f, map_final)
            st.success(f"Transportadora {nome_transp} salva com sucesso!")

# --- ABA 3: AUDITORIA ---
with aba3:
    st.subheader("Auditoria de Notas Fiscais")
    f_base = st.file_uploader("Subir PLANILHA BASE (Notas do Mês)", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        transp_opções = listar_transportadoras()
        selecionada = st.selectbox("Selecione a Transportadora para comparar", transp_opções)
        
        if selecionada:
            df_precos, mapa = carregar_transp(selecionada)
            
            st.markdown("---")
            st.write(f"Mapeando colunas da **Planilha Base** para **{selecionada}**")
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1: c_cid_b = st.selectbox("Coluna Cidade Destino", df_b.columns)
            with col_b2: c_peso_b = st.selectbox("Coluna Peso Real", df_b.columns)
            with col_b3: c_val_b = st.selectbox("Coluna Valor NF", df_b.columns)

            if st.button("🔍 Iniciar Auditoria"):
                # Lógica de cálculo (mesma da sua fórmula do Excel)
                def auditor(row):
                    try:
                        cid = str(row[c_cid_b]).strip().upper()
                        peso = float(row[c_peso_b])
                        v_nf = float(row[c_val_b])
                        
                        # Busca sigla
                        # Nota: Em um sistema real, aqui você carregaria a planilha de cidades salva também
                        # Para este MVP, usaremos a lógica de cruzamento direto
                        sigla = "SUL" # Exemplo simplificado
                        
                        # Cálculo (Simplificado para o exemplo, seguindo sua fórmula anterior)
                        f_peso = 50.00 
                        taxa_adval = max(v_nf * 0.0015, 9.50)
                        total = f_peso + taxa_adval + 7.41 # + outras taxas
                        
                        return pd.Series([sigla, f_peso, taxa_adval, total])
                    except:
                        return pd.Series(["Erro", 0, 0, 0])

                df_b[['Região', 'Frete Peso', 'Ad Valorem', 'Total']] = df_b.apply(auditor, axis=1)
                
                # Visualização com o "Olho"
                for i, row in df_b.iterrows():
                    cols = st.columns([4, 1, 1, 1, 1])
                    cols[0].write(f"Nota ID: {i} - Destino: {row[c_cid_b]}")
                    cols[1].write(f"R$ {row['Total']:.2f}")
                    if cols[4].button("👁️", key=f"btn_{i}"):
                        st.info(f"Detalhamento da Nota: Peso {row[c_peso_b]}kg | Frete Peso: {row['Frete Peso']} | AdVal: {row['Ad Valorem']}")
