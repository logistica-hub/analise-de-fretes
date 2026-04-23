import streamlit as st
import pandas as pd
from supabase import create_client, Client
import json
from datetime import datetime
import unicodedata
import numpy as np

# --- CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Ave-Maria | Sistema de Fretes", layout="wide")

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

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

# --- SIDEBAR ---
with st.sidebar:
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
    menu = st.radio("Navegação", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        all_dfs = [pd.DataFrame(r['detalhes_json']) for r in res.data if r['detalhes_json']]
        if all_dfs:
            df_total = pd.concat(all_dfs, ignore_index=True)
            st.subheader("🎯 Filtros")
            lista_ufs = sorted([str(x) for x in df_total['UF'].dropna().unique() if x != ""])
            sel_uf = st.multiselect("Filtrar por UF", lista_ufs)
            if sel_uf: df_total = df_total[df_total['UF'].isin(sel_uf)]
            col_fretes = [c for c in df_total.columns if c.startswith("TOTAL_")]
            c1, c2 = st.columns(2)
            c2.metric("Qtd Notas Únicas", len(df_total))
            if col_fretes:
                st.write("### 🌍 Comparativo de Gastos por UF")
                cons = df_total.groupby('UF')[col_fretes].sum()
                st.dataframe(cons.style.format(precision=2), use_container_width=True)
    else: st.info("Nenhum histórico encontrado.")

# --- TRANSPORTADORAS (LAYOUT CORRIGIDO) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_list = pd.DataFrame(res_t.data)

    with st.expander("📝 Configurar Mapeamento", expanded=st.session_state.get('edit_id') is not None):
        e_id = st.session_state.get('edit_id')
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id is not None else None
        
        nome_t = st.text_input("Nome da Transportadora", value=e_row['nome'] if e_row is not None else "").upper()
        
        # Colunas de Upload
        col_up1, col_up2 = st.columns(2)
        f_tab = col_up1.file_uploader("📂 Tabela de Preços", type=["xlsx"])
        f_abr = col_up2.file_uploader("📂 Abrangência", type=["xlsx"])
        
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.DataFrame(e_row['tabela_json']) if e_row is not None else None)
        df_a = pd.read_excel(f_abr).fillna(0) if f_abr else (pd.DataFrame(e_row['cidades_json']) if e_row is not None else None)

        if df_t is not None and df_a is not None:
            mapa = e_row['mapeamento_json'] if e_row is not None else {}
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_a = ["Não mapear"] + [str(c) for c in df_a.columns]
            
            # --- CORREÇÃO DO LAYOUT: ABRANGÊNCIA NA ESQUERDA, TABELA NA DIREITA ---
            l_abr, r_tab = st.columns(2)
            
            # Coluna Abrangência (Esquerda)
            m_ap_cid = l_abr.selectbox("Abrangência: Cidade", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
            m_ap_sig = l_abr.selectbox("Abrangência: Sigla", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            
            # Coluna Tabela (Direita)
            m_tb_sig = r_tab.selectbox("Tabela: Sigla (Match)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
            m_tb_uf = r_tab.selectbox("Tabela: UF", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)
            
            st.divider()
            
            # Configurações de Peso
            col_kg_ex = st.selectbox("Preço Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            n_faixas = st.number_input("Qtd Faixas de Peso", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(n_faixas)):
                r = st.columns(3)
                f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({
                    "min": r[0].number_input("De kg", value=float(f_i.get('min', 0.0)), key=f"min{i}"),
                    "max": r[1].number_input("Até kg", value=float(f_i.get('max', 0.0)), key=f"max{i}"),
                    "col": r[2].selectbox("Coluna na Tabela", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"col{i}")
                })

            # Mapeamento de Taxas
            st.write("### 💰 Mapeamento de Taxas")
            taxas_nomes = [
                "Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", 
                "Gris %", "Gris Min", "SEC-CAT", "Suframa", "EMEX", "TRT", "TDA",
                "Fluvial %", "Redespacho Fluvial %"
            ]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0)

            if st.button("💾 Salvar Transportadora"):
                mapa_final = {"ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig, "tab_sigla": m_tb_sig, "tab_uf": m_tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_ex}
                payload = {"nome": nome_t, "tabela_json": df_t.replace([np.inf, -np.inf], 0).fillna(0).to_dict(orient='records'), "cidades_json": df_a.to_dict(orient='records'), "mapeamento_json": mapa_final}
                if e_id: supabase.table("transportadoras").update(payload).eq("id", e_id).execute()
                else: supabase.table("transportadoras").insert(payload).execute()
                st.session_state.edit_id = None; st.rerun()

    for _, r in df_list.iterrows():
        c = st.columns([7, 1, 1]); c[0].write(f"**{r['nome']}**")
        if c[1].button("✏️", key=f"ed{r['id']}"): st.session_state.edit_id = r['id']; st.rerun()
        if c[2].button("🗑️", key=f"dl{r['id']}"): supabase.table("transportadoras").delete().eq("id", r['id']).execute(); st.rerun()

# --- COMPARATIVO ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo por Nota Fiscal")
    f_notas = st.file_uploader("Subir Notas Fiscais (Excel)", type=["xlsx"])
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)

    if f_notas and not df_ts.empty:
        selecionadas = st.multiselect("Selecione as Transportadoras", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular"):
            with st.spinner("Processando..."):
                df_base = pd.read_excel(f_notas).fillna(0).reset_index(drop=True)
                df_final = pd.DataFrame(index=df_base.index)
                df_final['UF'] = "ND"
                
                ch_notas = df_base.iloc[:, 2].astype(str).apply(normalizar)
                pesos_notas = pd.to_numeric(df_base.iloc[:, 6], errors='coerce').fillna(0).values
                valores_notas = pd.to_numeric(df_base.iloc[:, 7], errors='coerce').fillna(0).values

                for t_nome in selecionadas:
                    t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
                    m, df_tab, df_abr = t_r['mapeamento_json'], pd.DataFrame(t_r['tabela_json']), pd.DataFrame(t_r['cidades_json'])
                    
                    dic_abr = df_abr.set_index(df_abr[m['ap_cidade']].astype(str).apply(normalizar))[m['ap_sigla']].to_dict()
                    sig_match = ch_notas.map(dic_abr).astype(str).apply(normalizar)
                    
                    f_peso = np.zeros(len(df_base))
                    df_tab_idx = df_tab.set_index(df_tab[m['tab_sigla']].astype(str).apply(normalizar))
                    
                    for f in m['faixas']:
                        if f['col'] in df_tab_idx.columns:
                            col_vals = sig_match.map(df_tab_idx[f['col']]).fillna(0).values
                            mask = (pesos_notas <= f['max']) & (f_peso == 0.0)
                            f_peso[mask] = col_vals[mask]

                    if m.get('kg_extra') in df_tab_idx.columns:
                        u_max, u_col = m['faixas'][-1]['max'], m['faixas'][-1]['col']
                        mask_e = (pesos_notas > u_max)
                        b_val = sig_match.map(df_tab_idx[u_col]).fillna(0).values
                        e_val = sig_match.map(df_tab_idx[m['kg_extra']]).fillna(0).values
                        f_peso[mask_e] = b_val[mask_e] + ((pesos_notas[mask_e] - u_max) * e_val[mask_e])

                    def gv(n):
                        c = m['taxas'].get(n, "Não mapear")
                        return sig_match.map(df_tab_idx[c]).fillna(0).values if c in df_tab_idx.columns else np.zeros(len(df_base))

                    # Cálculo Final com todas as taxas (Fixas e %)
                    adval = np.maximum(valores_notas * gv("Ad Valorem %"), gv("Ad Valorem Min"))
                    gris = np.maximum(valores_notas * gv("Gris %"), gv("Gris Min"))
                    ped = np.ceil(pesos_notas/100) * gv("Pedagio")
                    fixas = gv("TAS") + gv("CTRC") + gv("SEC-CAT") + gv("Suframa") + gv("EMEX") + gv("TRT") + gv("TDA")
                    fluv = (valores_notas * gv("Fluvial %")) + (valores_notas * gv("Redespacho Fluvial %"))
                    
                    df_final[f'TOTAL_{t_nome}'] = f_peso + adval + gris + ped + fixas + fluv
                    if m['tab_uf'] in df_tab_idx.columns:
                        df_final['UF'] = sig_match.map(df_tab_idx[m['tab_uf']]).fillna("ND").values

                df_save = df_final.replace([np.inf, -np.inf], 0).fillna(0)
                lista_detalhes = df_save.to_dict(orient='records')
                data_h = datetime.now().strftime("%d/%m/%Y %H:%M")
                chunk = 5000
                total_g = float(df_save.filter(like='TOTAL_').sum().sum())
                for i in range(0, len(lista_detalhes), chunk):
                    p = {"data_hora": data_h, "total": total_g, "qtd": len(df_base), "detalhes_json": lista_detalhes[i : i + chunk]}
                    supabase.table("cotacoes").insert(p).execute()
                st.success("Calculado!"); st.rerun()

    st.divider()
    st.subheader("🕒 Histórico")
    res_h = supabase.table("cotacoes").select("*").order("id", desc=True).execute()
    if res_h.data:
        df_h_raw = pd.DataFrame(res_h.data)
        for t_ref, g in df_h_raw.groupby("data_hora", sort=False):
            det = []
            for d in g['detalhes_json']: det.extend(d)
            df_hist = pd.DataFrame(det)
            with st.expander(f"📦 {t_ref} | {len(df_hist)} Notas"):
                st.dataframe(df_hist, use_container_width=True)
                if st.button("🗑️", key=f"del_{t_ref}"):
                    for rid in g['id']: supabase.table("cotacoes").delete().eq("id", rid).execute()
                    st.rerun()
