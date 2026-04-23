import streamlit as st
import pandas as pd
from supabase import create_client, Client
import json
import io
import os
from datetime import datetime
import unicodedata
import numpy as np

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Ave-Maria | Fretes Oficial", layout="wide")

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- UTILITÁRIOS ---
def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def formata_br(valor):
    try:
        if pd.isna(valor) or valor == 0: return "0,00"
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0,00"

# --- BANCO DE DADOS ---
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

# --- INTERFACE ---
if 'edit_id' not in st.session_state: st.session_state.edit_id = None

with st.sidebar:
    st.title("Editora Ave-Maria")
    menu = st.radio("Menu", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])
    st.divider()
    st.caption("Conectado ao Supabase Cloud")

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Controle")
    res = supabase.table("cotacoes").select("*").order("id", desc=True).limit(1).execute()
    if res.data:
        lote = res.data[0]
        st.subheader(f"Último Lote: {lote['data_hora']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", f"R$ {formata_br(lote['total'])}")
        c2.metric("Notas", lote['qtd'])
        
        df_view = pd.DataFrame(lote['detalhes_json'])
        st.dataframe(df_view, use_container_width=True)
    else:
        st.info("Nenhum histórico disponível.")

# --- TRANSPORTADORAS (TESTE 8.0 RESTAURADO) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Configuração")
    df_list = get_transportadoras()
    
    with st.expander("📝 Mapeamento de Transportadora", expanded=st.session_state.edit_id is not None):
        e_id = st.session_state.edit_id
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id else None
        
        nome_t = st.text_input("Nome", value=e_row['nome'] if e_row is not None else "")
        f_t = st.file_uploader("Tabela de Preços")
        f_a = st.file_uploader("Abrangência")
        
        df_t = pd.read_excel(f_t).fillna(0) if f_t else (pd.DataFrame(e_row['tabela_json']) if e_row is not None else None)
        df_a = pd.read_excel(f_a).fillna(0) if f_a else (pd.DataFrame(e_row['cidades_json']) if e_row is not None else None)

        if df_t is not None and df_a is not None:
            mapa = e_row['mapeamento_json'] if e_row is not None else {"faixas": [], "taxas": {}}
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_c = ["Não mapear"] + [str(c) for c in df_a.columns]
            
            st.subheader("🔗 Ligações Chave")
            c1, c2 = st.columns(2)
            ap_cid = c1.selectbox("Abrangência: Coluna Cidade", cols_c, index=cols_c.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_c else 0)
            ap_sig = c1.selectbox("Abrangência: Coluna Sigla", cols_c, index=cols_c.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_c else 0)
            tb_sig = c2.selectbox("Tabela: Coluna Sigla (Match)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
            tb_uf = c2.selectbox("Tabela: Coluna UF", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)

            st.subheader("⚖️ Pesos e Faixas")
            kg_ex = st.selectbox("Preço Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            qtd_f = st.number_input("Qtd Faixas", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(qtd_f)):
                r = st.columns(3)
                f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({
                    "min": r[0].number_input("De", value=float(f_i.get('min', 0.0)), key=f"min{i}"),
                    "max": r[1].number_input("Até", value=float(f_i.get('max', 0.0)), key=f"max{i}"),
                    "col": r[2].selectbox("Coluna", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"col{i}")
                })

            st.subheader("💰 Taxas")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "SEC-CAT", "Suframa"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0)

            if st.button("💾 Salvar Transportadora"):
                mapa_f = {"ap_cidade": ap_cid, "ap_sigla": ap_sig, "tab_sigla": tb_sig, "tab_uf": tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": kg_ex}
                save_transportadora(e_id, nome_t, df_t, df_a, mapa_f)
                st.session_state.edit_id = None; st.rerun()

    for _, r in df_list.iterrows():
        c = st.columns([7, 1, 1])
        c[0].write(f"**{r['nome']}**")
        if c[1].button("✏️", key=f"e{r['id']}"): st.session_state.edit_id = r['id']; st.rerun()
        if c[2].button("🗑️", key=f"d{r['id']}"): supabase.table("transportadoras").delete().eq("id", r['id']).execute(); st.rerun()

# --- COMPARATIVO (CÁLCULO TOTAL) ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo Massivo")
    f_n = st.file_uploader("Notas Fiscais (Excel)")
    df_ts = get_transportadoras()
    
    if f_n and not df_ts.empty:
        selecionadas = st.multiselect("Transportadoras", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Processar 18k Linhas"):
            df_base = pd.read_excel(f_n).fillna(0)
            todos_resultados = []
            
            for t_nome in selecionadas:
                t_row = df_ts[df_ts['nome'] == t_nome].iloc[0]
                m = t_row['mapeamento_json']
                df_tab = pd.DataFrame(t_row['tabela_json'])
                df_abr = pd.DataFrame(t_row['cidades_json'])
                
                # 1. Normalização e Cruzamento
                df_c = df_base.copy()
                df_c['KEY_CID'] = df_c.iloc[:, 2].astype(str).apply(normalizar)
                df_abr['KEY_REF'] = df_abr[m['ap_cidade']].astype(str).apply(normalizar)
                df_tab['KEY_TAB'] = df_tab[m['tab_sigla']].astype(str).apply(normalizar)
                
                df_m1 = pd.merge(df_c, df_abr[[m['ap_sigla'], 'KEY_REF']], left_on='KEY_CID', right_on='KEY_REF', how='left')
                df_m1['KEY_M'] = df_m1[m['ap_sigla']].astype(str).apply(normalizar)
                df_final = pd.merge(df_m1, df_tab, left_on='KEY_M', right_on='KEY_TAB', how='left')
                
                # 2. Variáveis Numéricas
                peso = pd.to_numeric(df_final.iloc[:, 6], errors='coerce').fillna(0)
                valor = pd.to_numeric(df_final.iloc[:, 7], errors='coerce').fillna(0)
                
                # 3. Frete Peso
                df_final['F_PESO'] = 0.0
                for f in m['faixas']:
                    if f['col'] in df_final.columns:
                        mask = (peso <= f['max']) & (df_final['F_PESO'] == 0.0)
                        df_final.loc[mask, 'F_PESO'] = pd.to_numeric(df_final.loc[mask, f['col']], errors='coerce').fillna(0)
                
                if m.get('kg_extra') in df_final.columns:
                    u_max = m['faixas'][-1]['max']
                    u_col = m['faixas'][-1]['col']
                    mask_e = (peso > u_max)
                    base_v = pd.to_numeric(df_final.loc[mask_e, u_col], errors='coerce').fillna(0)
                    adic = pd.to_numeric(df_final.loc[mask_e, m['kg_extra']], errors='coerce').fillna(0)
                    df_final.loc[mask_e, 'F_PESO'] = base_v + ((peso[mask_e] - u_max) * adic)

                # 4. Taxas Dinâmicas
                def gv(name):
                    col = m['taxas'].get(name, "Não mapear")
                    return pd.to_numeric(df_final[col], errors='coerce').fillna(0) if col in df_final.columns else 0.0

                df_final['ADVAL'] = np.maximum(valor * gv("Ad Valorem %"), gv("Ad Valorem Min"))
                df_final['GRIS'] = np.maximum(valor * gv("Gris %"), gv("Gris Min"))
                df_final['PEDAGIO'] = np.ceil(peso / 100) * gv("Pedagio")
                
                df_final['VALOR_SISTEMA'] = (df_final['F_PESO'] + df_final['ADVAL'] + 
                                            df_final['GRIS'] + df_final['PEDAGIO'] + 
                                            gv("TAS") + gv("CTRC") + gv("SEC-CAT") + gv("Suframa"))
                
                df_final['T_NOME'] = t_nome
                todos_resultados.append(df_final)

            # Salvar Lote
            df_full = pd.concat(todos_resultados)
            payload = {
                "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "total": float(df_full['VALOR_SISTEMA'].sum()),
                "qtd": len(df_base),
                "detalhes_json": df_full.to_dict(orient='records')
            }
            supabase.table("cotacoes").insert(payload).execute()
            st.success("Cálculo concluído e salvo na nuvem!"); st.rerun()
