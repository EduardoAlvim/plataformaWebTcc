import os
import sqlite3
import pandas as pd

pasta_crimesViolentos = os.path.join("bd", "crimesViolentos")
nome_banco = "database.db"

conn = sqlite3.connect(nome_banco)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS crimesViolentos (
        registros TEXT,
        natureza TEXT,
        municipio TEXT,
        cod_municipio TEXT,
        mes TEXT,
        ano TEXT,
        risp TEXT,
        rmbh TEXT
    );
''')
conn.commit()

colunas_esperadas = ['registros', 'natureza', 'municipio', 'cod_municipio', 'mes', 'ano', 'risp', 'rmbh']

def padronizar_colunas(colunas):
    return [
        col.strip().lower()
           .replace('\ufeff', '')
           .replace(" ", "_")
           .replace("á", "a").replace("ã", "a")
           .replace("í", "i").replace("ú", "u")
           .replace("é", "e").replace("ê", "e")
           .replace("ó", "o").replace("ç", "c")
        for col in colunas
    ]

for ano in range(2012, 2025):
    nome_arquivo = f"crimes_violentos_{ano}.csv"
    caminho_arquivo = os.path.join(pasta_crimesViolentos, nome_arquivo)

    if os.path.exists(caminho_arquivo):
        print(f"Importando: {nome_arquivo}")
        try:
            df = pd.read_csv(caminho_arquivo, sep=None, engine='python')
            df.columns = padronizar_colunas(df.columns)
            df = df[colunas_esperadas]
            
            # Filtra apenas linhas onde a natureza contém "estupro"
            df = df[df['natureza'].str.contains('estupro', case=False, na=False)]

            if not df.empty:
                df.to_sql('crimesViolentos', conn, if_exists='append', index=False)
            else:
                print(f"Nenhum registro de 'estupro' encontrado em {nome_arquivo}.")

        except Exception as e:
            print(f"Erro ao importar {nome_arquivo}: {e}")
    else:
        print(f"Arquivo não encontrado: {nome_arquivo}")

conn.close()
print("Importação concluída.")
