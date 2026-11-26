import streamlit as st
import folium
import json
import sqlite3
import unicodedata
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from folium.plugins import MousePosition
from gerarGraficos import (
    gerar_grafico_anual_tabela,
    gerar_grafico_geral_anual,
    gerar_grafico_geral_mensal,
    gerar_grafico_mensal_tabela,
    gerar_grafico_relacao_escolaridade_violencia,
    gerar_grafico_demografico_ses,
    gerar_grafico_tipos_violencia_ses,
    gerar_grafico_natureza_crime_pc,
)


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
            where = "1=1"
            parametros = []
            if ano is not None:
                where += f" AND CAST({ano_expr} AS INTEGER) = ?"
                parametros.append(ano)
        else:
            where = "1=1"
            parametros = []
            if ano is not None:
                where += " AND CAST(ano AS INTEGER) = ?"
                parametros.append(ano)

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
        return valor if valor > 0 else ("Sem registros no período" if ano is None else "Sem registros neste ano")

    dados = {
        "Violência SES": buscar_casos("violenciaSES"),
        "Violência PC": buscar_casos("violenciaPc"),
        "Feminicídio": buscar_casos("feminicidio")
    }

    conn.close()
    return dados


@st.cache_data
def consultar_anos_disponiveis():
    with sqlite3.connect("database.db") as conn:
        consulta = """
            SELECT CAST(ano AS INTEGER) AS ano FROM violenciaPc
            UNION SELECT CAST(ano AS INTEGER) FROM feminicidio
            UNION SELECT CAST(CASE
                WHEN substr(trim(DT_NOTIFIC), 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                    THEN substr(trim(DT_NOTIFIC), 1, 4)
                ELSE substr(trim(DT_NOTIFIC), -4)
            END AS INTEGER) FROM violenciaSES
        """
        return [
            row[0] for row in conn.execute(
                f"SELECT DISTINCT ano FROM ({consulta}) WHERE ano BETWEEN 1900 AND 2100 ORDER BY ano DESC"
            )
        ]


@st.cache_data
def consultar_dimensao_mapa():
    with sqlite3.connect("database.db") as conn:
        return conn.execute(
            "SELECT codigo_ibge, municipio_nome, classificacao "
            "FROM dimensao_municipio"
        ).fetchall()


def consultar_indicadores_ibge(filtro, ano):
    conn = sqlite3.connect("database.db")
    parametros = []
    condicao = "1=1"
    regioes = {"Interior de MG", "RMBH", "Belo Horizonte"}
    if filtro in regioes:
        condicao = "classificacao = ?"
        parametros.append(filtro)
    elif filtro:
        condicao = (
            "REPLACE(REPLACE(municipio_nome, '-', ''), ' ', '') = "
            "REPLACE(REPLACE(?, '-', ''), ' ', '')"
        )
        parametros.append(normalizar_cidade(filtro))

    codigos = [
        row[0] for row in conn.execute(
            f"SELECT municipio_cod FROM dimensao_municipio WHERE {condicao}",
            parametros,
        )
    ]
    if not codigos:
        conn.close()
        return {}

    marcadores = ",".join("?" for _ in codigos)
    populacao_estimada, pib_mil = conn.execute(
        f"SELECT SUM(populacao_estimada), SUM(pib_mil_reais) "
        f"FROM indicadores_ibge_anual WHERE ano = ? AND municipio_cod IN ({marcadores})",
        [ano, *codigos],
    ).fetchone()
    censo = (None, None, None, None, None)
    if ano == 2022:
        censo = conn.execute(
            f"SELECT SUM(populacao_censo), SUM(area_km2), SUM(populacao_18mais), "
            f"SUM(populacao_18mais_superior), SUM(populacao_18mais_baixa_escolaridade) "
            f"FROM indicadores_ibge_censo2022 WHERE municipio_cod IN ({marcadores})",
            codigos,
        ).fetchone()
    conn.close()

    populacao_censo, area_km2, adultos, adultos_superior, adultos_escolaridade_baixa = censo
    densidade = populacao_censo / area_km2 if populacao_censo and area_km2 else None
    percentual_superior = (
        100 * adultos_superior / adultos if adultos and adultos_superior is not None else None
    )
    percentual_escolaridade_baixa = (
        100 * adultos_escolaridade_baixa / adultos
        if adultos and adultos_escolaridade_baixa is not None else None
    )
    populacao_ano = populacao_censo if ano == 2022 else populacao_estimada
    pib_per_capita = pib_mil * 1000 / populacao_ano if pib_mil and populacao_ano else None
    return {
        "ano": ano,
        "populacao": populacao_ano,
        "populacao_censo": populacao_censo,
        "area_km2": area_km2,
        "densidade": densidade,
        "pib_mil_reais": pib_mil,
        "pib_per_capita": pib_per_capita,
        "percentual_superior": percentual_superior,
        "percentual_escolaridade_baixa": percentual_escolaridade_baixa,
    }


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
    periodo = "todo o histórico disponível" if ano is None else f"ano de {ano}"

    st.markdown(f"""
        <div style="background-color:#f0f8ff;padding:20px;border-radius:10px;margin-bottom:20px">
            <h2 style="color:#004080;margin-bottom:5px;">{nome_exibicao}</h2>
            <small style="color:gray;">Dados de {periodo}</small>
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

# ---------- MAPA ----------
m = folium.Map(
    location=[-18.5122, -44.5550],
    zoom_start=6,
    tiles="cartodbdark_matter"
)

# Relaciona os polígonos do GeoJSON com a dimensão territorial pelo código IBGE.
municipios_mapa = consultar_dimensao_mapa()

classificacao_por_codigo = {
    str(codigo).zfill(7): classificacao
    for codigo, _, classificacao in municipios_mapa
    if codigo
}
codigo_por_nome = {
    normalizar_cidade(nome): str(codigo).zfill(7)
    for codigo, nome, _ in municipios_mapa
    if codigo and nome
}
codigo_cidade_selecionada = codigo_por_nome.get(normalizar_cidade(cidade)) if cidade else None
if cidade and not codigo_cidade_selecionada:
    st.warning("Não foi possível relacionar a cidade selecionada ao código municipal do mapa.")
cores_regiao = {
    "Interior de MG": "#f4a261",
    "RMBH": "#9b5de5",
    "Belo Horizonte": "#e63946",
}

def estilo_municipio(feature):
    propriedades = feature.get("properties", {})
    codigo = str(propriedades.get("id", "")).zfill(7)
    classificacao = classificacao_por_codigo.get(codigo)

    if codigo_cidade_selecionada and codigo == codigo_cidade_selecionada:
        return {"fillColor": "#e63946", "color": "#ffd166", "weight": 2.5, "fillOpacity": 0.75}
    if area in cores_regiao and classificacao == area:
        return {"fillColor": cores_regiao[area], "color": "#ffffff", "weight": 1.4, "fillOpacity": 0.68}
    return {"fillColor": "#1f6feb", "color": "#cbd5e1", "weight": 0.55, "fillOpacity": 0.16}

folium.GeoJson(
    geojson_mg,
    name="Municípios de Minas Gerais",
    style_function=estilo_municipio,
    highlight_function=lambda feature: {"weight": 2, "color": "#ffffff", "fillOpacity": 0.82},
    tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Município:"]),
).add_to(m)

if area in cores_regiao:
    municipios_destacados = [
        feature for feature in geojson_mg["features"]
        if classificacao_por_codigo.get(
            str(feature.get("properties", {}).get("id", "")).zfill(7)
        ) == area
    ]
    descricao_destaque = f"{len(municipios_destacados)} municípios de {area} destacados no mapa."
elif codigo_cidade_selecionada:
    municipios_destacados = [
        feature for feature in geojson_mg["features"]
        if str(feature.get("properties", {}).get("id", "")).zfill(7) == codigo_cidade_selecionada
    ]
    descricao_destaque = f"{cidade} destacada no mapa."
else:
    municipios_destacados = []
    descricao_destaque = None

# Aproxima o enquadramento à RMBH ou ao município selecionado.
if municipios_destacados and area != "Interior de MG":
    coordenadas = []

    def coletar_coordenadas(valor):
        if isinstance(valor, (list, tuple)):
            if len(valor) >= 2 and all(isinstance(item, (int, float)) for item in valor[:2]):
                coordenadas.append((valor[1], valor[0]))
            else:
                for item in valor:
                    coletar_coordenadas(item)

    for feature in municipios_destacados:
        coletar_coordenadas(feature.get("geometry", {}).get("coordinates", []))
    if coordenadas:
        m.fit_bounds(
            [
                [min(lat for lat, _ in coordenadas), min(lon for _, lon in coordenadas)],
                [max(lat for lat, _ in coordenadas), max(lon for _, lon in coordenadas)],
            ],
            padding=(18, 18),
        )

# Sempre mostra seleção e mapa, mesmo que nenhuma cidade seja escolhida
anos_disponiveis = consultar_anos_disponiveis()
opcoes_periodo = ["Todo o histórico", *anos_disponiveis]
periodo_selecionado = st.selectbox("Período de análise:", opcoes_periodo)
ano = None if periodo_selecionado == "Todo o histórico" else int(periodo_selecionado)

with st.container():
    dados = consultar_dados(filtro, ano)

    col_mapa, col_dados = st.columns([0.5, 0.5])

    with col_mapa:
        if descricao_destaque:
            st.caption(descricao_destaque)
        st_folium(m, width=450, height=500)

    with col_dados:
        mostrar_dados_resumo(filtro, ano, dados)
        if not filtro:
            st.info("Exibindo os dados gerais do estado de Minas Gerais.")

    indicadores = consultar_indicadores_ibge(filtro, ano) if ano is not None else {}
    if ano is None:
        st.info("O perfil do IBGE exige um ano de referência. Selecione um ano para consultar esses indicadores.")
    if indicadores:
        def formatar_numero(valor, casas=0):
            if valor is None:
                return None
            return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")

        cartoes = []
        if indicadores["populacao"] is not None:
            fonte_populacao = "Censo" if ano == 2022 else "estimada"
            cartoes.append((f"População {fonte_populacao} ({ano})", formatar_numero(indicadores["populacao"])))
        if indicadores["area_km2"] is not None:
            cartoes.append((f"Área territorial ({ano})", f"{formatar_numero(indicadores['area_km2'], 2)} km²"))
        if indicadores["densidade"] is not None:
            cartoes.append((f"Densidade demográfica ({ano})", f"{formatar_numero(indicadores['densidade'], 2)} hab./km²"))
        if indicadores["pib_mil_reais"] is not None:
            pib_bilhoes = indicadores["pib_mil_reais"] / 1_000_000
            cartoes.append((f"PIB total ({ano})", f"R$ {formatar_numero(pib_bilhoes, 2)} bi"))
        if indicadores["pib_per_capita"] is not None:
            cartoes.append((f"PIB per capita ({ano})", f"R$ {formatar_numero(indicadores['pib_per_capita'], 2)}"))
        if indicadores["percentual_superior"] is not None:
            cartoes.append((f"Adultos com superior completo ({ano})", f"{formatar_numero(indicadores['percentual_superior'], 2)}%"))
        if indicadores["percentual_escolaridade_baixa"] is not None:
            cartoes.append((f"Adultos sem instrução/fundamental incompleto ({ano})", f"{formatar_numero(indicadores['percentual_escolaridade_baixa'], 2)}%"))

        st.markdown("---")
        st.subheader(f"Perfil demográfico, econômico e educacional ({ano})")
        st.caption(
            f"Fontes: IBGE/SIDRA. Indicadores exibidos somente quando disponíveis para {ano}. "
            "O PIB per capita é calculado com o PIB e a população do mesmo ano."
        )
        if cartoes:
            for inicio in range(0, len(cartoes), 4):
                linha = st.columns(min(4, len(cartoes) - inicio))
                for coluna, (rotulo, valor) in zip(linha, cartoes[inicio:inicio + 4]):
                    coluna.metric(rotulo, valor)
        else:
            st.info(f"Não há indicadores do IBGE disponíveis para {ano} nesta seleção.")

        if ano == 2022:
            st.markdown("### Relação exploratória entre escolaridade e violência (2022)")
            gerar_grafico_relacao_escolaridade_violencia(filtro)

    tabs = st.tabs(["Detalhamento SES", "Natureza dos crimes — PC", "Evolução temporal"])
    with tabs[0]:
        dimensao_grafico = st.selectbox(
            "Distribuir notificações SES por:",
            ["Orientação sexual", "Identidade de gênero", "Raça/cor"],
            key="ses_dimensao_grafico",
        )
        gerar_grafico_demografico_ses(filtro, ano, dimensao_grafico)
        gerar_grafico_tipos_violencia_ses(filtro, ano)

    with tabs[1]:
        st.caption("Natureza do delito e total de vítimas registrados pela Polícia Civil.")
        gerar_grafico_natureza_crime_pc(filtro, ano)

    with tabs[2]:
        if ano is None:
            st.markdown("#### Casos ao longo dos anos")
            st.markdown("**Violência SES**")
            gerar_grafico_anual_tabela("violenciaSES", filtro)
            st.markdown("**Violência PC**")
            gerar_grafico_anual_tabela("violenciaPc", filtro)
            st.markdown("**Feminicídio**")
            gerar_grafico_anual_tabela("feminicidio", filtro)
            st.markdown("**Total das fontes ao longo dos anos**")
            gerar_grafico_geral_anual(filtro)

            st.markdown("#### Distribuição mensal em todo o histórico")
            gerar_grafico_mensal_tabela("violenciaSES", filtro)
            gerar_grafico_mensal_tabela("violenciaPc", filtro)
            gerar_grafico_mensal_tabela("feminicidio", filtro)
            gerar_grafico_geral_mensal(filtro)
        else:
            st.markdown(f"#### Distribuição mensal de {ano}")
            gerar_grafico_mensal_tabela("violenciaSES", filtro, ano=ano)
            gerar_grafico_mensal_tabela("violenciaPc", filtro, ano=ano)
            gerar_grafico_mensal_tabela("feminicidio", filtro, ano=ano)
            gerar_grafico_geral_mensal(filtro, ano=ano)





