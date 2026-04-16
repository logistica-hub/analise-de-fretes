import streamlit as st
import requests
import json
import time

st.title("🧪 Teste de 5 Linhas Simultâneas")

# Sua URL do Apps Script
SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw2stGRESs-l0dJQEd3bKAawtUb8_zRH1i3VIb4DALNSjdjZnked9Lxs97ProouwR0/exec"

st.write("Clique no botão abaixo para enviar 5 registros de uma vez para a planilha.")

if st.button("🚀 Enviar 5 Linhas"):
    sucessos = 0
    for i in range(1, 6):
        payload = {
            "Nome": f"TESTE LINHA {i}",
            "Mapeamento": f"Executado em {time.strftime('%H:%M:%S')}"
        }
        
        try:
            res = requests.post(SCRIPT_URL, data=json.dumps(payload))
            if res.status_code == 200:
                st.write(f"✅ Linha {i} enviada!")
                sucessos += 1
            else:
                st.error(f"❌ Erro na linha {i}")
        except Exception as e:
            st.error(f"Falha na linha {i}: {e}")
    
    if sucessos == 5:
        st.success("Tudo pronto! Verifique sua planilha, ela deve ter 5 novas linhas.")
