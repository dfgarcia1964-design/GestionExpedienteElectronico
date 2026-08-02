# Iniciar garciabermeo.net (interfaz del despacho) con navegacion a todas las herramientas
Set-Location $PSScriptRoot
python -m streamlit run "Lexivox_App.py" --server.headless true --server.port 8501
