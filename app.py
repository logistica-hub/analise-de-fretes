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
st.set_page_config(page_title="Ave-Maria | Gestão de Fretes", layout="wide")

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

# --- SIDEBAR (LOGO E NAVEGAÇÃO) ---
with st.sidebar:
    # 1. GESTÃO DO LOGO
    if 'logo_data' not in st.session_state:
        # Tenta buscar do Supabase ou manter em cache de sessão
        st.session_state.logo_data = None

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
    menu = st.radio("MENU", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])
    st.divider()
    st.caption("Conectado ao Supabase Cloud ✅")

# --- DASHBOARD (PONTOS 4 E 5) ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    
    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        all_data = []
        for r in res.data:
            temp_df = pd.DataFrame(r['detalhes_json'])
            all_data.append(temp_df)
        
        df_total = pd.concat(all_data, ignore_index=True)

        # 5. FILTROS
        st.subheader("🎯 Filtros")
        f1, f2 = st.columns(2)
        filtro_uf = f1.multiselect("Filtrar por UF", options=sorted(df_total['UF'].unique().tolist()))
        filtro_tr = f2.multiselect("Filtrar por Transportadora", options=df_total['T_NOME'].unique().tolist())

        if filtro_uf: df_total = df_total[df_total['UF'].isin(filtro_uf)]
        if filtro_tr: df_total = df_total[df_total['T_NOME'].isin(filtro_tr)]

        # 4. CONSOLIDADO UF E VALOR
        c1, c2 = st.columns([2, 1])
        
        consolidado = df_total.groupby(['UF', 'T_NOME'])['VALOR_SISTEMA'].sum().reset_index()
        consolidado['VALOR_FORMATADO'] = consolidado['VALOR_SISTEMA'].apply(lambda x: f"R$ {formata_br(x)}")
        
        c1.subheader("💰 Total por UF e Transportadora")
        st.dataframe(consolidado, use_container_width=True)
        
        total_geral = df_total['VALOR_SISTEMA'].sum()
        st.metric("Total Geral Cotado", f"R$ {formata_br(total_geral)}")
    else:
        st.info("Aguardando dados para gerar indicadores.")

# --- TRANSPORTADORAS (PONTO 2 - MAPEAMENTO TOTAL) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Configuração de Transportadoras")
    
    res_t = supabase.table("transportadoras").select("*").execute()
    df_list = pd.DataFrame(res_t.data)

    with st.expander("📝 Configurar Nova / Editar", expanded=st.session_state.get('edit_id') is not None):
        e_id = st.session_state.get('edit_id')
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id is not None else None
        
        nome_t = st.text_input("Nome da Transportadora", value=e_row['nome'] if e_row is not None else "").upper()
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("Subir Tabela de Preços")
        f_abr = c2.file_uploader("Subir Planilha de Abrangência")

        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.DataFrame(e_row['tabela_json']) if e_row is not None else None)
        df_a = pd.read_excel(f_abr).fillna(0) if f_abr else (pd.DataFrame(e_row['cidades_json']) if e_row is not None else None)

        if df_t is not None and df_a is not None:
            mapa = e_row['mapeamento_json'] if e_row is not None else {}
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_a = ["Não mapear"] + [str(c) for c in df_a.columns]

            st.subheader("🔗 Ligações e Siglas")
            l1, l2 = st.columns(2)
            m_ap_cid = l1.selectbox("Abrangência: Coluna Cidade", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
            m_ap_sig = l1.selectbox("Abrangência: Coluna Sigla", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            m_tb_sig = l2.selectbox("Tabela: Coluna Sigla (Match)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
            m_tb_uf = l2.selectbox("Tabela: Coluna UF", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)

            st.subheader("⚖️ Faixas de Peso")
            col_kg_ex = st.selectbox("Preço Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            n_faixas = st.number_input("Qtd Faixas", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(n_faixas)):
                r = st.columns(3)
                f_ini = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({
                    "min": r[0].number_input("De kg", value=float(f_ini.get('min', 0.0)), key=f"min{i}"),
                    "max": r[1].number_input("Até kg", value=float(f_ini.get('max', 0.0)), key=f"max{i}"),
                    "col": r[2].selectbox("Coluna na Tabela", cols_t, index=cols_t.index(f_ini.get('col')) if f_ini.get('col') in cols_t else 0, key=f"col{i}")
                })

            st.subheader("💰 Todas as Taxas")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "SEC-CAT", "Suframa", "EMEX", "TRT", "TDA"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0)

            if st.button("💾 Salvar no Supabase"):
                mapa_final = {"ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig, "tab_sigla": m_tb_sig, "tab_uf": m_tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_ex}
                payload = {"nome": nome_t, "tabela_json": df_t.to_dict(orient='records'), "cidades_json": df_a.to_dict(orient='records'), "mapeamento_json": mapa_final}
                if e_id: supabase.table("transportadoras").update(payload).eq("id", e_id).execute()
                else: supabase.table("transportadoras").insert(payload).execute()
                st.session_state.edit_id = None; st.rerun()

    # LISTAGEM
    for _, r in df_list.iterrows():
        c = st.columns([7, 1, 1])
        c[0].write(f"**{r['nome']}**")
        if c[1].button("✏️", key=f"ed{r['id']}"): st.session_state.edit_id = r['id']; st.rerun()
        if c[2].button("🗑️", key=f"dl{r['id']}"): supabase.table("transportadoras").delete().eq("id", r['id']).execute(); st.rerun()

# --- COMPARATIVO (PONTO 3 - LISTAGEM E EXPANSÃO) ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo Massivo")
    
    f_notas = st.file_uploader("📥 Planilha de Notas Fiscais (Vetorização 18k)")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)

    if f_notas and not df_ts.empty:
        selecionadas = st.multiselect("Selecione as Transportadoras", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular Agora"):
            with st.spinner("Processando milhares de linhas..."):
                df_base = pd.read_excel(f_notas).fillna(0)
                resultados_lote = []
                
                for t_nome in selecionadas:
                    t_row = df_ts[df_ts['nome'] == t_nome].iloc[0]
                    m = t_row['mapeamento_json']
                    df_tab = pd.DataFrame(t_row['tabela_json'])
                    df_abr = pd.DataFrame(t_row['cidades_json'])
                    
                    df_calc = df_base.copy()
                    df_calc['KEY_CIDADE'] = df_calc.iloc[:, 2].astype(str).apply(normalizar)
                    df_abr['KEY_REF'] = df_abr[m['ap_cidade']].astype(str).apply(normalizar)
                    df_tab['KEY_TAB'] = df_tab[m['tab_sigla']].astype(str).apply(normalizar)
                    
                    df_m1 = pd.merge(df_calc, df_abr[[m['ap_sigla'], 'KEY_REF']], left_on='KEY_CIDADE', right_on='KEY_REF', how='left')
                    df_m1['KEY_MATCH'] = df_m1[m['ap_sigla']].astype(str).apply(normalizar)
                    df_final = pd.merge(df_m1, df_tab, left_on='KEY_MATCH', right_on='KEY_TAB', how='left')
                    
                    peso = pd.to_numeric(df_final.iloc[:, 6], errors='coerce').fillna(0)
                    valor = pd.to_numeric(df_final.iloc[:, 7], errors='coerce').fillna(0)
                    
                    df_final['F_PESO'] = 0.0
                    for f in m['faixas']:
                        if f['col'] in df_final.columns:
                            mask = (peso <= f['max']) & (df_final['F_PESO'] == 0.0)
                            df_final.loc[mask, 'F_PESO'] = pd.to_numeric(df_final.loc[mask, f['col']], errors='coerce').fillna(0)
                    
                    if m.get('kg_extra') in df_final.columns:
                        u_max = m['faixas'][-1]['max']
                        u_col = m['faixas'][-1]['col']
                        mask_e = (peso > u_max)
                        df_final.loc[mask_e, 'F_PESO'] = pd.to_numeric(df_final.loc[mask_e, u_col], errors='coerce').fillna(0) + ((peso[mask_e] - u_max) * pd.to_numeric(df_final.loc[mask_e, m['kg_extra']], errors='coerce').fillna(0))

                    def gv(name):
                        col = m['taxas'].get(name, "Não mapear")
                        return pd.to_numeric(df_final[col], errors='coerce').fillna(0) if col in df_final.columns else 0.0

                    df_final['ADVAL'] = np.maximum(valor * gv("Ad Valorem %"), gv("Ad Valorem Min"))
                    df_final['GRIS'] = np.maximum(valor * gv("Gris %"), gv("Gris Min"))
                    df_final['PEDAGIO'] = np.ceil(peso / 100) * gv("Pedagio")
                    df_final['OUTRAS_TAXAS'] = gv("TAS") + gv("CTRC") + gv("SEC-CAT") + gv("Suframa") + gv("EMEX") + gv("TRT") + gv("TDA")
                    df_final['VALOR_SISTEMA'] = df_final['F_PESO'] + df_final['ADVAL'] + df_final['GRIS'] + df_final['PEDAGIO'] + df_final['OUTRAS_TAXAS']
                    df_final['T_NOME'] = t_nome
                    df_final['UF'] = df_final[m['tab_uf']]
                    
                    resultados_lote.append(df_final)

                df_full = pd.concat(resultados_lote)
                payload = {"data_hora": datetime.now().strftime("%d/%m/%Y %H:%M"), "total": float(df_full['VALOR_SISTEMA'].sum()), "qtd": len(df_base), "detalhes_json": df_full.to_dict(orient='records')}
                supabase.table("cotacoes").insert(payload).execute()
                st.success("Calculado com sucesso!"); st.rerun()

    st.divider()
    st.subheader("🕒 Histórico de Comparativos")
    res_h = supabase.table("cotacoes").select("*").order("id", desc=True).execute()
    
    for r in res_h.data:
        with st.expander(f"📅 {r['data_hora']} | {r['qtd']} notas | R$ {formata_br(r['total'])}"):
            df_h = pd.DataFrame(r['detalhes_json'])
            tr_unificadas = df_h['T_NOME'].unique()
            
            # REGRA 3: Detalhado (1 transp) vs Consolidado (várias)
            if len(tr_unificadas) == 1:
                st.write(f"**Detalhamento Taxa a Taxa - {tr_unificadas[0]}**")
                cols_view = ['VALOR_SISTEMA', 'F_PESO', 'ADVAL', 'GRIS', 'PEDAGIO', 'OUTRAS_TAXAS']
                st.dataframe(df_h[['UF'] + cols_view], use_container_width=True)
            else:
                st.write("**Consolidado por Transportadora**")
                resumo = df_h.groupby('T_NOME')['VALOR_SISTEMA'].sum().reset_index()
                resumo['VALOR_SISTEMA'] = resumo['VALOR_SISTEMA'].apply(lambda x: f"R$ {formata_br(x)}")
                st.table(resumo)
                if st.button("👁️ Ver todas as notas", key=f"btn_{r['id']}"):
                    st.dataframe(df_h)
            
            if st.button("🗑️ Excluir Lote", key=f"del_lote_{r['id']}"):
                supabase.table("cotacoes").delete().eq("id", r['id']).execute()
                st.rerun()
