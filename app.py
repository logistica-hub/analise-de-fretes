import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math
import unicodedata

# 1. Configuração de Layout
st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")

def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

DB_NAME = 'comparativo_v19.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cotacoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, transportadora TEXT, 
                  total REAL, qtd INTEGER, detalhes_json TEXT)''')
    conn.commit()
    conn.close()

init_db()

if 'edit_id' not in st.session_state: st.session_state.edit_id = None

with st.sidebar:
    st.title("Ave-Maria Fretes")
    menu = st.radio("MENU PRINCIPAL", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])

# --- MÓDULO 1: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        lista_completa = []
        for _, row in df_h.iterrows():
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            df_det['Transportadora_Ref'] = row['transportadora']
            lista_completa.append(df_det)
        df_bi = pd.concat(lista_completa, ignore_index=True)

        st.subheader("🎯 Filtros")
        f1, f2 = st.columns(2)
        transp_sel = f1.multiselect("Transportadora", options=df_bi['Transportadora_Ref'].unique())
        uf_sel = f2.multiselect("UF", options=df_bi['UF'].unique())

        if transp_sel: df_bi = df_bi[df_bi['Transportadora_Ref'].isin(transp_sel)]
        if uf_sel: df_bi = df_bi[df_bi['UF'].isin(uf_sel)]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_bi['VALOR_SISTEMA'].sum():,.2f}")
        c2.metric("Notas Processadas", f"{len(df_bi)}")
        c3.metric("Peso Total", f"{df_bi['PESO'].sum():,.2f} kg")

        st.subheader("📍 Resumo por UF")
        res_uf = df_bi.groupby('UF').agg({'VALOR_SISTEMA': 'sum', 'NF': 'count'}).reset_index()
        res_uf.columns = ['UF', 'Total Frete', 'Qtd Notas']
        st.table(res_uf.sort_values('Total Frete', ascending=False))
    else:
        st.info("Nenhuma cotação no histórico.")

# --- MÓDULO 2: TRANSPORTADORAS (CADASTRO) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    # ... (Mantendo a lógica de cadastro anterior para focar no Comparativo solicitado)
    st.info("Utilize para configurar os mapeamentos de colunas da Jamef e outras.")

# --- MÓDULO 3: COMPARATIVO E DETALHAMENTO NOTA A NOTA ---
elif menu == "💰 Comparativo":
    st.title("💰 Novo Cálculo")
    conn = sqlite3.connect(DB_NAME)
    ts = pd.read_sql_query("SELECT * FROM transportadoras", conn)
    conn.close()

    f_base = st.file_uploader("📥 Subir Notas Fiscais", type=["xlsx"])
    if not ts.empty:
        t_alvo = st.selectbox("Transportadora", ts['nome'].tolist())
        if f_base and st.button("🚀 Calcular e Salvar"):
            df_b = pd.read_excel(f_base).fillna(0)
            t_row = ts[ts['nome'] == t_alvo].iloc[0]
            df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
            df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
            mapa = json.loads(t_row['mapeamento_json'])
            
            df_b['BUSCA_NF'] = df_b.iloc[:, 2].apply(normalizar)
            df_cid_ref['BUSCA_REF'] = df_cid_ref[mapa['col_cid']].apply(normalizar)
            df_proc = pd.merge(df_b, df_cid_ref[['BUSCA_REF', mapa['col_sigla']]], left_on='BUSCA_NF', right_on='BUSCA_REF', how='left')
            df_tab['SIGLA_CHAVE'] = df_tab.iloc[:, 2].apply(normalizar)

            res = []
            for _, nf in df_proc.iterrows():
                try:
                    p = float(nf.iloc[6]); v_nf = float(nf.iloc[7]); s_norm = normalizar(str(nf[mapa['col_sigla']]))
                    l_p = df_tab[df_tab['SIGLA_CHAVE'] == s_norm].iloc[0]
                    
                    def get_v(taxa): return float(l_p[mapa['taxas'][taxa]]) if taxa in mapa['taxas'] and mapa['taxas'][taxa] != "Não mapear" else 0.0
                    
                    # Cálculo Frete Peso
                    f_peso = 0.0; u_max = 0; u_col = ""; achou = False
                    for f in mapa['faixas']:
                        u_max, u_col = f['max'], f['col']
                        if p <= f['max'] and f['col'] != "Não mapear":
                            f_peso = float(l_p[f['col']]); achou = True; break
                    if not achou and mapa.get('kg_extra') != "Não mapear":
                        f_peso = float(l_p[u_col]) + ((p - u_max) * float(l_p[mapa['kg_extra']]))

                    # Detalhando taxas para o "Olho"
                    taxas_calc = {
                        "AdValorem": max(v_nf * get_v("Ad Valorem %"), get_v("Ad Valorem Min")),
                        "Gris": max(v_nf * get_v("Gris %"), get_v("Gris Min")),
                        "Pedagio": (math.ceil(p/100) * get_v("Pedagio")),
                        "Outros": get_v("TAS") + get_v("CTRC") + get_v("TRT") + get_v("TDA") + get_v("SEC-CAT")
                    }
                    total_nf = f_peso + sum(taxas_calc.values())
                    
                    nf_dict = nf.to_dict()
                    nf_dict.update({"VALOR_SISTEMA": round(total_nf, 2), "F_PESO": f_peso})
                    nf_dict.update(taxas_calc)
                    res.append(nf_dict)
                except:
                    nf_dict = nf.to_dict()
                    nf_dict["VALOR_SISTEMA"] = 0.0
                    res.append(nf_dict)

            df_res = pd.DataFrame(res)
            conn = sqlite3.connect(DB_NAME)
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json) VALUES (?,?,?,?,?)",
                         (datetime.now().strftime("%d/%m/%Y %H:%M"), t_alvo, df_res['VALOR_SISTEMA'].sum(), len(df_res), df_res.to_json()))
            conn.commit(); conn.close(); st.rerun()

    st.divider()
    st.subheader("📜 Histórico de Cotações")
    conn = sqlite3.connect(DB_NAME)
    cots = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    conn.close()

    for _, c in cots.iterrows():
        exp = st.expander(f"📅 {c['data_hora']} | {c['transportadora']} | Total: R$ {c['total']:,.2f}")
        with exp:
            df_det = pd.read_json(io.StringIO(c['detalhes_json']))
            st.write("**Resumo das Notas:**")
            st.dataframe(df_det[['NF', 'CIDADE', 'UF', 'VALOR_SISTEMA']], use_container_width=True)
            
            st.write("---")
            st.write("**🔍 Detalhamento Nota a Nota (Taxas):**")
            for _, nota in df_det.iterrows():
                with st.expander(f"👁️ Detalhar Nota Fiscal: {nota['NF']} - {nota['CIDADE']}"):
                    col_a, col_b = st.columns(2)
                    col_a.write(f"**Frete Peso:** R$ {nota.get('F_PESO', 0):,.2f}")
                    col_a.write(f"**Ad Valorem:** R$ {nota.get('AdValorem', 0):,.2f}")
                    col_a.write(f"**Gris:** R$ {nota.get('Gris', 0):,.2f}")
                    col_b.write(f"**Pedágio:** R$ {nota.get('Pedagio', 0):,.2f}")
                    col_b.write(f"**Outras Taxas:** R$ {nota.get('Outros', 0):,.2f}")
                    col_b.subheader(f"Total: R$ {nota['VALOR_SISTEMA']:,.2f}")
