Créditos arquivo GeoJSON de Minas Gerais: https://github.com/tbrugz/geodata-br/blob/master/geojson/geojs-31-mun.json

Indicadores municipais do IBGE
Depois de criar o banco com bd/populaBanco.py, atualize os indicadores do IBGE executando:
    .\venv\Scripts\python.exe bd\atualizaIndicadoresIBGE.py

O script consulta a API do IBGE e atualiza população estimada, PIB e dados do Censo 2022.
