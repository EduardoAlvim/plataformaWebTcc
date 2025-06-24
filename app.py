import streamlit as st
import folium
import json
import sqlite3
import unicodedata
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from folium.plugins import MousePosition
from gerarGraficos import gerar_grafico_anual_tabela, gerar_grafico_geral_anual, gerar_grafico_geral_mensal, gerar_grafico_mensal_tabela


# ---------- CONFIGURAÇÕES INICIAIS ----------
st.set_page_config(page_title="Mapa de Minas Gerais", layout="wide")
st.title("Casos de Violência contra Mulher em Minas Gerais")
st.write("Escolha uma cidade de Minas Gerais para ver os dados.")

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
        if tabela == "violenciaSES":
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
        valor = resultado[0] if resultado else 0
        if valor is not None and valor > 0:
            return valor
        else:
            return "Sem registros neste ano"

    dados = {
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

def mostrar_dados(cidade):
    if cidade in cidades_mg:
        st.success(f"📍 Cidade Selecionada: {cidade}")

        # Seleção do ano
        ano = st.selectbox("Selecione o ano:", list(range(2010, 2025)))

        # Consulta ao banco
        if ano:
            st.subheader(f"📊 Dados de {cidade} para o ano {ano}")

            dados = consultar_dados(cidade, ano)

            col1, col2 = st.columns(2)
            col1.metric("Base de dados de Violência contra Mulher (SES)", dados["Violência SES"])
            col2.metric("Base de dados de Violência contra Mulher (Polícia Civil)", dados["Violência PC"])
            col2.metric("Base de dados de Feminicídio (Polícia Civil)", dados["Feminicídio"])

            st.markdown("---")
            st.subheader("📈 Evolução dos Casos ao Longo dos Anos")

            # Gerar gráficos individuais por base

            st.markdown("#### Violência SES")
            gerar_grafico_anual_tabela("violenciaSES", cidade)
            gerar_grafico_mensal_tabela("violenciaSES", cidade)

            st.markdown("#### Violência PC")
            gerar_grafico_anual_tabela("violenciaPc", cidade)
            gerar_grafico_mensal_tabela("violenciaPc", cidade)

            st.markdown("#### Feminicídio")
            gerar_grafico_anual_tabela("feminicidio", cidade)
            gerar_grafico_mensal_tabela("feminicidio", cidade)

            # Gráfico geral somando todas as bases
            st.markdown("#### Panorama Geral (Todos os Tipos)")
            gerar_grafico_geral_anual(cidade)
            gerar_grafico_geral_mensal(cidade)

    else:
        st.error("❌ Por favor, selecione uma cidade dentro de Minas Gerais.")

# ---------- INTERAÇÃO DO USUÁRIO ----------

cidade = st.selectbox(
    "Digite ou selecione a cidade:",
    options=[""] + sorted(cidades_mg),
    index=0,
    placeholder="Ex: Belo Horizonte"
)

def buscar_poligono_cidade(nome_cidade):
    for feature in geojson_mg["features"]:
        props = feature.get("properties", {})
        nome = props.get("name", "")
        if normalizar_cidade(nome) == normalizar_cidade(nome_cidade):
            return feature
    return None

# ---------- MAPA ----------
m = folium.Map(
    location=[-18.5122, -44.5550],
    zoom_start=6,
    tiles="cartodbdark_matter"
)

# Adiciona todos os municípios de MG (região demarcada em azul)
folium.GeoJson(
    geojson_mg,
    name="Minas Gerais",
    style_function=lambda feature: {
        "fillColor": "blue",
        "color": "white",
        "weight": 1,
        "fillOpacity": 0.2
    }
).add_to(m)

# Adiciona o polígono da cidade selecionada (destacada em vermelho)
if cidade:
    poligono = buscar_poligono_cidade(cidade)
    if poligono:
        folium.GeoJson(
            poligono,
            name=cidade,
            style_function=lambda feature: {
                "fillColor": "red",
                "color": "yellow",
                "weight": 3,
                "fillOpacity": 0.4
            },
            tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Cidade:"])
        ).add_to(m)
    else:
        st.warning("⚠️ Cidade não encontrada no arquivo GeoJSON.")

# Exibe o mapa no app
st_folium(m, width=700, height=500)

# Mostra os dados se uma cidade válida foi selecionada
if cidade:
    mostrar_dados(cidade)


