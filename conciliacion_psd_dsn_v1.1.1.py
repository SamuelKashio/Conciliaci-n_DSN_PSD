import streamlit as st
import pandas as pd
import io
import time
from datetime import datetime

# --------------------------
# CARGA ARCHIVOS
# --------------------------
@st.cache_data
def cargar_txt_crep(archivo_txt):
    lineas = archivo_txt.read().decode('utf-8').splitlines()
    registros = []
    for linea in lineas:
        if linea.startswith('DD'):
            try:
                psp_tin = linea[205:217].strip().lstrip("0")
                monto_raw = linea[73:88].strip()
                monto = int(monto_raw) / 100 if monto_raw.isdigit() else None
                medio_atencion = linea[156:168].strip()
                anio = linea[57:61]
                mes = linea[61:63]
                dia = linea[63:65]
                fecha_pago = f"{dia}/{mes}/{anio}"
                hora = linea[168:170]
                minuto = linea[170:172]
                segundo = linea[172:174]
                hora_pago = f"{hora}:{minuto}:{segundo}"
                fecha_hora_pago = datetime.strptime(f"{dia}/{mes}/{anio} {hora}:{minuto}:{segundo}", "%d/%m/%Y %H:%M:%S")
                nro_operacion = linea[124:130].strip()
                registros.append({
                    'PSP_TIN': psp_tin,
                    'Monto total pagado': monto,
                    'Medio de atención': medio_atencion,
                    'Fecha de pago': fecha_pago,
                    'Hora de atención': hora_pago,
                    'FechaHora': fecha_hora_pago,
                    'Nº operación': nro_operacion
                })
            except:
                continue
    df = pd.DataFrame(registros)
    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    return df.drop_duplicates(subset='PSP_TIN')

@st.cache_data
def cargar_excel_banco(archivo):
    try:
        df = pd.read_excel(archivo, skiprows=0)
        columnas = df.columns.str.lower()

        # Interbank
        if 'descripción' in columnas and 'número operación' in columnas and 'fecha' in columnas and 'importe' in columnas:
            st.caption("Formato detectado: INTERBANK (.xlsx)")
            df['PSP_TIN'] = df['Descripción'].astype(str).str.extract(r'(2\d{11})(?!\d)', expand=False)
            df['Nº operación'] = df['Número Operación'].astype(str).str.strip()
            df['FechaHora'] = pd.to_datetime(df['Fecha'], errors='coerce')

        # BCP - históricos
        elif 'descripción' in columnas and 'número de operación' in columnas and 'fecha' in columnas and 'operación - hora' in columnas:
            st.caption("Formato detectado: BCP Históricos (.xlsx)")
            df['PSP_TIN'] = df['Descripción'].astype(str).str.extract(r'(2\d{11})(?!\d)', expand=False)
            df['Nº operación'] = df['Número de Operación'].astype(str).str.strip()
            df['FechaHora'] = pd.to_datetime(df['Fecha'].astype(str) + ' ' + df['Operación - Hora'].astype(str), errors='coerce')

        # BCP - diarios
        elif 'descripción operación' in columnas and 'nº operación' in columnas and 'fecha operación' in columnas and 'hora' in columnas:
            st.caption("Formato detectado: BCP Diario (.xlsx)")
            df = pd.read_excel(archivo, skiprows=7)
            df['PSP_TIN'] = df['Descripción operación'].astype(str).str.extract(r'(2\d{11})(?!\d)', expand=False)
            df['Nº operación'] = df['Nº operación'].astype(str).str.strip()
            df['FechaHora'] = pd.to_datetime(df['Fecha operación'].astype(str) + ' ' + df['Hora'].astype(str), errors='coerce')

        else:
            raise ValueError("Formato de archivo no reconocido")

        duplicados = df[df.duplicated(subset=['Nº operación'], keep=False)]
        extornos = duplicados[df.columns[df.columns.str.lower().str.contains('descripción')][0]].str.contains('Extorno', case=False, na=False)
        numeros_extorno = duplicados[extornos]['Nº operación'].unique()
        df_filtrado = df[~df['Nº operación'].isin(numeros_extorno)]
        df_filtrado = df_filtrado.drop_duplicates(subset='PSP_TIN')
        df_filtrado = df_filtrado[df_filtrado['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
        return df_filtrado[['PSP_TIN', 'FechaHora']]

    except Exception as e:
        st.error(f"❌ Error al procesar archivo Excel del banco: {e}")
        st.stop()

@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)

# El resto del código (interfaz y lógica DSN/PSD) no cambia.
# Solo se debe reemplazar donde antes llamabas a `cargar_excel_bcp` por `cargar_excel_banco`
# Por ejemplo:

# if archivo_banco.name.endswith('.txt'):
#     df_banco = cargar_txt_crep(archivo_banco)
# else:
#     df_banco = cargar_excel_banco(archivo_banco)
