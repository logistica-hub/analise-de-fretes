import streamlit as st
import requests
import json

st.title("🧪 Teste de Gravação Direta")

# Sua URL do Apps Script
SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw2stGRESs-l0dJQEd3bKAawtUb8_zRH1i3VIb4DALNSjdjZnked9Lxs97ProouwR0/exec"

nome_teste = st.text_input("Digite algo para testar (ex: TESTE 123)")

if st.button("Enviar para Planilha"):
    if nome_teste:
        payload = {
            "Nome": nome_teste,
            "Mapeamento": "Teste de conexão rápido"
        }
        
        try:
            res = requests.post(SCRIPT_URL, data=json.dumps(payload))
            if res.status_code == 200:
                st.success(f"✅ Enviado! Verifique sua planilha agora.")
            else:
                st.error(f"Erro: {res.status_code}")
        except Exception as e:
            st.error(f"Falha técnica: {e}")
    else:
        st.warning("Escreva algo no campo acima.")
