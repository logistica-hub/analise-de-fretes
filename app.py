import streamlit as st
import pandas as pd
from supabase import create_client
import numpy as np
from datetime import datetime
import unicodedata
import re

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Ave-Maria | Sistema de Fretes", layout="wide")

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

def super_limpeza(txt):
    """Limpeza profunda para evitar o erro de 'ND'"""
    if not txt or pd.isna(txt): return ""
    # Transforma em string, remove espaços extras nas pontas e internos
    txt = str(txt).strip().upper()
    txt = re.sub(r'\s+', ' ', txt) 
    # Remove acentuação
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

# --- SIDEBAR ---
with st.sidebar:
    st.title("Ave-Maria Fretes")
    st.info("Versão de Teste: 15.1")
    if 'logo_data' not in st.session_state: st.session_state.logo_data = None
    if st.session_state.logo_data:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Alterar Logo"):
            st.session_state.logo_data = None
            st.rerun()
    else:
        up_logo = st.file_uploader("🖼️ Logo da Empresa", type=["png", "jpg", "jpeg"])
        if up_logo:
            st.session_state.logo_data = up_logo.read()
            st.rerun()
    
    st.divider()
    menu = st.radio("Navegação", ["📊 Dashboard", "🚛 Cadastro de Transportadora", "💰 Comparativo"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        all_dfs = [pd.DataFrame(r['detalhes_json']) for r in res.data if r['detalhes_json']]
        if all_dfs:
            df_total = pd.concat(all_dfs, ignore_index=True)
            st.subheader("🎯 Filtros")
            c_f1, c_f2 = st.columns(2)
            
            cols_f = [c for c in df_total.columns if c.startswith("TOTAL_")]
            nomes_t = [c.replace("TOTAL_", "") for c in cols_f]
            sel_tr = c_f2.multiselect("Transportadoras", nomes_t, default=nomes_t)
            
            df_filt = df_total.copy()
            cols_sel = [f"TOTAL_{t}" for t in sel_tr]
            
            if not df_filt.empty and cols_sel:
                m1, m2, m3 = st.columns(3)
                m1.metric("Notas Processadas", len(df_filt))
                m2.metric("Gasto Total", f"R$ {df_filt[cols_sel].sum().sum():,.2f}")
                m3.metric("Melhor Opção", df_filt[cols_sel].sum().idxmin().replace("TOTAL_", ""))
                
                st.divider()
                st.subheader("📋 Resumo por Nota (NF)")
                st.dataframe(df_filt, use_container_width=True)
    else: st.info("Sem dados no histórico.")

# --- CADASTRO ---
elif menu == "🚛 Cadastro de Transportadora":
    st.title("🚛 Cadastro de Transportadora")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_list = pd.DataFrame(res_t.data)
    if 'form_reset_key' not in st.session_state: st.session_state.form_reset_key = 0

    with st.expander("📝 Configurar Mapeamento", expanded=st.session_state.get('edit_id') is not None):
        e_id = st.session_state.get('edit_id')
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id is not None and not df_list.empty else None
        nome_t = st.text_input("Nome", value=e_row['nome'] if e_row is not None else "", key=f"n_{st.session_state.form_reset_key}").upper()
        
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("📂 Tabela de Preços", type=["xlsx"], key=f"t_{st.session_state.form_reset_key}")
        f_abr = c2.file_uploader("📂 Relação de Cidades (Siglas)", type=["xlsx"], key=f"a_{st.session_state.form_reset_key}")
        
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.DataFrame(e_row['tabela_json']) if e_row is not None else None)
        df_a = pd.read_excel(f_abr).fillna(0) if f_abr else (pd.DataFrame(e_row['cidades_json']) if e_row is not None else None)

        if df_t is not None and df_a is not None:
            mapa = e_row['mapeamento_json'] if e_row is not None else {}
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_a = ["Não mapear"] + [str(c) for c in df_a.columns]
            
            cm1, cm2 = st.columns(2)
            with cm1:
                st.markdown("### 📋 Configuração Tabela")
                m_tb_sig = st.selectbox("Coluna Sigla (na Tabela)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
                m_tb_uf = st.selectbox("Coluna UF (na Tabela)", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)
                col_kg_ex = st.selectbox("Coluna Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            with cm2:
                st.markdown("### 📍 Relação de Cidades")
                m_ap_cid = st.selectbox("Coluna Cidade (na Relação)", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
                m_ap_sig = st.selectbox("Coluna Sigla (na Relação)", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            
            st.divider()
            st.markdown("### ⚖️ Mapeamento de Faixas de Peso")
            n_f = st.number_input("Qtd Faixas de Peso", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3); f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({
                    "min": r[0].number_input("De kg", value=float(f_i.get('min', 0.0)), key=f"mi{i}"),
                    "max": r[1].number_input("Até kg", value=float(f_i.get('max', 0.0)), key=f"ma{i}"),
                    "col": r[2].selectbox("Coluna na Tabela", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"co{i}")
                })

            st.divider()
            st.markdown("### 💰 Mapeamento de Taxas Adicionais")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "Suframa", "Fluvial", "Redespacho Fluvial"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0, key=f"tx_{idx}")

            if st.button("💾 Salvar Transportadora"):
                mapa_f = {"ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig, "tab_sigla": m_tb_sig, "tab_uf": m_tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_ex}
                payload = {"nome": nome_t, "tabela_json": df_t.to_dict(orient='records'), "cidades_json": df_a.to_dict(orient='records'), "mapeamento_json": mapa_f}
                if e_id: supabase.table("transportadoras").update(payload).eq("id", e_id).execute()
                else: supabase.table("transportadoras").insert(payload).execute()
                st.session_state.edit_id = None; st.session_state.form_reset_key += 1; st.rerun()

    for _, r in df_list.iterrows():
        c = st.columns([7, 1, 1]); c[0].write(f"**{r['nome']}**")
        if c[1].button("✏️", key=f"ed{r['id']}"): st.session_state.edit_id = r['id']; st.rerun()
        if c[2].button("🗑️", key=f"dl{r['id']}"): supabase.table("transportadoras").delete().eq("id", r['id']).execute(); st.rerun()

# --- COMPARATIVO ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo Massivo")
    f_notas = st.file_uploader("Base de Notas (Excel)", type=["xlsx"])
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)

    if f_notas and not df_ts.empty:
        selecionadas = st.multiselect("Selecione as Transportadoras", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular"):
            with st.spinner("Processando..."):
                df_base = pd.read_excel(f_notas).fillna(0)
                df_final = pd.DataFrame(index=df_base.index)
                
                # Pegando o número da nota (Coluna 0 da Base)
                df_final['NF'] = df_base.iloc[:, 0].values
                
                # Cidades da Base de Notas (Coluna 2)
                cid_notas = df_base.iloc[:, 2].astype(str).apply(super_limpeza).values
                pesos_notas = pd.to_numeric(df_base.iloc[:, 6], errors='coerce').fillna(0).values
                valores_notas = pd.to_numeric(df_base.iloc[:, 7], errors='coerce').fillna(0).values

                for t_nome in selecionadas:
                    t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
                    m = t_r['mapeamento_json']
                    df_tab = pd.DataFrame(t_r['tabela_json'])
                    df_abr = pd.DataFrame(t_r['cidades_json'])

                    # 1. Ponte: Cidade Base -> Sigla Relação
                    df_abr['cid_clean'] = df_abr[m['ap_cidade']].astype(str).apply(super_limpeza)
                    dic_ponte = df_abr.set_index('cid_clean')[m['ap_sigla']].astype(str).apply(super_limpeza).to_dict()
                    siglas_match = pd.Series(cid_notas).map(dic_ponte).fillna("ND").values
                    
                    # 2. Tabela de Frete indexada pela Sigla
                    df_tab['sig_clean'] = df_tab[m['tab_sigla']].astype(str).apply(super_limpeza)
                    df_tab_idx = df_tab.set_index('sig_clean')

                    def get_v(col):
                        if col and col != "Não mapear" and col in df_tab_idx.columns:
                            return df_tab_idx[col].reindex(siglas_match).fillna(0).values
                        return np.zeros(len(df_base))

                    # 3. Frete Peso
                    f_peso = np.zeros(len(df_base))
                    for faixa in m['faixas']:
                        v_f = get_v(faixa['col'])
                        mask = (pesos_notas <= faixa['max']) & (f_peso == 0.0)
                        f_peso[mask] = v_f[mask]
                    
                    u_max = m['faixas'][-1]['max']
                    mask_e = (pesos_notas > u_max)
                    if mask_e.any():
                        v_b = get_v(m['faixas'][-1]['col'])
                        v_ex = get_v(m['kg_extra'])
                        f_peso[mask_e] = v_b[mask_e] + ((pesos_notas[mask_e] - u_max) * v_ex[mask_e])

                    # 4. Taxas
                    adv = np.maximum(valores_notas * get_v(m['taxas'].get("Ad Valorem %")), get_v(m['taxas'].get("Ad Valorem Min")))
                    grs = np.maximum(valores_notas * get_v(m['taxas'].get("Gris %")), get_v(m['taxas'].get("Gris Min")))
                    emx = np.maximum(valores_notas * get_v(m['taxas'].get("Emex %")), get_v(m['taxas'].get("Emex Min")))
                    suframa = valores_notas * get_v(m['taxas'].get("Suframa"))
                    fluvial = valores_notas * get_v(m['taxas'].get("Fluvial"))
                    redesp_flu = get_v(m['taxas'].get("Redespacho Fluvial"))
                    ped = np.ceil(pesos_notas/100) * get_v(m['taxas'].get("Pedagio"))
                    fixas = get_v(m['taxas'].get("TAS")) + get_v(m['taxas'].get("CTRC"))
                    
                    df_final[f'TOTAL_{t_nome}'] = f_peso + adv + grs + emx + suframa + fluvial + redesp_flu + ped + fixas

                supabase.table("cotacoes").insert({
                    "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "qtd": len(df_base),
                    "detalhes_json": df_final.fillna(0).to_dict(orient='records')
                }).execute()
                st.success("Calculado!"); st.rerun()

    st.divider()
    res_h = supabase.table("cotacoes").select("*").order("id", desc=True).execute()
    if res_h.data:
        for t_ref, g in pd.DataFrame(res_h.data).groupby("data_hora", sort=False):
            det = []
            for d in g['detalhes_json']: det.extend(d)
            df_det = pd.DataFrame(det)
            with st.expander(f"📦 {t_ref} | {len(det)} Notas"):
                cols_f = [c for c in df_det.columns if c.startswith("TOTAL_")]
                if cols_f:
                    resumo = df_det[cols_f].sum().reset_index()
                    resumo.columns = ['Transportadora', 'Frete Total']
                    resumo['Transportadora'] = resumo['Transportadora'].str.replace("TOTAL_", "")
                    st.table(resumo.style.format({'Frete Total': "R$ {:,.2f}"}))
                if st.button("🗑️ Remover", key=f"del_{t_ref}"):
                    for rid in g['id']: supabase.table("cotacoes").delete().eq("id", rid).execute()
                    st.rerun()
                st.dataframe(df_det, use_container_width=True)
