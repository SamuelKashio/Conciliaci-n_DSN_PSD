import streamlit as st
import pandas as pd
from datetime import datetime
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
                psp_tin_raw = linea[205:217].strip()
                psp_tin = psp_tin_raw.lstrip('0')

                monto_raw = linea[73:88].strip()
                monto = int(monto_raw) / 100 if monto_raw.isdigit() else None

                medio_atencion = linea[156:168].strip()

                anio = linea[57:61]
                mes = linea[61:63]
                dia = linea[63:65]
                fecha_pago = f"{dia}/{mes}/{anio}" if anio and mes and dia else ""

                hora = linea[168:170]
                minuto = linea[170:172]
                segundo = linea[172:174]
                hora_pago = f"{hora}:{minuto}:{segundo}" if hora and minuto and segundo else ""

                nro_operacion = linea[124:130].strip()

                registros.append({
                    'PSP_TIN': psp_tin,
                    'Monto total pagado': monto,
                    'Medio de atención': medio_atencion,
                    'Fecha de pago': fecha_pago,
                    'Hora de atención': hora_pago,
                    'Nº operación': nro_operacion
                })
            except Exception as e:
                print(f"Error al procesar línea: {linea}\n{e}")

    return pd.DataFrame(registros)

@st.cache_data
def cargar_metabase(archivo):
    df = pd.read_excel(archivo)
    df = df.rename(columns={'Deuda_PspTin': 'psp_tin'})  # Renombrar para compatibilidad
    return df

# ----------------------------
# INTERFAZ
# ----------------------------
st.title('Conciliación de Pagos: DSN y PSD')
st.markdown("""
Herramienta para identificar:
- **DSN**: Depósitos registrados en el banco que no fueron notificados en Kashio.
- **PSD**: Pagos registrados como "Pagado" en Kashio, pero no encontrados en el banco.

Filtra automáticamente solo las operaciones del **BCP** en **moneda PEN** y elimina duplicados de `psp_tin`.
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
    data_metabase = data_metabase.drop_duplicates(subset='psp_tin')

    columnas = data_metabase.columns
    if 'Banco' not in columnas or 'Moneda' not in columnas:
        st.error("❌ No se encontraron las columnas 'Banco' y 'Moneda' en el archivo de Metabase.")
    else:
        col_banco = 'Banco'
        col_moneda = 'Moneda'
        col_meta = 'psp_tin'
        col_eecc = 'PSP_TIN'

        data_metabase_bcp_pen = data_metabase[
            (data_metabase[col_banco].astype(str).str.upper() == 'BCP') &
            (data_metabase[col_moneda].astype(str).str.upper() == 'PEN')
        ]
        cantidad_filtrada = str(len(data_metabase_bcp_pen))
        st.info(f"🔍 Se filtraron {cantidad_filtrada} operaciones del BCP en moneda PEN desde Metabase (sin duplicados).")

        # -----------------------
        # 🟡 DSN
        # -----------------------
        st.subheader('🔎 DSN (Depósitos Sin Notificación)')
        dsn = df_filtrado[~df_filtrado[col_eecc].isin(data_metabase_bcp_pen[col_meta])]
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
