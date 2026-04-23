import streamlit as st
import pandas as pd
from supabase import create_client
import numpy as np
from datetime import datetime
import unicodedata

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Ave-Maria | Sistema de Fretes", layout="wide")

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(txt).upper().strip()) if unicodedata.category(c) != 'Mn')

# --- SIDEBAR ---
with st.sidebar:
    st.title("Ave-Maria Fretes")
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
            ufs = sorted(df_total['UF'].unique().tolist()) if 'UF' in df_total.columns else []
            sel_ufs = c_f1.multiselect("Filtrar por UF", ufs, default=ufs)
            
            cols_f = [c for c in df_total.columns if c.startswith("TOTAL_")]
            nomes_t = [c.replace("TOTAL_", "") for c in cols_f]
            sel_tr = c_f2.multiselect("Transportadoras", nomes_t, default=nomes_t)
            
            df_filt = df_total.copy()
            if sel_ufs: df_filt = df_filt[df_filt['UF'].isin(sel_ufs)]
            cols_sel = [f"TOTAL_{t}" for t in sel_tr]
            
            if not df_filt.empty and cols_sel:
                m1, m2, m3 = st.columns(3)
                m1.metric("Notas Processadas", len(df_filt))
                m2.metric("Gasto Estimado", f"R$ {df_filt[cols_sel].sum().sum():,.2f}")
                m3.metric("Melhor Opção", df_filt[cols_sel].sum().idxmin().replace("TOTAL_", ""))

                st.divider()
                st.subheader("🌍 Gastos por UF")
                resumo_uf = df_filt.groupby('UF')[cols_sel].sum()
                st.bar_chart(resumo_uf)
                st.dataframe(resumo_uf.style.format("R$ {:,.2f}"), use_container_width=True)
    else: st.info("Histórico vazio.")

# --- CADASTRO DE TRANSPORTADORA ---
elif menu == "🚛 Cadastro de Transportadora":
    st.title("🚛 Cadastro de Transportadora")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_list = pd.DataFrame(res_t.data)
    if 'form_reset_key' not in st.session_state: st.session_state.form_reset_key = 0

    with st.expander("📝 Configurar Nova ou Editar", expanded=st.session_state.get('edit_id') is not None):
        e_id = st.session_state.get('edit_id')
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id and not df_list.empty else None
        
        nome_t = st.text_input("Nome da Transportadora", value=e_row['nome'] if e_row else "", key=f"n_{st.session_state.form_reset_key}").upper()
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("📂 Tabela de Preços", type=["xlsx"], key=f"t_{st.session_state.form_reset_key}")
        f_abr = c2.file_uploader("📂 Relação de Cidades (Siglas Manuais)", type=["xlsx"], key=f"a_{st.session_state.form_reset_key}")
        
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.DataFrame(e_row['tabela_json']) if e_row else None)
        df_a = pd.read_excel(f_abr).fillna(0) if f_abr else (pd.DataFrame(e_row['cidades_json']) if e_row else None)

        if df_t is not None and df_a is not None:
            mapa = e_row['mapeamento_json'] if e_row else {}
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_a = ["Não mapear"] + [str(c) for c in df_a.columns]
            
            cm1, cm2 = st.columns(2)
            with cm1:
                st.caption("Configurações da Tabela")
                m_tb_sig = st.selectbox("Coluna Sigla (na Tabela)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
                m_tb_uf = st.selectbox("Coluna UF (na Tabela)", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)
                col_kg_ex = st.selectbox("Coluna Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            with cm2:
                st.caption("Configurações da Relação de Cidades")
                m_ap_cid = st.selectbox("Coluna Cidade (na Relação)", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
                m_ap_sig = st.selectbox("Coluna Sigla (na Relação)", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
                m_ap_tipo = st.selectbox("Coluna Capital/Interior", cols_a, index=cols_a.index(mapa.get('ap_tipo')) if mapa.get('ap_tipo') in cols_a else 0)
            
            st.divider()
            n_f = st.number_input("Qtd Faixas de Peso", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3); f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({
                    "min": r[0].number_input("De kg", value=float(f_i.get('min', 0.0)), key=f"mi{i}"),
                    "max": r[1].number_input("Até kg", value=float(f_i.get('max', 0.0)), key=f"ma{i}"),
                    "col": r[2].selectbox("Coluna Tabela", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"co{i}")
                })

            st.write("### 💰 Taxas")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0, key=f"tx_{idx}")

            if st.button("💾 Salvar Transportadora"):
                mapa_f = {"ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig, "ap_tipo": m_ap_tipo, "tab_sigla": m_tb_sig, "tab_uf": m_tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_ex}
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
    f_notas = st.file_uploader("Subir Notas (Excel)", type=["xlsx"])
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)

    if f_notas and not df_ts.empty:
        selecionadas = st.multiselect("Transportadoras", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular"):
            with st.spinner("Processando..."):
                df_base = pd.read_excel(f_notas).fillna(0)
                df_final = pd.DataFrame(index=df_base.index)
                
                cid_notas = df_base.iloc[:, 2].astype(str).apply(normalizar).values
                uf_notas = df_base.iloc[:, 3].astype(str).values
                pesos_notas = pd.to_numeric(df_base.iloc[:, 6], errors='coerce').fillna(0).values
                valores_notas = pd.to_numeric(df_base.iloc[:, 7], errors='coerce').fillna(0).values

                for t_nome in selecionadas:
                    t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
                    m = t_r['mapeamento_json']
                    df_tab = pd.DataFrame(t_r['tabela_json'])
                    df_abr = pd.DataFrame(t_r['cidades_json'])

                    # 1. Match de Cidade -> Sigla (Usando sua relação manual)
                    df_abr['cid_match'] = df_abr[m['ap_cidade']].astype(str).apply(normalizar)
                    # Dicionário Cidade -> Sigla
                    dic_sigla = df_abr.set_index('cid_match')[m['ap_sigla']].to_dict()
                    # Dicionário Cidade -> Tipo (Capital/Interior)
                    dic_tipo = df_abr.set_index('cid_match')[m['ap_tipo']].to_dict() if m.get('ap_tipo') != "Não mapear" else {}
                    
                    siglas_match = pd.Series(cid_notas).map(dic_sigla).fillna("ND").values
                    tipos_match = pd.Series(cid_notas).map(dic_tipo).fillna("").values
                    
                    # 2. Indexação da Tabela de Frete pela Sigla
                    df_tab_idx = df_tab.set_index(df_tab[m['tab_sigla']].astype(str))

                    def get_v(coluna, siglas):
                        if coluna in df_tab_idx.columns:
                            return df_tab_idx[coluna].reindex(siglas).fillna(0).values
                        return np.zeros(len(siglas))

                    # 3. Frete Peso (Até 100 ou Excedente)
                    f_peso = np.zeros(len(df_base))
                    for faixa in m['faixas']:
                        v_faixa = get_v(faixa['col'], siglas_match)
                        mask = (pesos_notas <= faixa['max']) & (f_peso == 0.0)
                        f_peso[mask] = v_faixa[mask]
                    
                    # Caso exceda o peso máximo cadastrado
                    u_max = m['faixas'][-1]['max']
                    mask_e = (pesos_notas > u_max)
                    if mask_e.any():
                        v_base = get_v(m['faixas'][-1]['col'], siglas_match)
                        v_extra = get_v(m['kg_extra'], siglas_match)
                        f_peso[mask_e] = v_base[mask_e] + ((pesos_notas[mask_e] - u_max) * v_extra[mask_e])

                    # 4. Taxas (Lógica de Mínimos do Excel)
                    adv = np.maximum(valores_notas * get_v(m['taxas'].get("Ad Valorem %"), siglas_match), get_v(m['taxas'].get("Ad Valorem Min"), siglas_match))
                    gris = np.maximum(valores_notas * get_v(m['taxas'].get("Gris %"), siglas_match), get_v(m['taxas'].get("Gris Min"), siglas_match))
                    pedagio = np.ceil(pesos_notas / 100) * 14.70
                    fixas = get_v(m['taxas'].get("TAS"), siglas_match) + 7.41 # CTRC fixo conforme sua fórmula
                    
                    # EMEX e Adicional Capital (Regra RJ)
                    emex = np.where(uf_notas == "RJ", np.maximum(valores_notas * 0.0021, 6.87), 0)
                    adj_cap = np.where((uf_notas == "RJ") & (tipos_match == "CAPITAL"), np.maximum(valores_notas * 0.0031, 28.48), 0)

                    df_final[f'TOTAL_{t_nome}'] = f_peso + adv + gris + pedagio + fixas + emex + adj_cap
                    df_final['UF'] = uf_notas

                # Salvar Histórico
                res_detalhes = df_final.fillna(0).to_dict(orient='records')
                supabase.table("cotacoes").insert({
                    "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "qtd": len(df_base),
                    "detalhes_json": res_detalhes
                }).execute()
                st.success("Cálculo Finalizado!"); st.rerun()

    st.divider()
    st.subheader("🕒 Histórico de Cálculos")
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
