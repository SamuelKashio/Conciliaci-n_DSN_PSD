import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import io

# ----------------------------
# Configuración y funciones
# ----------------------------
@st.cache_data
def cargar_eecc(archivo):
    return pd.read_excel(archivo, skiprows=7)

@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)

st.title('Conciliación de Pagos: DSN y PSD')
st.write('Herramienta para identificar **DSN (Depósitos Sin Notificación)** y **PSD (Pagos Sin Depósito)** entre EECC del banco (BCP) y registros de Metabase.')
st.divider()

# ----------------------------
# Cargar archivos
# ----------------------------
archivo_eecc = st.file_uploader('📥 Subir EECC del banco (BCP)', type=['xlsx', 'xls'])
archivo_metabase = st.file_uploader('📥 Subir archivo de Metabase (todos los bancos)', type=['xlsx', 'xls'])

# Procesar EECC
if archivo_eecc is not None:
    start = time.time()
    df = cargar_eecc(archivo_eecc)
    st.caption(f"⏱ EECC cargado en {round(time.time() - start, 2)} segundos")

    df['Descripción operación'] = df['Descripción operación'].str.strip()
    df['Nº operación'] = df['Nº operación'].astype(str).str.strip()
    df['PSP_TIN'] = df['Descripción operación'].str.extract(r'(2\d{11})(?!\d)', expand=False)
    df['PSPTIN_JSON'] = df['PSP_TIN'].apply(lambda x: f"'{x}'," if pd.notnull(x) else None)

    # Eliminar duplicados con extornos
    duplicados = df[df.duplicated(subset=['Nº operación'], keep=False)]
    condicion_extorno = duplicados['Descripción operación'].str.contains('Extorno', case=False, na=False)
    numeros_con_extorno = duplicados[condicion_extorno]['Nº operación'].unique()
    filas_a_eliminar = duplicados[duplicados['Nº operación'].isin(numeros_con_extorno)]
    st.subheader('🧾 Filas eliminadas por extornos')
    st.dataframe(filas_a_eliminar)

    # Descargar filas eliminadas
    csv_extornos = filas_a_eliminar.to_csv(index=False).encode('utf-8')
    timestamp = (datetime.utcnow() - timedelta(hours=5)).strftime("%d%m%H%M")
    st.download_button(
        label='Descargar extornos detectados (CSV)',
        data=csv_extornos,
        file_name=f'Extornos_{timestamp}.csv'
    )

    # EECC limpio
    df_filtrado = df[~df['Nº operación'].isin(numeros_con_extorno)]
    df_filtrado = df_filtrado.drop_duplicates(subset=['PSP_TIN'])
    df_filtrado = df_filtrado[df_filtrado['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]

# Procesar Metabase y comparar
if archivo_eecc is not None and archivo_metabase is not None:
    start = time.time()
    data_metabase = cargar_metabase(archivo_metabase)
    st.caption(f"⏱ Metabase cargado en {round(time.time() - start, 2)} segundos")

    data_metabase['psp_tin'] = data_metabase['psp_tin'].astype(str)

    # Filtrar solo las operaciones BCP en Metabase (columna 11 → índice 10)
    if 10 >= len(data_metabase.columns):
        st.error("❌ La columna 11 (banco) no se encuentra en el archivo de Metabase.")
    else:
        columna_banco = data_metabase.columns[10]
        data_metabase_bcp = data_metabase[data_metabase[columna_banco].astype(str).str.upper() == 'BCP']
        cantidad_bcp = str(len(data_metabase_bcp))
        st.info(f"🔍 Se filtraron {cantidad_bcp} operaciones del BCP desde Metabase.")

        # Índices de comparación
        col_eecc_index = 7   # columna 8
        col_meta_index = 26  # columna 27

        if col_eecc_index >= len(df_filtrado.columns) or col_meta_index >= len(data_metabase.columns):
            st.error("❌ Revisa que las columnas 8 (EECC) y 27 (Metabase) existan.")
        else:
            col_eecc = df_filtrado.columns[col_eecc_index]
            col_meta = data_metabase.columns[col_meta_index]

            # -----------------------
            # 🟡 DSN: en EECC pero no en Metabase
            # -----------------------
            st.subheader('🔎 DSN (Depósitos Sin Notificación)')
            dsn = df_filtrado[~df_filtrado[col_eecc].isin(data_metabase[col_meta])]
            st.write(f"✅ {len(dsn)} DSN encontrados")
            st.dataframe(dsn)

            # Descargar DSN
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
            # 🔁 PSD: en Metabase (BCP) pero no en EECC
            # -----------------------
            st.subheader('🔁 PSD (Pagos Sin Depósito)')
            psd = data_metabase_bcp[~data_metabase_bcp[col_meta].isin(df_filtrado[col_eecc])]
            st.write(f"⚠️ {len(psd)} PSD encontrados")
            st.dataframe(psd)

            # Descargar PSD
            output_psd = io.BytesIO()
            with pd.ExcelWriter(output_psd, engine='openpyxl') as writer:
                psd.to_excel(writer, index=False, sheet_name='PSD')
            st.download_button(
                label='Descargar PSD encontrados (Excel)',
                data=output_psd.getvalue(),
                file_name='PSD_encontrados.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
