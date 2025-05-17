import streamlit as st
import folium
import json
import sqlite3
import unicodedata
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from folium.plugins import MousePosition

# ---------- CONFIGURAÇÕES INICIAIS ----------
st.set_page_config(page_title="Mapa de Minas Gerais", layout="wide")
st.title("Casos de Violência contra Mulher em Minas Gerais")
st.write("Clique em uma cidade de Minas Gerais para ver os dados.")

# ---------- CARREGAMENTO DE DADOS ----------
with open("cidades_mg.json", "r", encoding="utf-8") as f:
    cidades_mg = json.load(f)

with open("br_mg.json", "r", encoding="utf-8") as f:
    geojson_mg = json.load(f)

# ---------- FUNÇÕES ----------
def get_city_name(lat, lon):
    geolocator = Nominatim(user_agent="geoapi_exemplo")
    try:
        location = geolocator.reverse((lat, lon), exactly_one=True)
        if location and 'address' in location.raw:
            address = location.raw['address']
            city = address.get('city', address.get('town', address.get('village', 'Cidade não encontrada')))
            return city
        return "Cidade não encontrada"
    except GeocoderTimedOut:
        return "Erro na consulta da cidade"

def consultar_dados(cidade, ano):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    def buscar_casos(tabela):
        if tabela == "crimesViolentos":
            query = f"SELECT COUNT(*) FROM {tabela} WHERE municipio = ? AND ano = ? AND registros > 0"
            cursor.execute(query, (normalizar_cidade(cidade), str(ano)))
        elif tabela == "violenciaSES":
            query = f"SELECT COUNT(*) FROM {tabela} WHERE ID_MN_RESI = ? AND substr(DT_NOTIFIC, -4) = ?"
            cursor.execute(query, (cidade, str(ano)))
        elif tabela == "feminicidio":
            normalizar_cidade(cidade)
            query = f"SELECT COUNT(*) FROM {tabela} WHERE municipio_fato = ? AND ano = ?"
            cursor.execute(query, (normalizar_cidade(cidade), str(ano)))
        elif tabela == "violenciaPc":
            normalizar_cidade(cidade)
            query = f"SELECT COUNT(*) FROM {tabela} WHERE municipio_fato = ? AND ano = ?"
            cursor.execute(query, (normalizar_cidade(cidade), str(ano)))
        else:
            return 0

        resultado = cursor.fetchone()
        return resultado[0] if resultado else 0

    dados = {
        "Crimes Violentos": buscar_casos("crimesViolentos"),
        "Violência SES": buscar_casos("violenciaSES"),
        "Violência PC": buscar_casos("violenciaPc"),
        "Feminicídio": buscar_casos("feminicidio")
    }

    conn.close()
    return dados

def normalizar_cidade(nome):
    """
    Remove acentos e transforma em letras maiúsculas.
    Ex: 'São João del-Rei' -> 'SAO JOAO DEL-REI'
    """
    if not isinstance(nome, str):
        return ""
    nome = unicodedata.normalize('NFKD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))
    return nome.upper()

# ---------- MAPA ----------
latitude_mg = -18.5122
longitude_mg = -44.5550

m = folium.Map(
    location=[latitude_mg, longitude_mg],
    zoom_start=6,
    min_zoom=6,
    max_zoom=10,
    tiles="cartodbdark_matter",
    max_bounds=True
)

# Adiciona o polígono de Minas Gerais
folium.GeoJson(
    geojson_mg,
    name="Minas Gerais",
    style_function=lambda feature: {
        "fillColor": "blue",
        "color": "white",
        "weight": 1,
        "fillOpacity": 0.5,
    }
).add_to(m)

MousePosition().add_to(m)

# ---------- EXIBIÇÃO DO MAPA ----------
map_data = st_folium(m, width=700, height=500)

# ---------- INTERAÇÃO DO USUÁRIO ----------
cidade = None
if map_data and map_data["last_clicked"]:
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]
    cidade = get_city_name(lat, lon)

    if cidade in cidades_mg:
        st.success(f"📍 Cidade Selecionada: {cidade}")

        # Seleção do ano
        ano = st.selectbox("Selecione o ano:", list(range(2010, 2025)))

        # Consulta ao banco
        if ano:
            st.subheader(f"📊 Dados de {cidade} para o ano {ano}")

            dados = consultar_dados(cidade, ano)

            col1, col2 = st.columns(2)
            col1.metric("Base de dados de Crimes Violentos (Polícia Civil)", dados["Crimes Violentos"])
            col1.metric("Base de dados de Violência contra Mulher (SES)", dados["Violência SES"])
            col2.metric("Base de dados de Violência (Polícia Civil)", dados["Violência PC"])
            col2.metric("Base de dados de Feminicídio (Polícia Civil)", dados["Feminicídio"])
    else:
        st.error("❌ Por favor, selecione uma cidade dentro de Minas Gerais.")
