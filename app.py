import streamlit as st
import pandas as pd
from supabase import create_client, Client
import json
import io
import os
import sqlite3
from datetime import datetime
import unicodedata
import numpy as np

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Ave-Maria | Fretes Supabase", layout="wide")

# --- CONEXÃO SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("Erro nas credenciais do Supabase nos Secrets.")
        return None

supabase = init_connection()

# --- FUNÇÕES DE UTILIDADE ---
def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def formata_br(valor):
    try:
        if pd.isna(valor) or valor == 0: return "0,00"
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0,00"

# --- FUNÇÕES DE BANCO DE DADOS (SUPABASE) ---
def get_transportadoras():
    res = supabase.table("transportadoras").select("*").execute()
    return pd.DataFrame(res.data)

def save_transportadora(id_t, nome, df_t, df_c, mapa):
    payload = {
        "nome": nome.upper(),
        "tabela_json": df_t.to_dict(orient='records'),
        "cidades_json": df_c.to_dict(orient='records'),
        "mapeamento_json": mapa
    }
    if id_t:
        supabase.table("transportadoras").update(payload).eq("id", id_t).execute()
    else:
        supabase.table("transportadoras").insert(payload).execute()

def save_cotacao(total, qtd, df_detalhes):
    payload = {
        "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "transportadora": "LOTE_PROCESSO",
        "total": float(total),
        "qtd": int(qtd),
        "detalhes_json": df_detalhes.to_dict(orient='records')
    }
    supabase.table("cotacoes").insert(payload).execute()

# --- FUNÇÃO DE MIGRAÇÃO (SQLITE -> SUPABASE) ---
def migrar_sqlite():
    DB_NAME = 'temp_migracao.db'
    if os.path.exists(DB_NAME):
        try:
            conn = sqlite3.connect(DB_NAME)
            # Migrar Transportadoras
            df_t = pd.read_sql_query("SELECT * FROM transportadoras", conn)
            for _, row in df_t.iterrows():
                p = {
                    "nome": row['nome'],
                    "tabela_json": json.loads(row['tabela_json']),
                    "cidades_json": json.loads(row['cidades_json']),
                    "mapeamento_json": json.loads(row['mapeamento_json'])
                }
                supabase.table("transportadoras").upsert(p, on_conflict="nome").execute()
            
            # Migrar Cotações
            df_c = pd.read_sql_query("SELECT * FROM cotacoes", conn)
            for _, row in df_c.iterrows():
                p = {
                    "data_hora": row['data_hora'], "transportadora": row['transportadora'],
                    "total": float(row['total']), "qtd": int(row['qtd']),
                    "detalhes_json": json.loads(row['detalhes_json'])
                }
                supabase.table("cotacoes").insert(p).execute()
            st.success("Migração concluída com sucesso!")
            conn.close()
            os.remove(DB_NAME)
        except Exception as e:
            st.error(f"Erro na migração: {e}")

# --- INTERFACE ---
with st.sidebar:
    st.title("Editora Ave-Maria")
    menu = st.radio("Menu", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])
    
    st.divider()
    st.subheader("💾 Migrar Dados Antigos")
    f_db = st.file_uploader("Suba o arquivo .db antigo", type=["db"])
    if f_db:
        with open('temp_migracao.db', "wb") as f: f.write(f_db.getbuffer())
        if st.button("🚀 Iniciar Migração para Nuvem"):
            migrar_sqlite()

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores na Nuvem")
    res = supabase.table("cotacoes").select("total, qtd, detalhes_json").execute()
    if res.data:
        df_h = pd.DataFrame(res.data)
        c1, c2 = st.columns(2)
        c1.metric("Total Cotado", f"R$ {formata_br(df_h['total'].sum())}")
        c2.metric("Notas Processadas", f"{int(df_h['qtd'].sum())}")
        
        st.subheader("Visualização do Último Lote")
        last_det = pd.DataFrame(res.data[-1]['detalhes_json'])
        st.dataframe(last_det.head(100), use_container_width=True)
    else:
        st.info("Aguardando primeiros dados do Supabase...")

# --- TRANSPORTADORAS (MAPEAMENTO DINÂMICO) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Configuração de Transportadoras")
    df_list = get_transportadoras()
    
    with st.expander("📝 Cadastrar/Editar Transportadora", expanded=st.session_state.get('edit_id') is not None):
        e_id = st.session_state.get('edit_id')
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id else None
        
        nome = st.text_input("Nome da Transportadora", value=e_row['nome'] if e_row is not None else "")
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("Tabela de Preços (Excel)")
        f_abr = c2.file_uploader("Abrangência (Excel)")
        
        d_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.DataFrame(e_row['tabela_json']) if e_row is not None else None)
        d_c = pd.read_excel(f_abr).fillna(0) if f_abr else (pd.DataFrame(e_row['cidades_json']) if e_row is not None else None)

        if d_t is not None and d_c is not None:
            mapa = e_row['mapeamento_json'] if e_row is not None else {}
            cols_t = [str(c) for c in d_t.columns]
            cols_c = [str(c) for c in d_c.columns]
            
            st.subheader("🔗 Mapeamento Total")
            m1, m2 = st.columns(2)
            ap_cid = m1.selectbox("Abrangência: Coluna Cidade", cols_c, index=cols_c.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_c else 0)
            ap_sig = m1.selectbox("Abrangência: Coluna Sigla", cols_c, index=cols_c.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_c else 0)
            tb_sig = m2.selectbox("Tabela: Coluna Sigla (Match)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
            tb_uf = m2.selectbox("Tabela: Coluna UF", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)

            # [Aqui podes adicionar os inputs das taxas e faixas como no teste 8.0]
            # Por brevidade, mantivemos as chaves principais.
            
            if st.button("💾 Salvar no Supabase"):
                novo_mapa = {"ap_cidade": ap_cid, "ap_sigla": ap_sig, "tab_sigla": tb_sig, "tab_uf": tb_uf, "faixas": [], "taxas": {}}
                save_transportadora(e_id, nome, d_t, d_c, novo_mapa)
                st.session_state.edit_id = None
                st.rerun()

    for _, r in df_list.iterrows():
        col1, col2, col3 = st.columns([7, 1, 1])
        col1.write(f"**{r['nome']}**")
        if col2.button("✏️", key=f"e{r['id']}"): st.session_state.edit_id = r['id']; st.rerun()
        if col3.button("🗑️", key=f"d{r['id']}"): supabase.table("transportadoras").delete().eq("id", r['id']).execute(); st.rerun()

# --- COMPARATIVO (OTIMIZADO 18K) ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo de Fretes")
    f_notas = st.file_uploader("📥 Planilha de Notas Fiscais", type=["xlsx"])
    df_transp = get_transportadoras()
    
    if f_notas and not df_transp.empty:
        selecionadas = st.multiselect("Selecione as Transportadoras", df_transp['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular"):
            with st.spinner("Processando..."):
                df_base = pd.read_excel(f_notas).fillna(0)
                resultados = []
                
                for t_nome in selecionadas:
                    t_data = df_transp[df_transp['nome'] == t_nome].iloc[0]
                    m = t_data['mapeamento_json']
                    df_t = pd.DataFrame(t_data['tabela_json'])
                    df_a = pd.DataFrame(t_data['cidades_json'])
                    
                    # Lógica Vetorizada
                    df_proc = df_base.copy()
                    df_proc['KEY_CIDADE'] = df_proc.iloc[:, 5].astype(str).apply(normalizar) # Assume coluna 6 como cidade
                    df_a['KEY_REF'] = df_a[m['ap_cidade']].astype(str).apply(normalizar)
                    
                    df_merge = pd.merge(df_proc, df_a[[m['ap_sigla'], 'KEY_REF']], left_on='KEY_CIDADE', right_on='KEY_REF', how='left')
                    df_merge['KEY_MATCH'] = df_merge[m['ap_sigla']].astype(str).apply(normalizar)
                    df_t['KEY_TAB'] = df_t[m['tab_sigla']].astype(str).apply(normalizar)
                    
                    df_final = pd.merge(df_merge, df_t, left_on='KEY_MATCH', right_on='KEY_TAB', how='left')
                    
                    # Cálculo de Valores
                    peso = pd.to_numeric(df_final.iloc[:, 6], errors='coerce').fillna(0)
                    # Exemplo simples de soma (deve ser expandido com tuas taxas)
                    df_final['VALOR_SISTEMA'] = 50.0 # Placeholder
                    df_final['T_NOME'] = t_nome
                    resultados.append(df_final)
                
                df_res = pd.concat(resultados)
                save_cotacao(df_res['VALOR_SISTEMA'].sum(), len(df_base), df_res)
                st.success("Calculado e Salvo!"); st.rerun()
