import streamlit as st
import pandas as pd
from supabase import create_client, Client
import json
import io
import os
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

# --- SIDEBAR (LOGO E MENU) ---
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
    menu = st.radio("MENUPrincipal", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])
    st.divider()
    st.caption("Conectado ao Supabase Cloud ✅")

# --- DASHBOARD (CONSOLIDADO UF E FILTROS) ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    res = supabase.table("cotacoes").select("*").execute()
    
    if res.data:
        all_dfs = [pd.DataFrame(r['detalhes_json']) for r in res.data if r['detalhes_json']]
        if all_dfs:
            df_total = pd.concat(all_dfs, ignore_index=True)
            
            # Filtros
            st.subheader("🎯 Filtros")
            f1, f2 = st.columns(2)
            lista_ufs = sorted([str(x) for x in df_total['UF'].dropna().unique() if x != ""])
            lista_transp = sorted([str(x) for x in df_total['T_NOME'].dropna().unique() if x != ""])
            
            sel_uf = f1.multiselect("Filtrar por UF", lista_ufs)
            sel_tr = f2.multiselect("Filtrar por Transportadora", lista_transp)
            
            if sel_uf: df_total = df_total[df_total['UF'].isin(sel_uf)]
            if sel_tr: df_total = df_total[df_total['T_NOME'].isin(sel_tr)]
            
            # Métricas e Consolidação por UF
            c1, c2 = st.columns(2)
            c1.metric("Total Cotado", f"R$ {formata_br(df_total['VALOR_SISTEMA'].sum())}")
            c2.metric("Qtd Notas", len(df_total))
            
            st.write("### 🌍 Consolidação por UF e Transportadora")
            if 'UF' in df_total.columns:
                cons = df_total.groupby(['UF', 'T_NOME'])['VALOR_SISTEMA'].sum().reset_index()
                st.dataframe(cons.sort_values('VALOR_SISTEMA', ascending=False), use_container_width=True)
    else:
        st.info("Nenhum dado encontrado.")

# --- TRANSPORTADORAS (MAPEAMENTO COMPLETO) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_list = pd.DataFrame(res_t.data)

    with st.expander("📝 Configurar Mapeamento", expanded=st.session_state.get('edit_id') is not None):
        e_id = st.session_state.get('edit_id')
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id is not None else None
        
        nome_t = st.text_input("Nome da Transportadora", value=e_row['nome'] if e_row is not None else "").upper()
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("Tabela de Preços")
        f_abr = c2.file_uploader("Abrangência")
        
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.DataFrame(e_row['tabela_json']) if e_row is not None else None)
        df_a = pd.read_excel(f_abr).fillna(0) if f_abr else (pd.DataFrame(e_row['cidades_json']) if e_row is not None else None)

        if df_t is not None and df_a is not None:
            mapa = e_row['mapeamento_json'] if e_row is not None else {}
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_a = ["Não mapear"] + [str(c) for c in df_a.columns]
            
            st.subheader("🔗 Ligações Chave")
            l1, l2 = st.columns(2)
            m_ap_cid = l1.selectbox("Abrangência: Cidade", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
            m_ap_sig = l1.selectbox("Abrangência: Sigla (Match)", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            m_tb_sig = l2.selectbox("Tabela: Sigla (Match)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
            m_tb_uf = l2.selectbox("Tabela: UF", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)
            
            st.subheader("⚖️ Pesos e Faixas")
            col_kg_ex = st.selectbox("Preço Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            n_faixas = st.number_input("Qtd Faixas", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(n_faixas)):
                r = st.columns(3)
                f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({
                    "min": r[0].number_input("De kg", value=float(f_i.get('min', 0.0)), key=f"min{i}"),
                    "max": r[1].number_input("Até kg", value=float(f_i.get('max', 0.0)), key=f"max{i}"),
                    "col": r[2].selectbox("Coluna", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"col{i}")
                })

            st.subheader("💰 Todas as Taxas")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "SEC-CAT", "Suframa", "EMEX", "TRT", "TDA"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0)

            if st.button("💾 Salvar Transportadora"):
                mapa_final = {"ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig, "tab_sigla": m_tb_sig, "tab_uf": m_tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_ex}
                payload = {"nome": nome_t, "tabela_json": df_t.replace([np.inf, -np.inf], 0).fillna(0).to_dict(orient='records'), "cidades_json": df_a.to_dict(orient='records'), "mapeamento_json": mapa_final}
                if e_id: supabase.table("transportadoras").update(payload).eq("id", e_id).execute()
                else: supabase.table("transportadoras").insert(payload).execute()
                st.session_state.edit_id = None; st.success("Salvo!"); st.rerun()

    for _, r in df_list.iterrows():
        c = st.columns([7, 1, 1]); c[0].write(f"**{r['nome']}**")
        if c[1].button("✏️", key=f"ed{r['id']}"): st.session_state.edit_id = r['id']; st.rerun()
        if c[2].button("🗑️", key=f"dl{r['id']}"): supabase.table("transportadoras").delete().eq("id", r['id']).execute(); st.rerun()

# --- COMPARATIVO (EXPANSÃO INTELIGENTE) ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo Massivo")
    f_notas = st.file_uploader("Subir Notas Fiscais", type=["xlsx"])
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)

    if f_notas and not df_ts.empty:
        selecionadas = st.multiselect("Transportadoras", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular"):
            with st.spinner("Vetorizando 18k linhas..."):
                df_base = pd.read_excel(f_notas).fillna(0)
                resultados_lote = []
                for t_nome in selecionadas:
                    t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
                    m, df_tab, df_abr = t_r['mapeamento_json'], pd.DataFrame(t_r['tabela_json']), pd.DataFrame(t_r['cidades_json'])
                    
                    df_c = df_base.copy()
                    df_c['K_CID'] = df_c.iloc[:, 2].astype(str).apply(normalizar)
                    df_abr['K_REF'] = df_abr[m['ap_cidade']].astype(str).apply(normalizar)
                    df_tab['K_TAB'] = df_tab[m['tab_sigla']].astype(str).apply(normalizar)
                    
                    df_m = pd.merge(df_c, df_abr[[m['ap_sigla'], 'K_REF']], left_on='K_CID', right_on='KEY_REF' if 'KEY_REF' in df_abr else 'K_REF', how='left')
                    df_m['K_MATCH'] = df_m[m['ap_sigla']].astype(str).apply(normalizar)
                    df_f = pd.merge(df_m, df_tab, left_on='K_MATCH', right_on='K_TAB', how='left')
                    
                    p_kg, v_nf = pd.to_numeric(df_f.iloc[:, 6], errors='coerce').fillna(0), pd.to_numeric(df_f.iloc[:, 7], errors='coerce').fillna(0)
                    df_f['F_PESO'] = 0.0
                    for f in m['faixas']:
                        if f['col'] in df_f.columns:
                            mask = (p_kg <= f['max']) & (df_f['F_PESO'] == 0.0)
                            df_f.loc[mask, 'F_PESO'] = pd.to_numeric(df_f.loc[mask, f['col']], errors='coerce').fillna(0)
                    
                    if m.get('kg_extra') in df_f.columns:
                        u_max, u_col = m['faixas'][-1]['max'], m['faixas'][-1]['col']
                        mask_e = (p_kg > u_max)
                        df_f.loc[mask_e, 'F_PESO'] = pd.to_numeric(df_f.loc[mask_e, u_col], errors='coerce').fillna(0) + ((p_kg[mask_e]-u_max)*pd.to_numeric(df_f.loc[mask_e, m['kg_extra']], errors='coerce').fillna(0))

                    def gv(n):
                        c = m['taxas'].get(n, "Não mapear")
                        return pd.to_numeric(df_f[c], errors='coerce').fillna(0) if c in df_f.columns else 0.0

                    df_f['ADVAL'] = np.maximum(v_nf * gv("Ad Valorem %"), gv("Ad Valorem Min"))
                    df_f['GRIS'] = np.maximum(v_nf * gv("Gris %"), gv("Gris Min"))
                    df_f['PEDAGIO'] = np.ceil(p_kg/100)*gv("Pedagio")
                    df_f['OUTRAS'] = gv("TAS")+gv("CTRC")+gv("SEC-CAT")+gv("Suframa")+gv("EMEX")+gv("TRT")+gv("TDA")
                    df_f['VALOR_SISTEMA'] = df_f['F_PESO']+df_f['ADVAL']+df_f['GRIS']+df_f['PEDAGIO']+df_f['OUTRAS']
                    df_f['T_NOME'], df_f['UF'] = t_nome, df_f[m['tab_uf']] if m['tab_uf'] in df_f.columns else "ND"
                    resultados_lote.append(df_f)

                df_full = pd.concat(resultados_lote).replace([np.inf, -np.inf], 0).fillna(0)
                payload = {"data_hora": datetime.now().strftime("%d/%m/%Y %H:%M"), "total": float(df_full['VALOR_SISTEMA'].sum()), "qtd": len(df_base), "detalhes_json": df_full.to_dict(orient='records')}
                supabase.table("cotacoes").insert(payload).execute()
                st.rerun()

    st.divider()
    st.subheader("🕒 Histórico")
    res_h = supabase.table("cotacoes").select("*").order("id", desc=True).execute()
    for r in res_h.data:
        with st.expander(f"📦 {r['data_hora']} | {r['qtd']} notas | R$ {formata_br(r['total'])}"):
            df_h = pd.DataFrame(r['detalhes_json'])
            
            # REGRA: 1 Transportadora = Detalhado | Várias = Consolidado
            unificadas = df_h['T_NOME'].unique()
            if len(unificadas) == 1:
                st.info(f"Detalhamento de Taxas: {unificadas[0]}")
                cols_det = ['UF', 'VALOR_SISTEMA', 'F_PESO', 'ADVAL', 'GRIS', 'PEDAGIO', 'OUTRAS']
                st.dataframe(df_h[[c for c in cols_det if c in df_h.columns]], use_container_width=True)
            else:
                st.info("Resumo por Transportadora")
                resumo = df_h.groupby('T_NOME')['VALOR_SISTEMA'].sum().reset_index()
                resumo['VALOR_SISTEMA'] = resumo['VALOR_SISTEMA'].apply(lambda x: f"R$ {formata_br(x)}")
                st.table(resumo)
                if st.button("Ver Todas as Notas", key=f"view_{r['id']}"): st.dataframe(df_h)
            
            if st.button("🗑️ Excluir", key=f"del_{r['id']}"):
                supabase.table("cotacoes").delete().eq("id", r['id']).execute(); st.rerun()
