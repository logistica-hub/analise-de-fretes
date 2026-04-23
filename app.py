import streamlit as st
import pandas as pd
from supabase import create_client
import numpy as np
from datetime import datetime, timedelta
import unicodedata
import re
from io import BytesIO

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Ave-Maria | Análise de Fretes", layout="wide")

# CSS Original preservado
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .metric-card {
        background-color: #ffffff;
        padding: 24px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #e2e8f0;
        text-align: center;
        transition: transform 0.2s;
    }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .metric-label { font-size: 13px; color: #64748b; margin-bottom: 8px; font-weight: 700; letter-spacing: 0.5px; }
    .metric-value { font-size: 22px; color: #1e293b; font-weight: 800; }
    h1, h2, h3 { color: #0f172a !important; font-weight: 800 !important; }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

def format_brl(val):
    if pd.isna(val) or val == 0: return "R$ 0,00"
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_kg(val):
    if pd.isna(val) or val == 0: return "0,00 kg"
    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " kg"

def super_limpeza(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).strip().upper()
    txt = re.sub(r'\s+', ' ', txt) 
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def to_excel(df_completo):
    output = BytesIO()
    cols_total = [c for c in df_completo.columns if c.startswith("TOTAL_")]
    transportadoras = [c.replace("TOTAL_", "") for c in cols_total]
    prefixos = ["PESO_BASE_", "KG_ADIC_", "ADVAL_", "GRIS_", "EMEX_", "PEDAGIO_", "TAS_", "CTRC_", "OUTROS_", "TOTAL_"]
    cols_originais = [c for c in df_completo.columns if not any(c.startswith(p) for p in prefixos)]
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_geral = df_completo[cols_originais + cols_total].copy()
        df_geral.to_excel(writer, index=False, sheet_name='Geral')
        for t in transportadoras:
            cols_especificas = [c for c in df_completo.columns if c.endswith(f'_{t}')]
            df_t = df_completo[cols_originais + cols_especificas].copy()
            df_t.columns = [c.replace(f'_{t}', '') for c in df_t.columns]
            if 'TOTAL' in df_t.columns:
                cols_ordenadas = [c for c in df_t.columns if c != 'TOTAL'] + ['TOTAL']
                df_t = df_t[cols_ordenadas]
            df_t.to_excel(writer, index=False, sheet_name=t[:31])
    return output.getvalue()

# --- SIDEBAR ---
with st.sidebar:
    st.title("Ave Maria")
    st.info("Versão 18.0")
    if 'logo_data' not in st.session_state: st.session_state.logo_data = None
    if st.session_state.logo_data:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Alterar Logo"): st.session_state.logo_data = None; st.rerun()
    else:
        up_logo = st.file_uploader("🖼️ Logo da Empresa", type=["png", "jpg", "jpeg"])
        if up_logo: st.session_state.logo_data = up_logo.read(); st.rerun()
    st.divider()
    menu = st.radio("Navegação", ["📊 Dashboard", "📂 Base Comercial", "🚛 Cadastro de Transportadora", "💰 Comparativo"])

# --- BASE COMERCIAL (NOVO) ---
if menu == "📂 Base Comercial":
    st.title("📂 Base Comercial Fixa")
    up_base = st.file_uploader("Subir Nova Base de Notas (Excel)", type=["xlsx"])
    if up_base:
        if st.button("💾 Salvar Base no Banco"):
            df_base_nova = pd.read_excel(up_base).fillna(0)
            # Salva no banco em uma tabela dedicada para a base fixa
            supabase.table("base_comercial").delete().neq("id", 0).execute() # Limpa a anterior
            supabase.table("base_comercial").insert({"dados_json": df_base_nova.to_dict(orient='records')}).execute()
            st.success("Base Comercial salva com sucesso!"); st.rerun()
    
    res_b = supabase.table("base_comercial").select("id").execute()
    if res_b.data:
        st.info("✅ Existe uma base carregada no sistema.")
        if st.button("🗑️ Excluir Base Atual"):
            supabase.table("base_comercial").delete().neq("id", 0).execute()
            st.rerun()
    else: st.warning("Nenhuma base carregada.")

# --- DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        # No dashboard, usamos apenas o resumo para ser rápido
        df_resumo_hist = pd.DataFrame(res.data)
        # (Lógica de exibição simplificada para evitar lentidão)
        st.write("Histórico de Cotações (Totais)")
        st.dataframe(df_resumo_hist[['data_hora', 'qtd', 'resumo_json']], use_container_width=True)
    else: st.info("Sem histórico.")

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
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]; cols_a = ["Não mapear"] + [str(c) for c in df_a.columns]
            cm1, cm2 = st.columns(2)
            with cm1:
                m_tb_sig = st.selectbox("Coluna Sigla (na Tabela)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
                m_tb_uf = st.selectbox("Coluna UF (na Tabela)", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)
                col_kg_ex = st.selectbox("Coluna Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            with cm2:
                m_ap_cid = st.selectbox("Coluna Cidade (na Relação)", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
                m_ap_sig = st.selectbox("Coluna Sigla (na Relação)", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            n_f = st.number_input("Qtd Faixas de Peso", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3); f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({"min": r[0].number_input("De kg", value=float(f_i.get('min', 0.0)), key=f"mi{i}"), "max": r[1].number_input("Até kg", value=float(f_i.get('max', 0.0)), key=f"ma{i}"), "col": r[2].selectbox("Coluna na Tabela", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"co{i}")})
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
    res_base = supabase.table("base_comercial").select("*").execute()
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)

    if res_base.data and not df_ts.empty:
        df_base = pd.DataFrame(res_base.data[0]['dados_json'])
        st.info(f"Base Fixa carregada: {len(df_base)} notas.")
        selecionadas = st.multiselect("Selecione as Transportadoras", df_ts['nome'].tolist())
        
        if selecionadas and st.button("🚀 Iniciar Cálculo"):
            with st.spinner("Calculando fretes..."):
                df_final = df_base.copy()
                cid_notas = df_base.iloc[:, 2].astype(str).apply(super_limpeza).values
                pesos_notas = pd.to_numeric(df_base.iloc[:, 6], errors='coerce').fillna(0).values
                valores_notas = pd.to_numeric(df_base.iloc[:, 7], errors='coerce').fillna(0).values

                resumo_calculo = {}
                for t_nome in selecionadas:
                    t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
                    m, df_tab, df_abr = t_r['mapeamento_json'], pd.DataFrame(t_r['tabela_json']), pd.DataFrame(t_r['cidades_json'])
                    df_abr['cid_clean'] = df_abr[m['ap_cidade']].astype(str).apply(super_limpeza)
                    dic_ponte = df_abr.set_index('cid_clean')[m['ap_sigla']].astype(str).apply(super_limpeza).to_dict()
                    siglas_match = pd.Series(cid_notas).map(dic_ponte).fillna("ND").values
                    df_tab['sig_clean'] = df_tab[m['tab_sigla']].astype(str).apply(super_limpeza)
                    df_tab_idx = df_tab.set_index('sig_clean')

                    def get_v(col):
                        if col and col != "Não mapear" and col in df_tab_idx.columns: return df_tab_idx[col].reindex(siglas_match).fillna(0).values
                        return np.zeros(len(df_base))

                    f_peso = np.zeros(len(df_base)); v_kg_adic = np.zeros(len(df_base))
                    for faixa in m['faixas']:
                        v_f = get_v(faixa['col']); mask = (pesos_notas <= faixa['max']) & (f_peso == 0.0); f_peso[mask] = v_f[mask]
                    u_max = m['faixas'][-1]['max']; mask_e = (pesos_notas > u_max)
                    if mask_e.any():
                        v_b = get_v(m['faixas'][-1]['col']); v_ex = get_v(m['kg_extra'])
                        v_kg_adic[mask_e] = (pesos_notas[mask_e] - u_max) * v_ex[mask_e]; f_peso[mask_e] = v_b[mask_e] + v_kg_adic[mask_e]

                    adv = np.maximum(valores_notas * get_v(m['taxas'].get("Ad Valorem %")), get_v(m['taxas'].get("Ad Valorem Min")))
                    grs = np.maximum(valores_notas * get_v(m['taxas'].get("Gris %")), get_v(m['taxas'].get("Gris Min")))
                    emx = np.maximum(valores_notas * get_v(m['taxas'].get("Emex %")), get_v(m['taxas'].get("Emex Min")))
                    ped = np.ceil(pesos_notas/100) * get_v(m['taxas'].get("Pedagio"))
                    tas, ctrc = get_v(m['taxas'].get("TAS")), get_v(m['taxas'].get("CTRC"))
                    outros = (valores_notas * get_v(m['taxas'].get("Suframa"))) + (valores_notas * get_v(m['taxas'].get("Fluvial"))) + get_v(m['taxas'].get("Redespacho Fluvial"))
                    
                    # Colunas para o Excel (em memória)
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
                    resumo_calculo[t_nome] = df_final[f'TOTAL_{t_nome}'].sum()

                # Salva apenas o RESUMO no banco (evita erro de tamanho)
                data_sao_paulo = datetime.utcnow() - timedelta(hours=3)
                supabase.table("cotacoes").insert({
                    "data_hora": data_sao_paulo.strftime("%d/%m/%Y %H:%M"),
                    "qtd": len(df_base),
                    "resumo_json": resumo_calculo # Apenas os totais
                }).execute()
                st.success("Cálculo Finalizado!")
                st.download_button("📥 Baixar Excel Detalhado (Taxa a Taxa)", data=to_excel(df_final), file_name="Comparativo_Detalhado.xlsx")
    else: st.warning("Certifique-se de ter uma Base Comercial e Transportadoras cadastradas.")
