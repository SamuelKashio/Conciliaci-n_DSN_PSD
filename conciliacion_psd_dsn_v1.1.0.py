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
                nro_operacion = linea[124:130].strip()

                registros.append({
                    'PSP_TIN': psp_tin,
                    'Monto total pagado': monto,
                    'Medio de atención': medio_atencion,
                    'Fecha de pago': fecha_pago,
                    'Hora de atención': hora_pago,
                    'Nº operación': nro_operacion,
                    'FechaHora': datetime.strptime(f"{anio}-{mes}-{dia} {hora}:{minuto}:{segundo}", "%Y-%m-%d %H:%M:%S")
                })
            except:
                continue
    df = pd.DataFrame(registros)
    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    return df.drop_duplicates(subset='PSP_TIN')

@st.cache_data
def cargar_excel_bcp(archivo):
    df = pd.read_excel(archivo)
    columnas = df.columns.str.lower()

    if 'operación - hora' in columnas:
        df = pd.read_excel(archivo, header=4)  # movimientos históricos
        df['PSP_TIN'] = df['Descripción operación'].astype(str).str.extract(r'(2\d{11})(?!\d)', expand=False)
        df['Nº operación'] = df['Operación - Número'].astype(str).str.strip()
        df['Operación - Hora'] = df['Operación - Hora'].astype(str).str.strip()
        df['FechaHora'] = pd.to_datetime(df['Fecha'].astype(str) + ' ' + df['Operación - Hora'])
    else:
        df = pd.read_excel(archivo, skiprows=7)  # movimientos diarios
        df['Descripción operación'] = df['Descripción operación'].astype(str).str.strip()
        df['Nº operación'] = df['Nº operación'].astype(str).str.strip()
        df['PSP_TIN'] = df['Descripción operación'].str.extract(r'(2\d{11})(?!\d)', expand=False)
        df['FechaHora'] = pd.to_datetime(df['Fecha operación'])

    duplicados = df[df.duplicated(subset=['Nº operación'], keep=False)]
    extornos = duplicados['Descripción operación'].str.contains('Extorno', case=False, na=False)
    numeros_extorno = duplicados[extornos]['Nº operación'].unique()
    df_filtrado = df[~df['Nº operación'].isin(numeros_extorno)]
    df_filtrado = df_filtrado.drop_duplicates(subset='PSP_TIN')
    df_filtrado = df_filtrado[df_filtrado['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]

    return df_filtrado[['PSP_TIN', 'FechaHora']]

@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)

# --------------------------
# INTERFAZ
# --------------------------
st.title("Conciliación de Pagos - Kashio")
st.markdown("""
Detecta:
- **DSN** (Depósitos sin notificación)
- **PSD** (Pagos sin depósito)

Compatible con EECC del banco en `.txt`, `movimientos diarios (.xlsx)` y `movimientos históricos (.xlsx)`
""")
st.divider()

archivo_banco = st.file_uploader("📥 Subir archivo del banco (.txt o .xlsx)", type=["txt", "xlsx", "xls"])
archivo_metabase = st.file_uploader("📥 Subir archivo de Metabase (.xlsx)", type=["xlsx", "xls"])

# PROCESAMIENTO BANCO
df_banco = None
hora_corte = None
if archivo_banco is not None:
    start = time.time()
    try:
        if archivo_banco.name.endswith('.txt'):
            st.caption("Formato detectado: CREP (.txt)")
            df_banco = cargar_txt_crep(archivo_banco)
        else:
            st.caption("Formato detectado: EECC BCP (.xlsx)")
            df_banco = cargar_excel_bcp(archivo_banco)

        hora_corte = df_banco['FechaHora'].max()
        st.success(f"✅ EECC del banco cargado con {len(df_banco)} operaciones únicas en {round(time.time() - start, 2)} s")
        st.info(f"⏱ Hora de corte detectada: {hora_corte}")
    except Exception as e:
        st.error(f"❌ Error al procesar el archivo del banco: {e}")
        st.stop()

# PROCESAMIENTO METABASE
if archivo_banco and archivo_metabase:
    start = time.time()
    df_meta = cargar_metabase(archivo_metabase)
    st.caption(f"✅ Metabase cargado en {round(time.time() - start, 2)} segundos")

    columnas = df_meta.columns.str.lower()
    if 'deuda_psptin' in columnas and 'banco' in columnas and 'moneda' in columnas and 'pc_create_date_gmt_peru' in columnas:
        col_psptin = df_meta.columns[columnas.get_loc('deuda_psptin')]
        col_banco = df_meta.columns[columnas.get_loc('banco')]
        col_moneda = df_meta.columns[columnas.get_loc('moneda')]
        col_fecha = df_meta.columns[columnas.get_loc('pc_create_date_gmt_peru')]
    else:
        col_psptin = df_meta.columns[26]
        col_banco = df_meta.columns[10]
        col_moneda = df_meta.columns[21]
        col_fecha = df_meta.columns[15]

    df_meta[col_psptin] = df_meta[col_psptin].astype(str)
    df_meta = df_meta.drop_duplicates(subset=col_psptin)
    df_meta[col_fecha] = pd.to_datetime(df_meta[col_fecha], errors='coerce')

    df_meta_bcp_pen = df_meta[
        (df_meta[col_banco].astype(str).str.upper() == "BCP") &
        (df_meta[col_moneda].astype(str).str.upper() == "PEN") &
        (df_meta[col_fecha] <= hora_corte)
    ]
    st.info(f"🔍 {len(df_meta_bcp_pen)} registros de Metabase (BCP - PEN) únicos hasta la hora de corte")

    dsn = df_banco[~df_banco['PSP_TIN'].isin(df_meta_bcp_pen[col_psptin])]
    st.subheader("🟡 DSN encontrados")
    st.write(f"{len(dsn)} DSN detectados")
    st.dataframe(dsn)
    output_dsn = io.BytesIO()
    with pd.ExcelWriter(output_dsn, engine='openpyxl') as writer:
        dsn.to_excel(writer, index=False)
    st.download_button("⬇️ Descargar DSN", data=output_dsn.getvalue(),
                       file_name="DSN_encontrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    psd = df_meta_bcp_pen[~df_meta_bcp_pen[col_psptin].isin(df_banco['PSP_TIN'])]
    st.subheader("🔁 PSD encontrados")
    st.write(f"{len(psd)} PSD detectados")
    st.dataframe(psd)
    output_psd = io.BytesIO()
    with pd.ExcelWriter(output_psd, engine='openpyxl') as writer:
        psd.to_excel(writer, index=False)
    st.download_button("⬇️ Descargar PSD", data=output_psd.getvalue(),
                       file_name="PSD_encontrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
