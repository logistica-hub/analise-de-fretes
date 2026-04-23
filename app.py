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

def to_excel(df_completo):
    """Gera Excel com múltiplas abas: Geral e Transportadoras"""
    output = BytesIO()
    
    # Identifica colunas de cálculo (as que têm prefixos de taxas ou TOTAL_)
    cols_total = [c for c in df_completo.columns if c.startswith("TOTAL_")]
    transportadoras = [c.replace("TOTAL_", "") for c in cols_total]
    
    # Identifica colunas originais (aquelas que NÃO são colunas de cálculo)
    prefixos_calculo = ["PESO_BASE_", "KG_ADIC_", "ADVAL_", "GRIS_", "EMEX_", "PEDAGIO_", "TAS_", "CTRC_", "OUTROS_", "TOTAL_"]
    cols_originais = [c for c in df_completo.columns if not any(c.startswith(p) for p in prefixos_calculo)]
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # --- ABA GERAL ---
        # Colunas originais + Colunas de Total no final
        df_geral = df_completo[cols_originais + cols_total].copy()
        df_geral.to_excel(writer, index=False, sheet_name='Geral')
        
        # --- ABAS POR TRANSPORTADORA ---
        for t in transportadoras:
            # Seleciona colunas originais + cálculos desta transportadora específica
            cols_calc_t = [c for c in df_completo.columns if c.endswith(f'_{t}')]
            df_t = df_completo[cols_originais + cols_calc_t].copy()
            
            # Limpa o nome das colunas de cálculo (remove o _NOME_DA_TRANS)
            df_t.columns = [c.replace(f'_{t}', '') if c.endswith(f'_{t}') else c for c in df_t.columns]
            
            # Garante que a coluna TOTAL da aba seja a última
            if 'TOTAL' in df_t.columns:
                cols_finais = [c for c in df_t.columns if c != 'TOTAL'] + ['TOTAL']
                df_t = df_t[cols_finais]
            
            # Excel limita nome da aba a 31 caracteres
            df_t.to_excel(writer, index=False, sheet_name=t[:31])
            
    return output.getvalue()

# --- SIDEBAR ---
with st.sidebar:
    st.title("Ave-Maria Fretes")
    st.info("Versão de Teste: 17.1")
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
            c_f2 = st.columns(1)[0]
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
                st.subheader("📋 Últimas Notas")
                # Tenta pegar 'NF' ou a primeira coluna
                nf_col = 'NF' if 'NF' in df_filt.columns else df_filt.columns[0]
                st.dataframe(df_filt[[nf_col] + cols_sel], use_container_width=True)
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
                # O df_final agora começa com uma cópia da base para não perdermos nada
                df_final = df_base.copy()
                
                cid_notas = df_base.iloc[:, 2].astype(str).apply(super_limpeza).values
                pesos_notas = pd.to_numeric(df_base.iloc[:, 6], errors='coerce').fillna(0).values
                valores_notas = pd.to_numeric(df_base.iloc[:, 7], errors='coerce').fillna(0).values

                for t_nome in selecionadas:
                    t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
                    m = t_r['mapeamento_json']
                    df_tab = pd.DataFrame(t_r['tabela_json'])
                    df_abr = pd.DataFrame(t_r['cidades_json'])

                    df_abr['cid_clean'] = df_abr[m['ap_cidade']].astype(str).apply(super_limpeza)
                    dic_ponte = df_abr.set_index('cid_clean')[m['ap_sigla']].astype(str).apply(super_limpeza).to_dict()
                    siglas_match = pd.Series(cid_notas).map(dic_ponte).fillna("ND").values
                    
                    df_tab['sig_clean'] = df_tab[m['tab_sigla']].astype(str).apply(super_limpeza)
                    df_tab_idx = df_tab.set_index('sig_clean')

                    def get_v(col):
                        if col and col != "Não mapear" and col in df_tab_idx.columns:
                            return df_tab_idx[col].reindex(siglas_match).fillna(0).values
                        return np.zeros(len(df_base))

                    f_peso = np.zeros(len(df_base))
                    v_kg_adic = np.zeros(len(df_base))
                    
                    for faixa in m['faixas']:
                        v_f = get_v(faixa['col'])
                        mask = (pesos_notas <= faixa['max']) & (f_peso == 0.0)
                        f_peso[mask] = v_f[mask]
                    
                    u_max = m['faixas'][-1]['max']
                    mask_e = (pesos_notas > u_max)
                    if mask_e.any():
                        v_b = get_v(m['faixas'][-1]['col']); v_ex = get_v(m['kg_extra'])
                        v_kg_adic[mask_e] = (pesos_notas[mask_e] - u_max) * v_ex[mask_e]
                        f_peso[mask_e] = v_b[mask_e] + v_kg_adic[mask_e]

                    adv = np.maximum(valores_notas * get_v(m['taxas'].get("Ad Valorem %")), get_v(m['taxas'].get("Ad Valorem Min")))
                    grs = np.maximum(valores_notas * get_v(m['taxas'].get("Gris %")), get_v(m['taxas'].get("Gris Min")))
                    emx = np.maximum(valores_notas * get_v(m['taxas'].get("Emex %")), get_v(m['taxas'].get("Emex Min")))
                    ped = np.ceil(pesos_notas/100) * get_v(m['taxas'].get("Pedagio"))
                    tas = get_v(m['taxas'].get("TAS"))
                    ctrc = get_v(m['taxas'].get("CTRC"))
                    outros = (valores_notas * get_v(m['taxas'].get("Suframa"))) + (valores_notas * get_v(m['taxas'].get("Fluvial"))) + get_v(m['taxas'].get("Redespacho Fluvial"))
                    
                    # Detalhamento para Exportação concatenado ao DF
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

                # Salva o dataframe COMPLETO no banco
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
                cols_totais = [c for c in df_det.columns if c.startswith("TOTAL_")]
                
                c_btn1, c_btn2 = st.columns(2)
                # A função to_excel agora cuida de separar a aba Geral e as individuais
                xlsx_data = to_excel(df_det)
                c_btn1.download_button(f"📥 Baixar Relatório Detalhado", data=xlsx_data, file_name=f"Cotacao_{t_ref.replace('/','-')}.xlsx")
                if c_btn2.button("🗑️ Excluir Cotação", key=f"del_{t_ref}"):
                    for rid in g['id']: supabase.table("cotacoes").delete().eq("id", rid).execute()
                    st.rerun()

                resumo = df_det[cols_totais].sum().reset_index()
                resumo.columns = ['Transportadora', 'Frete Total']
                resumo['Transportadora'] = resumo['Transportadora'].str.replace("TOTAL_", "")
                st.table(resumo.style.format({'Frete Total': "R$ {:,.2f}"}))
                
                nf_col = 'NF' if 'NF' in df_det.columns else df_det.columns[0]
                st.dataframe(df_det[[nf_col] + cols_totais], use_container_width=True)
