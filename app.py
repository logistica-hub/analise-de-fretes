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
    # Remove acentos, coloca em maiúsculo e remove espaços extras nas pontas
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

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
    menu = st.radio("Navegação", ["📊 Dashboard", "🚛 Cadastro de Transportadora", "💰 Comparativo"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        all_dfs = [pd.DataFrame(r['detalhes_json']) for r in res.data if r['detalhes_json']]
        if all_dfs:
            df_total = pd.concat(all_dfs, ignore_index=True)
            st.write(f"Total de registros analisados: {len(df_total)}")
            # ... (filtros do dashboard)
    else: st.info("Nenhum histórico encontrado.")

# --- CADASTRO DE TRANSPORTADORA ---
elif menu == "🚛 Cadastro de Transportadora":
    st.title("🚛 Cadastro de Transportadora")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_list = pd.DataFrame(res_t.data)

    if 'form_reset_key' not in st.session_state: st.session_state.form_reset_key = 0

    with st.expander("📝 Configurar Mapeamento", expanded=st.session_state.get('edit_id') is not None):
        e_id = st.session_state.get('edit_id')
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id is not None and not df_list.empty else None
        
        nome_t = st.text_input("Nome da Transportadora", value=e_row['nome'] if e_row is not None else "", key=f"n_{st.session_state.form_reset_key}").upper()
        
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("📂 Tabela de Preços", type=["xlsx"], key=f"t_{st.session_state.form_reset_key}")
        f_abr = c2.file_uploader("📂 Relação de Cidades", type=["xlsx"], key=f"a_{st.session_state.form_reset_key}")
        
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.DataFrame(e_row['tabela_json']) if e_row is not None else None)
        df_a = pd.read_excel(f_abr).fillna(0) if f_abr else (pd.DataFrame(e_row['cidades_json']) if e_row is not None else None)

        if df_t is not None and df_a is not None:
            mapa = e_row['mapeamento_json'] if e_row is not None else {}
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_a = ["Não mapear"] + [str(c) for c in df_a.columns]
            
            cm_tab, cm_abr = st.columns(2)
            with cm_tab:
                m_tb_sig = st.selectbox("Tabela: Coluna Sigla/Chave", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
                m_tb_uf = st.selectbox("Tabela: Coluna UF", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)
                col_kg_ex = st.selectbox("Tabela: Preço Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            with cm_abr:
                m_ap_cid = st.selectbox("Relação de Cidades: Coluna Cidade", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
                m_ap_sig = st.selectbox("Relação de Cidades: Coluna Sigla (Match)", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            
            # ... (Resto do formulário de faixas e taxas igual à v9.8)
            st.divider()
            n_faixas = st.number_input("Qtd Faixas de Peso", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(n_faixas)):
                r = st.columns(3); f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({
                    "min": r[0].number_input("De kg", value=float(f_i.get('min', 0.0)), key=f"mi{i}"),
                    "max": r[1].number_input("Até kg", value=float(f_i.get('max', 0.0)), key=f"ma{i}"),
                    "col": r[2].selectbox("Coluna na Tabela", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"co{i}")
                })

            st.write("### 💰 Mapeamento de Taxas")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "SEC-CAT", "Suframa", "TRT", "TDA", "Fluvial %", "Redespacho Fluvial %", "EMEX %", "EMEX Min"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0)

            if st.button("💾 Salvar Transportadora"):
                mapa_final = {"ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig, "tab_sigla": m_tb_sig, "tab_uf": m_tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_ex}
                payload = {"nome": nome_t, "tabela_json": df_t.replace([np.inf, -np.inf], 0).fillna(0).to_dict(orient='records'), "cidades_json": df_a.fillna("").to_dict(orient='records'), "mapeamento_json": mapa_final}
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
    f_notas = st.file_uploader("Subir Notas Fiscais (Excel)", type=["xlsx"])
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)

    if f_notas and not df_ts.empty:
        selecionadas = st.multiselect("Selecione as Transportadoras", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular"):
            with st.spinner("Processando..."):
                df_base = pd.read_excel(f_notas).fillna(0)
                df_final = pd.DataFrame(index=df_base.index)
                
                # Normalização das colunas da Base de Notas
                cidade_notas = df_base.iloc[:, 2].astype(str).apply(normalizar).values
                pesos_notas = pd.to_numeric(df_base.iloc[:, 6], errors='coerce').fillna(0).values
                valores_notas = pd.to_numeric(df_base.iloc[:, 7], errors='coerce').fillna(0).values

                for t_nome in selecionadas:
                    t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
                    m = t_r['mapeamento_json']
                    df_tab = pd.DataFrame(t_r['tabela_json'])
                    df_abr = pd.DataFrame(t_r['cidades_json'])

                    # 1. Cria dicionário de Abrangência (Cidade -> Sigla)
                    df_abr['cid_norm'] = df_abr[m['ap_cidade']].astype(str).apply(normalizar)
                    dic_abr = df_abr.set_index('cid_norm')[m['ap_sigla']].to_dict()
                    
                    # 2. Faz o Match das notas com as siglas
                    siglas_match = pd.Series(cidade_notas).map(dic_abr).fillna("NOT_FOUND").values
                    
                    # 3. Indexa a Tabela de Preços pela Sigla
                    df_tab['sig_norm'] = df_tab[m['tab_sigla']].astype(str).apply(normalizar)
                    df_tab_idx = df_tab.set_index('sig_norm')

                    # --- CÁLCULO DO PESO ---
                    f_peso = np.zeros(len(df_base))
                    for f in m['faixas']:
                        if f['col'] in df_tab_idx.columns:
                            precos_col = df_tab_idx[f['col']].to_dict()
                            # Mapeia os preços da coluna para as siglas encontradas
                            valores_mapeados = np.array([precos_col.get(s, 0) for s in siglas_match])
                            mask = (pesos_notas <= f['max']) & (f_peso == 0.0)
                            f_peso[mask] = valores_mapeados[mask]

                    # Peso Extra
                    if m.get('kg_extra') in df_tab_idx.columns:
                        u_max = m['faixas'][-1]['max']
                        u_col = m['faixas'][-1]['col']
                        mask_e = (pesos_notas > u_max)
                        if mask_e.any():
                            precos_base = df_tab_idx[u_col].to_dict()
                            precos_extra = df_tab_idx[m['kg_extra']].to_dict()
                            v_base = np.array([precos_base.get(s, 0) for s in siglas_match])
                            v_extra = np.array([precos_extra.get(s, 0) for s in siglas_match])
                            f_peso[mask_e] = v_base[mask_e] + ((pesos_notas[mask_e] - u_max) * v_extra[mask_e])

                    # --- TAXAS ---
                    def gv_array(nome_taxa):
                        col_name = m['taxas'].get(nome_taxa, "Não mapear")
                        if col_name in df_tab_idx.columns:
                            dict_taxa = df_tab_idx[col_name].to_dict()
                            return np.array([dict_taxa.get(s, 0) for s in siglas_match])
                        return np.zeros(len(df_base))

                    adval = np.maximum(valores_notas * gv_array("Ad Valorem %"), gv_array("Ad Valorem Min"))
                    gris = np.maximum(valores_notas * gv_array("Gris %"), gv_array("Gris Min"))
                    emex = np.maximum(valores_notas * gv_array("EMEX %"), gv_array("EMEX Min"))
                    ped = np.ceil(pesos_notas/100) * gv_array("Pedagio")
                    fixas = gv_array("TAS") + gv_array("CTRC") + gv_array("SEC-CAT") + gv_array("Suframa") + gv_array("TRT") + gv_array("TDA")
                    fluv = (valores_notas * gv_array("Fluvial %")) + (valores_notas * gv_array("Redespacho Fluvial %"))
                    
                    df_final[f'TOTAL_{t_nome}'] = f_peso + adval + gris + emex + ped + fixas + fluv
                    
                    # UF para o histórico
                    if m['tab_uf'] in df_tab_idx.columns:
                        dict_uf = df_tab_idx[m['tab_uf']].to_dict()
                        df_final['UF'] = [dict_uf.get(s, "ND") for s in siglas_match]

                # Salvar Histórico
                df_save = df_final.fillna(0)
                lista_det = df_save.to_dict(orient='records')
                data_h = datetime.now().strftime("%d/%m/%Y %H:%M")
                total_global = float(df_save.filter(like='TOTAL_').sum().sum())
                supabase.table("cotacoes").insert({"data_hora": data_h, "total": total_global, "qtd": len(df_base), "detalhes_json": lista_det}).execute()
                st.success("Cálculo concluído com sucesso!"); st.rerun()

    # ... (Histórico igual à v9.8)
