import streamlit as st
import pandas as pd
import sqlite3
import json
import io
import os
from datetime import datetime
import math
import requests
import unicodedata

# 1. Configuração de Layout
st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")

SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw2stGRESs-l0dJQEd3bKAawtUb8_zRH1i3VIb4DALNSjdjZnked9Lxs97ProouwR0/exec"

def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def formata_br(valor):
    try:
        if pd.isna(valor) or valor == 0: return "0,00"
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"

DB_NAME = 'comparativo_v19.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cotacoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, transportadora TEXT, 
                  total REAL, qtd INTEGER, detalhes_json TEXT)''')
    conn.commit()
    conn.close()

init_db()

if 'edit_id' not in st.session_state: st.session_state.edit_id = None

# --- SIDEBAR ---
with st.sidebar:
    if 'logo_data' not in st.session_state: st.session_state.logo_data = None
    if st.session_state.logo_data:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Editar Logo"):
            st.session_state.logo_data = None
            st.rerun()
    else:
        up = st.file_uploader("🖼️ Subir Logo", type=["png", "jpg"])
        if up: st.session_state.logo_data = up.read(); st.rerun()
    
    st.divider()
    menu = st.radio("MENU PRINCIPAL", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])
    
    st.divider()
    st.subheader("💾 Gestão de Dados")
    try:
        if os.path.exists(DB_NAME):
            with open(DB_NAME, "rb") as f:
                st.download_button("📥 Baixar Backup Atual", f, f"backup_fretes_{datetime.now().strftime('%d_%m_%H%M')}.db", "application/x-sqlite3")
    except: pass
    restore_file = st.file_uploader("📤 Restaurar Backup (.db)", type=["db"])
    if restore_file and st.button("✅ Confirmar Restauração"):
        with open(DB_NAME, "wb") as f: f.write(restore_file.getbuffer())
        st.success("Dados restaurados!"); st.rerun()

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()
    
    if not df_h.empty:
        all_data = []
        for _, row in df_h.iterrows():
            try:
                temp_df = pd.read_json(io.StringIO(row['detalhes_json']))
                if 'T_NOME' not in temp_df.columns: temp_df['T_NOME'] = row['transportadora']
                all_data.append(temp_df)
            except: continue
        
        if all_data:
            df_full = pd.concat(all_data, ignore_index=True)
            st.subheader("🎯 Filtros")
            f1, f2 = st.columns(2)
            sel_t = f1.multiselect("Transportadora", options=df_full['T_NOME'].unique())
            sel_uf = f2.multiselect("UF", options=df_full['UF'].unique() if 'UF' in df_full.columns else ["N/A"])

            if sel_t: df_full = df_full[df_full['T_NOME'].isin(sel_t)]
            if sel_uf: df_full = df_full[df_full['UF'].isin(sel_uf)]

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Cotado", f"R$ {formata_br(df_full['VALOR_SISTEMA'].sum())}")
            c2.metric("Notas Processadas", f"{len(df_full)}")
            c3.metric("Peso Total", f"{formata_br(df_full['PESO'].sum())} kg")
            
            st.subheader("📍 Resumo por UF e Transportadora")
            if 'UF' in df_full.columns:
                pivot_uf = df_full.pivot_table(index='UF', columns='T_NOME', values='VALOR_SISTEMA', aggfunc='sum', fill_value=0)
                st.dataframe(pivot_uf.map(formata_br), use_container_width=True)
    else:
        st.info("Nenhuma cotação no histórico.")

# --- TRANSPORTADORAS ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    is_editing = st.session_state.edit_id is not None
    
    with st.expander("📝 Configurar Mapeamento", expanded=is_editing):
        edit_data = None
        mapa_previo = {"faixas": [], "taxas": {}, "kg_extra": "Não mapear", "col_cid": "Não mapear", "col_sigla": "Não mapear"}
        if is_editing:
            conn = sqlite3.connect(DB_NAME)
            edit_data = pd.read_sql_query(f"SELECT * FROM transportadoras WHERE id={st.session_state.edit_id}", conn).iloc[0]
            conn.close()
            mapa_previo = json.loads(edit_data['mapeamento_json'])

        t_nome = st.text_input("Nome da Transportadora", value=edit_data['nome'] if is_editing else "").upper()
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("Tabela de Preços (Excel)", type=["xlsx"])
        f_cid = c2.file_uploader("Planilha de Apoio (Cidades)", type=["xlsx"])
        
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.read_json(io.StringIO(edit_data['tabela_json'])) if is_editing else None)
        df_c = pd.read_excel(f_cid).fillna(0) if f_cid else (pd.read_json(io.StringIO(edit_data['cidades_json'])) if is_editing else None)

        if df_t is not None and df_c is not None:
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_c = ["Não mapear"] + [str(c) for c in df_c.columns]
            
            st.subheader("📍 Mapeamento")
            m1, m2 = st.columns(2)
            m_col_cid = m1.selectbox("Coluna Cidade", cols_c, index=cols_c.index(str(mapa_previo.get('col_cid'))) if str(mapa_previo.get('col_cid')) in cols_c else 0)
            m_col_sigla = m2.selectbox("Coluna Sigla", cols_c, index=cols_c.index(str(mapa_previo.get('col_sigla'))) if str(mapa_previo.get('col_sigla')) in cols_c else 0)

            st.subheader("⚖️ Regras de Peso")
            col_kg_extra = st.selectbox("Kg Adicional", cols_t, index=cols_t.index(str(mapa_previo.get('kg_extra'))) if str(mapa_previo.get('kg_extra')) in cols_t else 0)
            n_f = st.number_input("Qtd Faixas", 1, 50, len(mapa_previo['faixas']) if is_editing else 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3)
                f_ini = mapa_previo['faixas'][i] if is_editing and i < len(mapa_previo['faixas']) else {}
                faixas.append({"min": r[0].number_input(f"De", value=float(f_ini.get('min', 0.0)), key=f"mi{i}"), "max": r[1].number_input(f"Até", value=float(f_ini.get('max', 0.0)), key=f"ma{i}"), "col": r[2].selectbox(f"Coluna", cols_t, index=cols_t.index(str(f_ini.get('col'))) if str(f_ini.get('col')) in cols_t else 0, key=f"co{i}")})
            
            st.subheader("💰 Taxas Adicionais")
            taxas_n = [
                "Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", 
                "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", 
                "SEC-CAT", "Suframa (Fixo)", "Fluvial %", "Redespacho Fluvial %"
            ]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_n):
                s_tx = str(mapa_previo.get('taxas', {}).get(tx, "Não mapear"))
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(s_tx) if s_tx in cols_t else 0, key=f"tx_{tx}")

            if st.button("💾 Salvar"):
                mapa = {"faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_extra, "col_cid": m_col_cid, "col_sigla": m_col_sigla}
                conn = sqlite3.connect(DB_NAME)
                if is_editing:
                    conn.execute("UPDATE transportadoras SET nome=?, tabela_json=?, cidades_json=?, mapeamento_json=? WHERE id=?", (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa), st.session_state.edit_id))
                else:
                    conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)", (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa)))
                conn.commit(); conn.close(); st.session_state.edit_id = None; st.rerun()

    ts = pd.read_sql_query("SELECT id, nome FROM transportadoras", sqlite3.connect(DB_NAME))
    for _, row in ts.iterrows():
        c1, c2, c3 = st.columns([7, 1.5, 1.5])
        c1.write(f"**{row['nome']}**")
        if c2.button("✏️", key=f"ed_{row['id']}"): st.session_state.edit_id = row['id']; st.rerun()
        if c3.button("🗑️", key=f"dl_{row['id']}"):
            conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM transportadoras WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()

# --- COMPARATIVO ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo de Fretes")
    f_base = st.file_uploader("📥 Subir Planilha de Notas Fiscais (Base)", type=["xlsx"])
    
    conn = sqlite3.connect(DB_NAME)
    ts_db = pd.read_sql_query("SELECT * FROM transportadoras", conn)
    conn.close()
    
    if not ts_db.empty:
        opcoes = ts_db['nome'].tolist()
        selecionadas = st.multiselect("Selecione as Transportadoras para cotação", options=opcoes, default=opcoes[:1])
        
        if f_base and selecionadas and st.button("🚀 Calcular Agora"):
            df_b_original = pd.read_excel(f_base).fillna(0)
            consolidado_historico = []
            
            for t_nome in selecionadas:
                t_row = ts_db[ts_db['nome'] == t_nome].iloc[0]
                df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
                df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
                mapa = json.loads(t_row['mapeamento_json'])
                
                df_b = df_b_original.copy()
                df_b['BUSCA_NF'] = df_b.iloc[:, 2].apply(normalizar)
                df_cid_ref['BUSCA_REF'] = df_cid_ref[mapa['col_cid']].apply(normalizar)
                df_proc = pd.merge(df_b, df_cid_ref[['BUSCA_REF', mapa['col_sigla']]], left_on='BUSCA_NF', right_on='BUSCA_REF', how='left')
                df_tab['SIGLA_CHAVE'] = df_tab.iloc[:, 2].apply(normalizar)

                res_transp = []
                for _, nf in df_proc.iterrows():
                    try:
                        peso_nf = float(nf.iloc[6]); valor_nf = float(nf.iloc[7]); sigla = normalizar(str(nf[mapa['col_sigla']]))
                        linha_preco = df_tab[df_tab['SIGLA_CHAVE'] == sigla].iloc[0]
                        f_peso = 0.0; u_max = 0; u_col = ""; d = False
                        for f in mapa['faixas']:
                            u_max, u_col = f['max'], f['col']
                            if peso_nf <= f['max'] and f['col'] != "Não mapear":
                                f_peso = float(linha_preco[f['col']]); d = True; break
                        if not d and mapa.get('kg_extra') != "Não mapear":
                            f_peso = float(linha_preco[u_col]) + ((peso_nf - u_max) * float(linha_preco[mapa['kg_extra']]))
                        
                        def gv(n): return float(linha_preco[mapa['taxas'][n]]) if n in mapa['taxas'] and mapa['taxas'][n] != "Não mapear" else 0.0
                        
                        tx_adval = max(valor_nf * gv("Ad Valorem %"), gv("Ad Valorem Min"))
                        tx_gris = max(valor_nf * gv("Gris %"), gv("Gris Min"))
                        tx_pedagio = (math.ceil(peso_nf/100)*gv("Pedagio"))
                        tx_tas = gv("TAS")
                        tx_ctrc = gv("CTRC")
                        tx_trt = gv("TRT")
                        tx_tda = gv("TDA")
                        tx_seccat = gv("SEC-CAT")
                        tx_emex = max(valor_nf * gv("Emex %"), gv("Emex Min"))
                        tx_suframa = gv("Suframa (Fixo)")
                        tx_fluvial = valor_nf * gv("Fluvial %")
                        tx_red_fluvial = valor_nf * gv("Redespacho Fluvial %")
                        
                        total = f_peso + tx_adval + tx_gris + tx_pedagio + tx_tas + tx_ctrc + tx_trt + tx_tda + tx_seccat + tx_emex + tx_suframa + tx_fluvial + tx_red_fluvial
                        
                        item = nf.to_dict()
                        item.update({
                            "VALOR_SISTEMA": round(total, 2), "T_NOME": t_nome, "F_PESO": f_peso, 
                            "ADVAL": tx_adval, "GRIS": tx_gris, "PEDAGIO": tx_pedagio, "TAS": tx_tas,
                            "CTRC": tx_ctrc, "TRT": tx_trt, "TDA": tx_tda, "SECCAT": tx_seccat,
                            "EMEX": tx_emex, "SUFRAMA": tx_suframa, "FLUVIAL": tx_fluvial, "RED_FLUVIAL": tx_red_fluvial
                        })
                        res_transp.append(item)
                    except:
                        item = nf.to_dict(); item.update({"VALOR_SISTEMA": 0.0, "T_NOME": t_nome}); res_transp.append(item)
                
                consolidado_historico.extend(res_transp)
            
            df_final = pd.DataFrame(consolidado_historico)
            nome_label = "COMPARATIVO MULTIPLO" if len(selecionadas) > 1 else selecionadas[0]
            conn = sqlite3.connect(DB_NAME)
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json) VALUES (?,?,?,?,?)",
                         (datetime.now().strftime("%d/%m/%Y %H:%M"), nome_label, df_final['VALOR_SISTEMA'].sum(), len(df_b_original), df_final.to_json()))
            conn.commit(); conn.close()
            st.success(f"Cálculo concluído!"); st.rerun()

    st.divider()
    st.subheader("🕒 Histórico")
    conn = sqlite3.connect(DB_NAME); df_h = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn); conn.close()
    
    for _, row in df_h.iterrows():
        try:
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            if 'T_NOME' not in df_det.columns: df_det['T_NOME'] = row['transportadora']
            transp_unicas = df_det['T_NOME'].unique()
            is_multitransp = len(transp_unicas) > 1
            
            with st.expander(f"📅 {row['data_hora']} | {row['transportadora']} | Total: R$ {formata_br(row['total'])}"):
                if st.button("🗑️ Excluir", key=f"del_{row['id']}"):
                    conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()
                
                notas_ids = df_det['NF'].unique()
                for nf_id in notas_ids:
                    dados_nota = df_det[df_det['NF'] == nf_id]
                    cidade = dados_nota.iloc[0]['CIDADE']
                    
                    with st.expander(f"👁️ Nota: {nf_id} - {cidade}"):
                        if is_multitransp:
                            st.write("**Resumo por Transportadora:**")
                            df_comp = dados_nota[['T_NOME', 'VALOR_SISTEMA']].sort_values(by='VALOR_SISTEMA')
                            df_comp.columns = ['Transportadora', 'Valor Total']
                            st.table(df_comp.assign(Valor=df_comp['Valor Total'].apply(formata_br))[['Transportadora', 'Valor']])
                        else:
                            n = dados_nota.iloc[0]
                            st.markdown(f"**Frete Peso:** R$ {formata_br(n.get('F_PESO',0))}")
                            
                            # LISTAGEM INDIVIDUALIZADA (SÓ MOSTRA SE > 0)
                            taxas_lista = {
                                "Ad Valorem": n.get('ADVAL',0),
                                "Gris": n.get('GRIS',0),
                                "Pedágio": n.get('PEDAGIO',0),
                                "TAS": n.get('TAS',0),
                                "CTRC": n.get('CTRC',0),
                                "TRT": n.get('TRT',0),
                                "TDA": n.get('TDA',0),
                                "SEC-CAT": n.get('SECCAT',0),
                                "Emex": n.get('EMEX',0),
                                "Suframa": n.get('SUFRAMA',0),
                                "Fluvial": n.get('FLUVIAL',0),
                                "Red. Fluvial": n.get('RED_FLUVIAL',0)
                            }
                            
                            for label, valor in taxas_lista.items():
                                if valor > 0:
                                    st.markdown(f"**{label}:** R$ {formata_br(valor)}")
                            
                            st.divider()
                            st.subheader(f"Total: R$ {formata_br(n['VALOR_SISTEMA'])}")
        except:
            if st.button(f"⚠️ Erro nos dados (ID {row['id']})", key=f"err_{row['id']}"):
                conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()
