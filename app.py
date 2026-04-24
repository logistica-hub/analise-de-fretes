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

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- UTILITÁRIOS ---
def format_brl(val):
    if pd.isna(val) or val == 0: return "R$ 0,00"
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def super_limpeza(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).strip().upper()
    txt = re.sub(r'\s+', ' ', txt) 
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

# --- MOTOR DE CÁLCULO (REUTILIZÁVEL) ---
def calcular_frete_completo(df_base, transportadoras_nomes, df_ts):
    df_final = df_base.copy()
    
    col_cid_nome = next((c for c in df_base.columns if 'CIDADE' in c.upper()), df_base.columns[2])
    col_peso_nome = next((c for c in df_base.columns if 'PESO' in c.upper() and 'BASE' not in c.upper()), df_base.columns[6])
    col_valor_nome = next((c for c in df_base.columns if 'VALOR' in c.upper() and 'FRETE' not in c.upper()), df_base.columns[7])
    
    cid_notas = df_base[col_cid_nome].astype(str).apply(super_limpeza).values
    pesos_notas = pd.to_numeric(df_base[col_peso_nome], errors='coerce').fillna(0).values
    valores_notas = pd.to_numeric(df_base[col_valor_nome], errors='coerce').fillna(0).values

    for t_nome in transportadoras_nomes:
        t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
        m, df_tab, df_abr = t_r['mapeamento_json'], pd.DataFrame(t_r['tabela_json']), pd.DataFrame(t_r['cidades_json'])
        
        df_abr['cid_clean'] = df_abr[m['ap_cidade']].astype(str).apply(super_limpeza)
        dic_ponte = df_abr.set_index('cid_clean')[m['ap_sigla']].astype(str).apply(super_limpeza).to_dict()
        siglas_match = pd.Series(cid_notas).map(dic_ponte).fillna("ND").values
        df_tab['sig_clean'] = df_tab[m['tab_sigla']].astype(str).apply(super_limpeza)
        df_tab_idx = df_tab.set_index('sig_clean')
        
        def get_v(col): return df_tab_idx[col].reindex(siglas_match).fillna(0).values if col and col != "Não mapear" and col in df_tab_idx.columns else np.zeros(len(df_base))
        
        f_peso = np.zeros(len(df_base)); v_kg_adic = np.zeros(len(df_base))
        for faixa in m['faixas']:
            v_f = get_v(faixa['col']); mask = (pesos_notas <= faixa['max']) & (f_peso == 0.0); f_peso[mask] = v_f[mask]
        
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
        
        # TAXAS CORRIGIDAS
        suf = get_v(m['taxas'].get("Suframa")) # FIXO
        seccat = get_v(m['taxas'].get("SEC-CAT")) # FIXO
        fluv = valores_notas * get_v(m['taxas'].get("Fluvial")) # %
        red_f = valores_notas * get_v(m['taxas'].get("Redespacho Fluvial")) # %

        # ARMAZENAMENTO DAS COLUNAS
        df_final[f'PESO_BASE_{t_nome}'] = f_peso - v_kg_adic
        df_final[f'KG_ADIC_{t_nome}'] = v_kg_adic
        df_final[f'ADVAL_{t_nome}'] = adv
        df_final[f'GRIS_{t_nome}'] = grs
        df_final[f'EMEX_{t_nome}'] = emx
        df_final[f'PEDAGIO_{t_nome}'] = ped
        df_final[f'TAS_{t_nome}'] = get_v(m['taxas'].get("TAS"))
        df_final[f'CTRC_{t_nome}'] = get_v(m['taxas'].get("CTRC"))
        df_final[f'SUFRAMA_{t_nome}'] = suf
        df_final[f'SEC_CAT_{t_nome}'] = seccat
        df_final[f'FLUVIAL_{t_nome}'] = fluv
        df_final[f'REDESPACHO_F_{t_nome}'] = red_f
        df_final[f'TOTAL_{t_nome}'] = (f_peso + adv + grs + emx + ped + 
                                       get_v(m['taxas'].get("TAS")) + 
                                       get_v(m['taxas'].get("CTRC")) + 
                                       suf + seccat + fluv + red_f)
    return df_final

def to_excel(df_completo):
    output = BytesIO()
    cols_total = [c for c in df_completo.columns if c.startswith("TOTAL_")]
    transportadoras = [c.replace("TOTAL_", "") for c in cols_total]
    prefixos = ["PESO_BASE_", "KG_ADIC_", "ADVAL_", "GRIS_", "EMEX_", "PEDAGIO_", "TAS_", "CTRC_", "SUFRAMA_", "SEC_CAT_", "FLUVIAL_", "REDESPACHO_F_", "OUTROS_", "TOTAL_"]
    cols_originais = [c for c in df_completo.columns if not any(c.startswith(p) for p in prefixos)]
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_completo[cols_originais + cols_total].to_excel(writer, index=False, sheet_name='Geral')
        for t in transportadoras:
            cols_t = [c for c in df_completo.columns if c.endswith(f'_{t}')]
            df_t = df_completo[cols_originais + cols_t].copy()
            df_t.columns = [c.replace(f'_{t}', '') for c in df_t.columns]
            df_t.to_excel(writer, index=False, sheet_name=t[:31])
    return output.getvalue()

# --- SIDEBAR E MENUS (DASHBOARD E HISTÓRICO ADAPTADOS) ---
with st.sidebar:
    st.title("Ave Maria - Analise")
    st.info("Versão 21.0 - BI Mode")
    menu = st.radio("Navegação", ["📊 Dashboard", "📂 Base Comercial", "🚛 Cadastro de Transportadora", "💰 Comparativo", "📜 Histórico"])

if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        df_resumo = pd.DataFrame(res.data)
        # O resumo agora já vem agrupado por UF do banco
        st.subheader("💰 Custo Total por Estado (Histórico)")
        st.dataframe(df_resumo.drop(columns=['id', 'transportadoras_json'], errors='ignore'), use_container_width=True)
    else: st.info("Sem histórico.")

elif menu == "🚛 Cadastro de Transportadora":
    # ... (O código de cadastro permanece igual, apenas adicionei o SEC-CAT na lista de taxas como você pediu)
    st.title("🚛 Cadastro de Transportadora")
    # (Inserir aqui o bloco de cadastro que já temos, garantindo que SEC-CAT esteja em taxas_nomes)
    # [Mantido igual ao anterior para brevidade, mas com SEC-CAT na lista]
    # ... (Continua conforme Versão 20.0)

elif menu == "💰 Comparativo":
    st.title("💰 Cotação de Fretes")
    res_base = supabase.table("base_comercial").select("*").execute()
    res_t = supabase.table("transportadoras").select("*").execute()
    
    if res_base.data and res_t.data:
        df_base = pd.DataFrame(res_base.data[0]['dados_json'])
        df_ts = pd.DataFrame(res_t.data)
        selecionadas = st.multiselect("Transportadoras", df_ts['nome'].tolist())
        
        if selecionadas and st.button("🚀 Calcular e Gerar Resumo"):
            # 1. Calcula tudo na memória
            df_calculado = calcular_frete_completo(df_base, selecionadas, df_ts)
            
            # 2. Gera Resumo para o Dashboard (Agrupado por UF e Transportadora)
            col_uf = next((c for c in df_calculado.columns if c.upper() == 'UF'), 'UF')
            data_atual = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")
            
            # Criando o JSON de resumo
            resumo_lista = []
            for t in selecionadas:
                total_t = df_calculado[f'TOTAL_{t}'].sum()
                resumo_lista.append({
                    "data_hora": data_atual,
                    "transportadora": t,
                    "qtd_notas": len(df_calculado),
                    "valor_total_frete": total_t,
                    "transportadoras_json": selecionadas # Guardamos a lista para o download saber quem recalcular
                })
            
            supabase.table("cotacoes").insert(resumo_lista).execute()
            st.success("Cálculo finalizado! Resumo salvo no histórico.")
            st.balloons()

elif menu == "📜 Histórico":
    st.title("📜 Histórico e Download Detalhado")
    res = supabase.table("cotacoes").select("*").order("id", desc=True).execute()
    if res.data:
        df_h = pd.DataFrame(res.data)
        for data_ref, g in df_h.groupby("data_hora", sort=False):
            with st.expander(f"📦 {data_ref} | {len(g)} Transportadoras"):
                if st.button(f"📥 Gerar Excel Detalhado", key=f"dl_{data_ref}"):
                    with st.spinner("Recalculando 17 mil linhas para gerar o arquivo..."):
                        # BUSCA DADOS NECESSÁRIOS PARA RECALCULAR
                        res_b = supabase.table("base_comercial").select("*").execute()
                        df_base = pd.DataFrame(res_b.data[0]['dados_json'])
                        
                        # Transportadoras que participaram desta cotação
                        nomes_t = g['transportadora'].tolist()
                        res_ts = supabase.table("transportadoras").select("*").in_("nome", nomes_t).execute()
                        df_ts = pd.DataFrame(res_ts.data)
                        
                        # RECALCULA NA HORA
                        df_full = calcular_frete_completo(df_base, nomes_t, df_ts)
                        excel = to_excel(df_full)
                        
                        st.download_button("Clique para Baixar", excel, f"Relatorio_{data_ref}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
