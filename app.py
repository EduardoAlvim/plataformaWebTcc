import streamlit as st
import folium
import json
import sqlite3
import unicodedata
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from folium.plugins import MousePosition
from gerarGraficos import gerar_grafico_anual_tabela, gerar_grafico_geral_anual, gerar_grafico_geral_mensal, gerar_grafico_mensal_tabela, gerar_grafico_anual_tabela_mg, gerar_grafico_geral_anual_mg, gerar_grafico_geral_mensal_mg, gerar_grafico_mensal_tabela_mg


# ---------- CONFIGURAÇÕES INICIAIS ----------
st.set_page_config(page_title="Mapa de Minas Gerais", layout="wide")
st.title("Casos de Violência contra Mulher em Minas Gerais")
st.write("Escolha Minas Gerais, uma região ou uma cidade para ver os dados.")

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

def consultar_dados(filtro, ano):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    def buscar_casos(tabela):
        if tabela == "violenciaSES":
            ano_expr = "CASE WHEN substr(trim(DT_NOTIFIC),1,4) GLOB '[0-9][0-9][0-9][0-9]' THEN substr(trim(DT_NOTIFIC),1,4) ELSE substr(trim(DT_NOTIFIC),-4) END"
            where = f"CAST({ano_expr} AS INTEGER) = ?"
            parametros = [ano]
        else:
            where = "CAST(ano AS INTEGER) = ?"
            parametros = [ano]

        if filtro in {"Interior de MG", "RMBH", "Belo Horizonte"}:
            if tabela == "violenciaSES":
                where += " AND ID_MN_RESI IN (SELECT municipio_ses FROM dimensao_municipio WHERE classificacao = ? AND municipio_ses IS NOT NULL)"
            else:
                where += " AND municipio_cod IN (SELECT municipio_cod FROM dimensao_municipio WHERE classificacao = ?)"
            parametros.append(filtro)
        elif filtro:
            if tabela == "violenciaSES":
                where += " AND ID_MN_RESI = ?"
                parametros.append(filtro)
            else:
                where += " AND municipio_cod IN (SELECT municipio_cod FROM dimensao_municipio WHERE REPLACE(REPLACE(municipio_nome, '-', ''), ' ', '') = REPLACE(REPLACE(?, '-', ''), ' ', ''))"
                parametros.append(normalizar_cidade(filtro))

        cursor.execute(f"SELECT COUNT(*) FROM {tabela} WHERE {where}", parametros)

        resultado = cursor.fetchone()
        valor = resultado[0] if resultado else 0
        return valor if valor > 0 else "Sem registros neste ano"

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

def mostrar_dados_resumo(cidade, ano, dados):
    nome_exibicao = "Minas Gerais" if not cidade.strip() else cidade

    st.markdown(f"""
        <div style="background-color:#f0f8ff;padding:20px;border-radius:10px;margin-bottom:20px">
            <h2 style="color:#004080;margin-bottom:5px;">{nome_exibicao}</h2>
            <small style="color:gray;">Dados do ano de {ano}</small>
        </div>
    """, unsafe_allow_html=True)

    # Indicadores principais
    st.markdown("### 🔹 Indicadores principais")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("👩‍⚕️ Violência SES", dados["Violência SES"])
    with col2:
        st.metric("🚔 Violência PC", dados["Violência PC"])
    with col3:
        st.metric("🟥 Feminicídio", dados["Feminicídio"])




# ---------- INTERAÇÃO DO USUÁRIO ----------

area = st.selectbox(
    "Filtrar por:",
    ["Minas Gerais", "Interior de MG", "RMBH", "Belo Horizonte", "Cidade específica"],
)
cidade = ""
if area == "Cidade específica":
    cidade = st.selectbox(
        "Digite ou selecione a cidade:",
        options=sorted(cidades_mg),
        index=None,
        placeholder="Ex: Belo Horizonte",
    )
filtro = cidade if area == "Cidade específica" and cidade else ("" if area == "Minas Gerais" else area)
if area == "Cidade específica" and not cidade:
    st.info("Selecione uma cidade para continuar.")
    st.stop()

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

# Sempre mostra seleção e mapa, mesmo que nenhuma cidade seja escolhida
ano = st.selectbox("Selecione o ano:", list(range(2010, 2027)))

if ano is not None:
    dados = consultar_dados(filtro, ano)

    col_mapa, col_dados = st.columns([0.5, 0.5])

    with col_mapa:
        st_folium(m, width=450, height=500)

    with col_dados:
        mostrar_dados_resumo(filtro, ano, dados)
        if not filtro:
            st.info("Exibindo os dados gerais do estado de Minas Gerais.")

    st.markdown("---")
    st.markdown("### 📊 Evolução dos Casos por Tipo")
    st.markdown("#### 🔵 Violência SES")
    gerar_grafico_anual_tabela("violenciaSES", filtro)
    gerar_grafico_mensal_tabela("violenciaSES", filtro)
    st.markdown("#### 🟠 Violência PC")
    gerar_grafico_anual_tabela("violenciaPc", filtro)
    gerar_grafico_mensal_tabela("violenciaPc", filtro)
    st.markdown("#### 🔴 Feminicídio")
    gerar_grafico_anual_tabela("feminicidio", filtro)
    gerar_grafico_mensal_tabela("feminicidio", filtro)
    st.markdown("---")
    st.markdown("### 📈 Panorama Geral de Casos (Todas as Fontes)")
    gerar_grafico_geral_anual(filtro)
    gerar_grafico_geral_mensal(filtro)





