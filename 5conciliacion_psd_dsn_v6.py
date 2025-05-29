import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import io

# ----------------------------
# FUNCIONES
# ----------------------------
@st.cache_data
def cargar_txt_crep(archivo_txt):
    lineas = archivo_txt.read().decode('utf-8').splitlines()
    registros = []

    for linea in lineas:
        if linea.startswith('DD'):
            try:
                monto_raw = linea[60:74].strip()
                monto = int(monto_raw) / 100 if monto_raw.isdigit() else None

                fecha_raw = linea[40:48]
                fecha_pago = f"{fecha_raw[6:8]}/{fecha_raw[4:6]}/{fecha_raw[0:4]}" if len(fecha_raw) == 8 else ""

                hora_raw = linea[48:54]
                hora_pago = f"{hora_raw[0:2]}:{hora_raw[2:4]}:{hora_raw[4:6]}" if len(hora_raw) == 6 else ""

                medio_atencion = linea[110:121].strip()

                psp_tin_raw = linea[205:217].strip()
                psp_tin = psp_tin_raw.lstrip('0')

                registros.append({
                    'PSP_TIN': psp_tin,
                    'Monto total pagado': monto,
                    'Medio de atención': medio_atencion,
                    'Fecha de pago': fecha_pago,
                    'Hora de atención': hora_pago,
                    'Nº operación': psp_tin  # compatibilidad
                })
            except Exception as e:
                print(f"Error al procesar línea: {linea}\n{e}")

    return pd.DataFrame(registros)

@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)

# ----------------------------
# INTERFAZ
# ----------------------------
st.title('Conciliación de Pagos: DSN y PSD')
st.markdown("""
Herramienta para identificar:
- **DSN**: Depósitos registrados en el banco que no fueron notificados en Kashio.
- **PSD**: Pagos registrados como "Pagado" en Kashio, pero no encontrados en el banco.

Filtra automáticamente solo las operaciones del **BCP** en **moneda PEN**.
""")
st.divider()

archivo_txt = st.file_uploader('📥 Subir archivo CREP del banco (formato .txt)', type=['txt'])
archivo_metabase = st.file_uploader('📥 Subir archivo de Metabase (formato .xlsx)', type=['xlsx', 'xls'])

if archivo_txt is not None:
    start = time.time()
    df = cargar_txt_crep(archivo_txt)
    st.caption(f"⏱ EECC del banco cargado en {round(time.time() - start, 2)} segundos")
    st.dataframe(df.head())

    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    df_filtrado = df.drop_duplicates(subset=['PSP_TIN'])

if archivo_txt is not None and archivo_metabase is not None:
    start = time.time()
    data_metabase = cargar_metabase(archivo_metabase)
    st.caption(f"⏱ Metabase cargado en {round(time.time() - start, 2)} segundos")

    data_metabase['psp_tin'] = data_metabase['psp_tin'].astype(str)

    # Validar columnas necesarias
    if 10 >= len(data_metabase.columns) or 21 >= len(data_metabase.columns):
        st.error("❌ No se encontraron las columnas 11 (banco) y 22 (moneda) en el archivo de Metabase.")
    else:
        col_banco = data_metabase.columns[10]
        col_moneda = data_metabase.columns[21]

        # Filtrar por BCP y PEN
        data_metabase_bcp_pen = data_metabase[
            (data_metabase[col_banco].astype(str).str.upper() == 'BCP') &
            (data_metabase[col_moneda].astype(str).str.upper() == 'PEN')
        ]
        cantidad_filtrada = str(len(data_metabase_bcp_pen))
        st.info(f"🔍 Se filtraron {cantidad_filtrada} operaciones del BCP en moneda PEN desde Metabase.")

        col_eecc = 'PSP_TIN'
        col_meta = data_metabase.columns[26]

        # -----------------------
        # 🟡 DSN
        # -----------------------
        st.subheader('🔎 DSN (Depósitos Sin Notificación)')
        dsn = df_filtrado[~df_filtrado[col_eecc].isin(data_metabase[col_meta])]
        st.write(f"✅ {len(dsn)} DSN encontrados")
        st.dataframe(dsn)

        output_dsn = io.BytesIO()
        with pd.ExcelWriter(output_dsn, engine='openpyxl') as writer:
            dsn.to_excel(writer, index=False, sheet_name='DSN')
        st.download_button(
            label='Descargar DSN encontrados (Excel)',
            data=output_dsn.getvalue(),
            file_name='DSN_encontrados.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        # -----------------------
        # 🔁 PSD
        # -----------------------
        st.subheader('🔁 PSD (Pagos Sin Depósito)')
        psd = data_metabase_bcp_pen[~data_metabase_bcp_pen[col_meta].isin(df_filtrado[col_eecc])]
        st.write(f"⚠️ {len(psd)} PSD encontrados")
        st.dataframe(psd)

        output_psd = io.BytesIO()
        with pd.ExcelWriter(output_psd, engine='openpyxl') as writer:
            psd.to_excel(writer, index=False, sheet_name='PSD')
        st.download_button(
            label='Descargar PSD encontrados (Excel)',
            data=output_psd.getvalue(),
            file_name='PSD_encontrados.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
