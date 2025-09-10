import streamlit as st
import pandas as pd
import io
import time
from datetime import datetime

# === CARGA DE ARCHIVOS ===
@st.cache_data(ttl=600, max_entries=5)
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
                fecha_hora_pago = datetime.strptime(f"{dia}/{mes}/{anio} {hora}:{minuto}:{segundo}", "%d/%m/%Y %H:%M:%S")
                nro_operacion = linea[124:130].strip()
                registros.append({
                    'PSP_TIN': psp_tin,
                    'Monto': monto,
                    'Medio de atención': medio_atencion,
                    'Fecha': fecha_pago,
                    'Hora': f"{hora}:{minuto}:{segundo}",
                    'FechaHora': fecha_hora_pago,
                    'Nº operación': nro_operacion
                })
            except:
                continue
    df = pd.DataFrame(registros)
    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    return df.drop_duplicates(subset='PSP_TIN'), True

@st.cache_data(ttl=600, max_entries=5)
def cargar_excel_bcp(archivo):
    # Optimizar lectura de excel
    df = pd.read_excel(archivo, skiprows=7, dtype={"Nº operación": str})
    df['Descripción operación'] = df['Descripción operación'].astype(str).str.strip()
    df['Nº operación'] = df['Nº operación'].astype(str).str.strip()
    df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce')
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
    df['PSP_TIN'] = df['Descripción operación'].str.extract(r'(2\d{11})(?!\d)', expand=False)

    # Detectar y filtrar extornos
    duplicados = df[df.duplicated(subset=['Nº operación'], keep=False)]
    extornos = duplicados['Descripción operación'].str.contains('Extorno', case=False, na=False)
    numeros_extorno = duplicados[extornos]['Nº operación'].unique()
    df_filtrado = df[~df['Nº operación'].isin(numeros_extorno)]
    df_filtrado = df_filtrado[df_filtrado['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    df_filtrado = df_filtrado.drop_duplicates(subset='PSP_TIN')
    return df_filtrado[['PSP_TIN', 'Monto', 'Fecha', 'Nº operación']], False

# No cacheamos metabase porque puede ser enorme
def cargar_metabase(archivo):
    return pd.read_excel(archivo, dtype=str)

# === INTERFAZ ===
st.title("Conciliación de Pagos - Kashio")
st.markdown("""
Detecta:
- **DSN** (Depósitos sin notificación)
- **PSD** (Pagos sin depósito)

✅ Compatible con archivos .txt y .xlsx  
✅ Compara solo hasta la **hora de corte del banco (CREP)**
""")
st.divider()

archivo_banco = st.file_uploader("📥 Subir archivo del banco (.txt o .xlsx)", type=["txt", "xlsx", "xls"])
archivo_metabase = st.file_uploader("📥 Subir archivo de Metabase (.xlsx)", type=["xlsx", "xls"])

df_banco = None
hora_corte = None
es_crep = False

# === PROCESAR BANCO ===
if archivo_banco is not None:
    start = time.time()
    try:
        if archivo_banco.name.endswith('.txt'):
            st.caption("Formato detectado: CREP (.txt)")
            df_banco, es_crep = cargar_txt_crep(archivo_banco)
            hora_corte = df_banco['FechaHora'].max()
            st.info(f"🕐 Hora de corte detectada: {hora_corte}")
        else:
            st.caption("Formato detectado: EECC BCP (.xlsx)")
            df_banco, es_crep = cargar_excel_bcp(archivo_banco)
        st.success(f"✅ Archivo del banco cargado con {len(df_banco)} operaciones únicas en {round(time.time() - start, 2)} s")
    except Exception as e:
        st.error(f"❌ Error al procesar el archivo del banco: {e}")
        st.stop()

# === PROCESAR METABASE Y CONCILIAR ===
if archivo_banco and archivo_metabase:
    start = time.time()
    df_meta = cargar_metabase(archivo_metabase)
    st.caption(f"✅ Metabase cargado en {round(time.time() - start, 2)} segundos")

    columnas = df_meta.columns.str.lower()
    if 'deuda_psptin' in columnas and 'banco' in columnas and 'moneda' in columnas:
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

    if hora_corte:
        df_meta_bcp_pen = df_meta[
            (df_meta[col_banco].astype(str).str.upper() == "(BCP) - Banco de Crédito del Perú") &
            (df_meta[col_moneda].astype(str).str.upper() == "PEN") &
            (df_meta[col_fecha] <= hora_corte)
        ]
        st.info(f"🔍 {len(df_meta_bcp_pen)} registros filtrados de Metabase (BCP - PEN) hasta la hora de corte")
    else:
        df_meta_bcp_pen = df_meta[
            (df_meta[col_banco].astype(str).str.upper() == "(BCP) - Banco de Crédito del Perú") &
            (df_meta[col_moneda].astype(str).str.upper() == "PEN")
        ]
        st.info(f"🔍 {len(df_meta_bcp_pen)} registros filtrados de Metabase ((BCP) - Banco de Crédito del Perú - PEN)")

    # === DSN ===
    dsn = df_banco[~df_banco['PSP_TIN'].isin(df_meta_bcp_pen[col_psptin])]
    st.subheader("🟡 DSN encontrados")
    st.write(f"{len(dsn)} DSN detectados")
    if not es_crep:
        dsn['Fecha'] = pd.to_datetime(dsn['Fecha'], errors='coerce').dt.strftime('%d/%m/%Y')
    st.dataframe(dsn.head(100))  # mostrar solo primeras 100 filas
    output_dsn = io.BytesIO()
    with pd.ExcelWriter(output_dsn, engine='openpyxl') as writer:
        dsn.to_excel(writer, index=False)
    st.download_button("⬇️ Descargar DSN", data=output_dsn.getvalue(),
                       file_name="DSN_encontrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # === PSD ===
    psd = df_meta_bcp_pen[~df_meta_bcp_pen[col_psptin].isin(df_banco['PSP_TIN'])]
    st.subheader("🔁 PSD encontrados")
    st.write(f"{len(psd)} PSD detectados")
    st.dataframe(psd.head(100))  # mostrar solo primeras 100 filas
    output_psd = io.BytesIO()
    with pd.ExcelWriter(output_psd, engine='openpyxl') as writer:
        psd.to_excel(writer, index=False)
    st.download_button("⬇️ Descargar PSD", data=output_psd.getvalue(),
                       file_name="PSD_encontrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
