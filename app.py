import streamlit as st
import pandas as pd
import math
import sqlite3
import json
import io

st.set_page_config(page_title="Auditor de Frete Pro", layout="wide")

# --- BANCO DE DADOS (Versão 2 para evitar erro de coluna) ---
def init_db():
    conn = sqlite3.connect('dados_frete_v2.db') # Nome alterado para resetar estrutura
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (nome TEXT PRIMARY KEY, tabela_json TEXT, mapeamento_json TEXT, cidades_json TEXT)''')
    conn.commit()
    conn.close()

def salvar_transportadora(nome, df_tabela, df_cidades, mapeamento):
    conn = sqlite3.connect('dados_frete_v2.db')
    tabela_json = df_tabela.to_json(orient='split')
    cidades_json = df_cidades.to_json(orient='split')
    mapeamento_json = json.dumps(mapeamento)
    conn.execute("INSERT OR REPLACE INTO transportadoras VALUES (?, ?, ?, ?)", 
                 (nome.upper(), tabela_json, mapeamento_json, cidades_json))
    conn.commit()
    conn.close()

def listar_transportadoras():
    try:
        conn = sqlite3.connect('dados_frete_v2.db')
        df = pd.read_sql_query("SELECT nome FROM transportadoras", conn)
        conn.close()
        return df['nome'].tolist()
    except: return []

def carregar_transp(nome):
    conn = sqlite3.connect('dados_frete_v2.db')
    cur = conn.cursor()
    cur.execute("SELECT tabela_json, mapeamento_json, cidades_json FROM transportadoras WHERE nome=?", (nome,))
    res = cur.fetchone()
    conn.close()
    df_t = pd.read_json(io.StringIO(res[0]), orient='split')
    df_c = pd.read_json(io.StringIO(res[2]), orient='split')
    return df_t, json.loads(res[1]), df_c

init_db()

# --- NAVEGAÇÃO ---
aba1, aba2, aba3 = st.tabs(["📊 Dashboard Geral", "🚛 Cadastro de Transportadora", "📝 Auditoria de Notas"])

# --- ABA 1: DASHBOARD ---
with aba1:
    st.subheader("Dashboard de Transportadoras")
    transp_ativas = listar_transportadoras()
    if transp_ativas:
        dados_resumo = []
        for t in transp_ativas:
            df_t, map_t, _ = carregar_transp(t)
            col_ref = map_t['c_faixas'][0]
            for _, row in df_t.iterrows():
                dados_resumo.append({"Região": row[map_t['c_sigla_f']], "Transportadora": t, "Valor": row[col_ref]})
        df_dash = pd.DataFrame(dados_resumo)
        st.write("**Tabela Dinâmica: Região vs Transportadora**")
        st.dataframe(df_dash.pivot_table(index="Região", columns="Transportadora", values="Valor"))
    else:
        st.info("Nenhuma transportadora cadastrada.")

# --- ABA 2: CADASTRO ---
with aba2:
    st.subheader("Cadastrar Nova Transportadora")
    nome_t = st.text_input("Nome da Transportadora").upper()
    
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        st.markdown("**1. Planilha de CIDADES**")
        f_cid = st.file_uploader("Suba a planilha de cidades/siglas", type=["xlsx"], key="u_cid")
    with col_u2:
        st.markdown("**2. Planilha de PREÇOS**")
        f_pre = st.file_uploader("Suba a tabela de preços", type=["xlsx"], key="u_pre")

    if f_cid and f_pre and nome_t:
        df_c = pd.read_excel(f_cid).fillna(0)
        df_p = pd.read_excel(f_pre).fillna(0)
        
        st.divider()
        st.subheader("Mapeamento das Planilhas")
        m1, m2 = st.columns(2)
        with m1:
            st.write("**[MAPEAR PLANILHA CIDADES]**")
            c_cid_ref = st.selectbox("Coluna CIDADE", df_c.columns)
            c_sigla_ref = st.selectbox("Coluna SIGLA", df_c.columns)
            
            st.write("**[MAPEAR TABELA PREÇOS]**")
            c_sigla_f = st.selectbox("Coluna SIGLA na Tabela de Preços", df_p.columns)
            c_faixas = st.multiselect("Colunas de PESO (E até J)", df_p.columns)
            c_exc = st.selectbox("Coluna EXCEDENTE (K)", df_p.columns)
        
        with m2:
            st.write("**[MAPEAR TAXAS DA TABELA]**")
            c_adv_p = st.selectbox("Ad Valorem % (Coluna L)", df_p.columns)
            c_adv_m = st.selectbox("Ad Valorem Mínimo (Coluna M)", df_p.columns)
            c_tas = st.selectbox("TAS (Coluna N)", df_p.columns)
            
        if st.button("💾 SALVAR E MANTER TRANSPORTADORA"):
            mapeamento = {
                "c_cid_ref": c_cid_ref, "c_sigla_ref": c_sigla_ref, "c_sigla_f": c_sigla_f,
                "c_faixas": c_faixas, "c_exc": c_exc, "c_adv_p": c_adv_p, "c_adv_m": c_adv_m, "c_tas": c_tas
            }
            salvar_transportadora(nome_t, df_p, df_c, mapeamento)
            st.success("Salvo com sucesso!")

# --- ABA 3: AUDITORIA ---
with aba3:
    st.subheader("Auditoria de Movimentação")
    f_base = st.file_uploader("Suba sua Planilha Base fixa", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        lista_t = listar_transportadoras()
        t_sel = st.selectbox("Selecione a Transportadora Salva", lista_t)
        
        if t_sel:
            df_p, mapa, df_c = carregar_transp(t_sel)
            st.write("**Mapear Planilha Base**")
            b1, b2, b3, b4 = st.columns(4)
            with b1: c_cid_b = st.selectbox("Coluna Cidade", df_b.columns)
            with b2: c_uf_b = st.selectbox("Coluna UF", df_b.columns)
            with b3: c_peso_b = st.selectbox("Coluna Peso", df_b.columns)
            with b4: c_val_b = st.selectbox("Coluna Valor NF", df_b.columns)

            if st.button("🔍 Calcular"):
                def calcular(row):
                    try:
                        cid = str(row[c_cid_b]).strip().upper()
                        uf = str(row[c_uf_b]).strip().upper()
                        peso = float(row[c_peso_b])
                        v_nf = float(row[c_val_b])

                        sigla = df_c[df_c[mapa['c_cid_ref']].str.upper() == cid][mapa['c_sigla_ref']].values[0]
                        f_row = df_p[df_p[mapa['c_sigla_f']] == sigla].iloc[0]

                        # FRETE PESO
                        if peso <= 100:
                            f_nomes = mapa['c_faixas']
                            f_nums = sorted([int(''.join(filter(str.isdigit, str(c)))) for c in f_nomes])
                            col = f_nomes[-1]
                            for n in f_nums:
                                if peso <= n:
                                    col = [c for c in f_nomes if str(n) in str(c)][0]
                                    break
                            frete_peso = float(f_row[col])
                        else:
                            frete_peso = float(f_row[mapa['c_faixas'][-1]]) + ((peso-100) * float(f_row[mapa['c_exc']]))

                        # TAXAS DA FÓRMULA EXCEL
                        adv = max(v_nf * (float(f_row[mapa['c_adv_p']])), float(f_row[mapa['c_adv_m']]))
                        pedagio = math.ceil(peso/100) * 14.70
                        tas = float(f_row[mapa['c_tas']])
                        fixa = 7.41 
                        gris = max(v_nf * 0.0016, 4.36)
                        
                        # REGRA RJ
                        rj_extra = 0
                        if uf == "RJ":
                            rj_extra += max(v_nf * 0.0021, 6.87)
                        
                        total = frete_peso + adv + pedagio + tas + fixa + gris + rj_extra
                        detalhes = f"F.Peso: {frete_peso} | Adv: {adv} | Ped: {pedagio} | TAS: {tas} | Fixa: 7.41 | Gris: {gris} | RJ: {rj_extra}"
                        return pd.Series([sigla, total, detalhes])
                    except: return pd.Series(["Erro", 0, "Cidade não encontrada"])

                df_b[['Sigla', 'TOTAL', 'DETALHES']] = df_b.apply(calcular, axis=1)
                
                for i, r in df_b.iterrows():
                    c1, c2, c3 = st.columns([6, 2, 1])
                    c1.write(f"📍 {r[c_cid_b]} ({r['Sigla']})")
                    c2.write(f"**R$ {r['TOTAL']:.2f}**")
                    if c3.button("👁️", key=f"olho_{i}"): st.info(r['DETALHES'])

                st.download_button("📥 Baixar Resultado", df_b.to_csv(index=False).encode('utf-8-sig'), "auditoria.csv")
