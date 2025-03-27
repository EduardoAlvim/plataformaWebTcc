import streamlit as st
import folium
import json
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from folium.plugins import MousePosition

# Configuração da página
st.set_page_config(page_title="Mapa Interativo de Minas Gerais", layout="wide")

# Título do site
st.title("Casos de Violência contra Mulher em Minas Gerais")

st.write("Clique em um ponto do mapa para visualizar a cidade correspondente.")

# Definir limites do estado de Minas Gerais (coordenadas aproximadas)
bounds = [[-23.5, -51.5], [-14.0, -39.5]]  # [Sudoeste, Nordeste]

# Criar um mapa centrado em Minas Gerais com limites de navegação
latitude_mg = -18.5122
longitude_mg = -44.5550
zoom_mg = 6

m = folium.Map(
    location=[latitude_mg, longitude_mg], 
    zoom_start=zoom_mg, 
    min_zoom=6, 
    max_zoom=10,
    max_bounds=True  # Impede que o usuário mova o mapa para fora dos limites
)

# Carregar o arquivo GeoJSON com a fronteira de MG
with open("br_mg.json", "r", encoding="utf-8") as f:
    geojson_mg = json.load(f)

# Adicionar a camada com a fronteira de Minas Gerais
folium.GeoJson(
    geojson_mg,
    name="Minas Gerais",
    style_function=lambda feature: {
        "fillColor": "blue",
        "color": "black",
        "weight": 2,
        "fillOpacity": 0.2,
    }
).add_to(m)

# Adicionar plugin para exibir coordenadas ao passar o mouse
MousePosition().add_to(m)

# Capturar o clique do usuário
map_data = st_folium(m, width=700, height=500)

# Função para obter o nome da cidade a partir da latitude e longitude
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

# Verificar se o usuário clicou no mapa
if map_data and map_data["last_clicked"]:
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]
    city_name = get_city_name(lat, lon)

    # Exibir o nome da cidade
    st.subheader(f"📍 Cidade Selecionada: {city_name}")
