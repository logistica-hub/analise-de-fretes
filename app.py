import streamlit as st
import pandas as pd
from supabase import create_client
import numpy as np
from datetime import datetime
import unicodedata
import re
from io import BytesIO

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Ave-Maria | Sistema de Fretes", layout="wide")

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

def super_limpeza(txt):
    """Limpeza profunda para evitar o erro de 'ND'"""
    if not txt or pd.isna(txt): return ""
    txt = str(txt).strip().upper()
    txt = re.sub(r'\s+', ' ', txt) 
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def to_excel_multisheet(df_detalhado, df_original):
    """Gera Excel com aba Geral (original + totais) e abas individuais por transportadora"""
    output = BytesIO()
    
    # Identifica transportadoras pelos prefixos das colunas
    cols_total = [c for c in df_detalhado.columns if c.startswith("TOTAL_")]
    transportadoras = [c.replace("TOTAL_", "") for c in cols_total]
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # --- ABA GERAL ---
        df_geral = df_original.copy()
        for t in transportadoras:
            df_geral[f'TOTAL {t}'] = df_detalhado[f'TOTAL_{t}'].values
        df_geral.to_excel(writer, index=False, sheet_name='Geral')
        
        # --- ABAS INDIVIDUAIS ---
        for t in transportadoras:
            # Seleciona apenas as colunas detalhadas desta transportadora
            cols_t = ['NF'] + [c for c in df_detalhado.columns if c.endswith(f'_{t}')]
            df_t = df_detalhado[cols_t].copy()
            
            # Limpa os nomes das colunas para a aba (remove o nome da transportadora do título da coluna)
            df_t.columns = [c.replace(f'_{t}', '') for c in df_t.columns]
            
            # Reordena para o Total ser o último
            cols_calc = [c for c in df_t.columns if c != 'TOTAL'] + ['TOTAL']
            df_t = df_t[cols_calc]
            
            df_t.to_excel(writer, index=False, sheet_name=t[:31]) # Excel limita nome da aba a 31 caracteres
            
    return output.getvalue()

# --- SIDEBAR ---
with st.sidebar:
    st.title("Ave-Maria Fretes")
    st.info("Versão de Teste: 17.0")
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
            sel_tr = st.multiselect("Transportadoras", [c.replace("TOTAL_", "") for c in df_total.columns if c.startswith("TOTAL_")])
            
            if sel_tr:
                cols_sel = [f"TOTAL_{t}" for t in sel_tr]
                m1, m2, m3 = st.columns(3)
                m1.metric("Notas Processadas", len(df_total))
                m2.metric("Gasto Total", f"R$ {df_total[cols_sel].sum().sum():,.2f}")
                m3.metric("Melhor Opção", df_total[cols_sel].sum().idxmin().replace("TOTAL_", ""))
                st.dataframe(df_total[['NF'] + cols_sel], use_container_width=True)
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
                m_tb_sig = st.selectbox("Sigla (Tabela)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
                m_tb_uf = st.selectbox("UF (Tabela)", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)
                col_kg_ex = st.selectbox("Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            with cm2:
                st.markdown("### 📍 Relação de Cidades")
                m_ap_cid = st.selectbox("Cidade (Relação)", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
                m_ap_sig = st.selectbox("Sigla (Relação)", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            
            faixas = []
            st.divider()
            n_f = st.number_input("Faixas de Peso", 1, 50, len(mapa.get('faixas', [])) or 6)
            for i in range(int(n_f)):
                r = st.columns(3); f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({"min": r[0].number_input("De", value=float(f_i.get('min', 0.0)), key=f"mi{i}"), "max": r[1].number_input("Até", value=float(f_i.get('max', 0.0)), key=f"ma{i}"), "col": r[2].selectbox("Coluna", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"co{i}")})

            m_taxas = {}
            st.divider()
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "Suframa", "Fluvial", "Redespacho Fluvial"]
            tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0, key=f"tx_{idx}")

            if st.button("💾 Salvar"):
                mapa_f = {"ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig, "tab_sigla": m_tb_sig, "tab_uf": m_tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_ex}
                payload = {"nome": nome_t, "tabela_json": df_t.to_dict(orient='records'), "cidades_json": df_a.to_dict(orient='records'), "mapeamento_json": mapa_f}
                if e_id: supabase.table("transportadoras").update(payload).eq("id", e_id).execute()
                else: supabase.table("transportadoras").insert(payload).execute()
                st.session_state.edit_id = None; st.session_state.form_reset_key += 1; st.rerun()

# --- COMPARATIVO ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo Massivo")
    f_notas = st.file_uploader("Base de Notas (Excel)", type=["xlsx"])
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)

    if f_notas and not df_ts.empty:
        selecionadas = st.multiselect("Transportadoras", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular"):
            with st.spinner("Processando..."):
                df_base = pd.read_excel(f_notas).fillna(0)
                df_final = pd.DataFrame(index=df_base.index)
                df_final['NF'] = df_base.iloc[:, 0].values
                
                cid_notas = df_base.iloc[:, 2].astype(str).apply(super_limpeza).values
                pesos_notas = pd.to_numeric(df_base.iloc[:, 6], errors='coerce').fillna(0).values
                valores_notas = pd.to_numeric(df_base.iloc[:, 7], errors='coerce').fillna(0).values

                for t_nome in selecionadas:
                    t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
                    m, df_tab, df_abr = t_r['mapeamento_json'], pd.DataFrame(t_r['tabela_json']), pd.DataFrame(t_r['cidades_json'])
                    
                    df_abr['cid_clean'] = df_abr[m['ap_cidade']].astype(str).apply(super_limpeza)
                    dic_ponte = df_abr.set_index('cid_clean')[m['ap_sigla']].astype(str).apply(super_limpeza).to_dict()
                    siglas_match = pd.Series(cid_notas).map(dic_ponte).fillna("ND").values
                    
                    df_tab_idx = df_tab.set_index(df_tab[m['tab_sigla']].astype(str).apply(super_limpeza))
                    def get_v(col):
                        if col and col != "Não mapear" and col in df_tab_idx.columns:
                            return df_tab_idx[col].reindex(siglas_match).fillna(0).values
                        return np.zeros(len(df_base))

                    f_peso = np.zeros(len(df_base)); v_kg_adic = np.zeros(len(df_base))
                    for fx in m['faixas']:
                        v_f = get_v(fx['col'])
                        mask = (pesos_notas <= fx['max']) & (f_peso == 0.0)
                        f_peso[mask] = v_f[mask]
                    
                    u_max = m['faixas'][-1]['max']
                    mask_e = (pesos_notas > u_max)
                    if mask_e.any():
                        v_b, v_ex = get_v(m['faixas'][-1]['col']), get_v(m['kg_extra'])
                        v_kg_adic[mask_e] = (pesos_notas[mask_e] - u_max) * v_ex[mask_e]
                        f_peso[mask_e] = v_b[mask_e] + v_kg_adic[mask_e]

                    adv = np.maximum(valores_notas * get_v(m['taxas'].get("Ad Valorem %")), get_v(m['taxas'].get("Ad Valorem Min")))
                    grs = np.maximum(valores_notas * get_v(m['taxas'].get("Gris %")), get_v(m['taxas'].get("Gris Min")))
                    emx = np.maximum(valores_notas * get_v(m['taxas'].get("Emex %")), get_v(m['taxas'].get("Emex Min")))
                    ped = np.ceil(pesos_notas/100) * get_v(m['taxas'].get("Pedagio"))
                    tas, ctrc = get_v(m['taxas'].get("TAS")), get_v(m['taxas'].get("CTRC"))
                    outros = (valores_notas * (get_v(m['taxas'].get("Suframa")) + get_v(m['taxas'].get("Fluvial")))) + get_v(m['taxas'].get("Redespacho Fluvial"))
                    
                    df_final[f'PESO_BASE_{t_nome}'] = f_peso - v_kg_adic
                    df_final[f'KG_ADIC_{t_nome}'] = v_kg_adic
                    df_final[f'ADVAL_{t_nome}'] = adv
                    df_final[f'GRIS_{t_nome}'] = grs
                    df_final[f'EMEX_{t_nome}'] = emx
                    df_final[f'PEDAGIO_{t_nome}'] = ped
                    df_final[f'TAS_{t_nome}'] = tas
                    df_final[f'CTRC_{t_nome}'] = ctrc
                    df_final[f'OUTROS_{t_nome}'] = outros
                    df_final[f'TOTAL_{t_nome}'] = f_peso + adv + grs + emx + ped + tas + ctrc + outros

                supabase.table("cotacoes").insert({
                    "data_hora": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "qtd": len(df_base),
                    "detalhes_json": df_final.fillna(0).to_dict(orient='records'),
                    "base_original_json": df_base.to_dict(orient='records') # Salva base para a aba Geral
                }).execute()
                st.success("Calculado!"); st.rerun()

    res_h = supabase.table("cotacoes").select("*").order("id", desc=True).execute()
    if res_h.data:
        for t_ref, g in pd.DataFrame(res_h.data).groupby("data_hora", sort=False):
            df_det = pd.DataFrame(g.iloc[0]['detalhes_json'])
            df_orig = pd.DataFrame(g.iloc[0]['base_original_json'])
            with st.expander(f"📦 {t_ref} | {len(df_det)} Notas"):
                xlsx_data = to_excel_multisheet(df_det, df_orig)
                st.download_button(f"📥 Baixar Comparativo Multi-Abas", data=xlsx_data, file_name=f"Relatorio_{t_ref.replace('/','-')}.xlsx")
                if st.button("🗑️ Remover", key=f"del_{t_ref}"):
                    for rid in g['id']: supabase.table("cotacoes").delete().eq("id", rid).execute()
                    st.rerun()
                st.dataframe(df_det[['NF'] + [c for c in df_det.columns if c.startswith("TOTAL_")]], use_container_width=True)
