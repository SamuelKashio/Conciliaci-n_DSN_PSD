import streamlit as st
import pandas as pd
import numpy as np
import io
import time
from datetime import datetime

# -------------------------------------------------
# CARGA CREP TXT (BCP)
# -------------------------------------------------
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
                fecha_hora_pago = datetime.strptime(
                    f"{dia}/{mes}/{anio} {hora}:{minuto}:{segundo}",
                    "%d/%m/%Y %H:%M:%S"
                )
                nro_operacion = linea[124:130].strip()
                registros.append({
                    'PSP_TIN': psp_tin,
                    'Monto': monto,
                    'Medio de atención': medio_atencion,
                    'Fecha': fecha_pago,
                    'Hora': hora_pago,
                    'FechaHora': fecha_hora_pago,
                    'Nº operación': nro_operacion
                })
            except:
                continue
    df = pd.DataFrame(registros)
    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    return df.drop_duplicates(subset='PSP_TIN'), True


# -------------------------------------------------
# CARGA EECC BCP EXCEL
# -------------------------------------------------
@st.cache_data
def cargar_excel_bcp(archivo):
    df = pd.read_excel(archivo, skiprows=7)
    df['Descripción operación'] = df['Descripción operación'].astype(str).str.strip()
    df['Nº operación'] = df['Nº operación'].astype(str).str.strip()
    df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce')
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
    df['PSP_TIN'] = df['Descripción operación'].str.extract(r'(2\d{11})(?!\d)', expand=False)

    # Extornos por Nº operación
    duplicados = df[df.duplicated(subset=['Nº operación'], keep=False)]
    extornos = duplicados['Descripción operación'].str.contains('Extorno', case=False, na=False)
    numeros_extorno = duplicados[extornos]['Nº operación'].unique()
    df_filtrado = df[~df['Nº operación'].isin(numeros_extorno)]

    # Solo PSP_TIN válidos
    df_filtrado = df_filtrado[df_filtrado['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    df_filtrado = df_filtrado.drop_duplicates(subset='PSP_TIN')

    return df_filtrado[['PSP_TIN', 'Monto', 'Fecha', 'Nº operación']], False


# -------------------------------------------------
# CARGA EECC BBVA EXCEL
# -------------------------------------------------
@st.cache_data
def cargar_excel_bbva(archivo):
    # El BBVA trae texto y filtros arriba: nos saltamos las primeras 10 filas
    df = pd.read_excel(archivo, skiprows=10)

    cols = df.columns

    # Detectar columnas clave con fallback por posición
    col_concepto = 'Concepto' if 'Concepto' in cols else cols[3]

    if 'Nº Operación' in cols:
        col_nro_op = 'Nº Operación'
    elif 'N° Operación' in cols:
        col_nro_op = 'N° Operación'
    else:
        col_nro_op = cols[4]

    col_importe = 'Importe' if 'Importe' in cols else cols[5]
    col_fecha = 'F.Operación' if 'F.Operación' in cols else cols[0]

    # Limpieza básica
    df[col_concepto] = df[col_concepto].astype(str).str.strip()
    df[col_nro_op] = df[col_nro_op].astype(str).str.strip()

    # Monto y fecha
    df['Monto'] = pd.to_numeric(df[col_importe], errors='coerce')
    df['Fecha'] = pd.to_datetime(df[col_fecha], format='%d-%m-%Y', errors='coerce')

    # Extraer PSP_TIN desde Concepto (12 dígitos empezando en 2)
    df['PSP_TIN'] = df[col_concepto].str.extract(r'(2\d{11})(?!\d)', expand=False)

    # Solo PSP_TIN válidos
    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]

    # Extornos BBVA: misma operación con positivo y negativo
    duplicados = df[df.duplicated(subset=[col_nro_op], keep=False)]
    ops_extorno = duplicados.groupby(col_nro_op)['Monto'].apply(
        lambda s: s.gt(0).any() and s.lt(0).any()
    )
    numeros_extorno = ops_extorno[ops_extorno].index

    df_filtrado = df[~df[col_nro_op].isin(numeros_extorno)]

    # Eliminamos duplicados por PSP_TIN
    df_filtrado = df_filtrado.drop_duplicates(subset='PSP_TIN')

    # Normalizamos nombre de la columna de número de operación
    df_filtrado = df_filtrado.rename(columns={col_nro_op: 'Nº operación'})

    return df_filtrado[['PSP_TIN', 'Monto', 'Fecha', 'Nº operación']], False


# -------------------------------------------------
# CARGA METABASE
# -------------------------------------------------
@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)


# -------------------------------------------------
# INTERFAZ STREAMLIT
# -------------------------------------------------
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
banco_archivo = None  # 'BCP' o 'BBVA' según el archivo cargado


# -------------------------------------------------
# PROCESO DE CARGA ARCHIVO BANCO
# -------------------------------------------------
if archivo_banco is not None:
    start = time.time()
    try:
        if archivo_banco.name.endswith('.txt'):
            # CREP (BCP)
            st.caption("Formato detectado: CREP (.txt)")
            df_banco, es_crep = cargar_txt_crep(archivo_banco)
            hora_corte = df_banco['FechaHora'].max()
            banco_archivo = "BCP"  # CREP es BCP
            st.info(f"🕐 Hora de corte detectada: {hora_corte}")
        else:
            # Excel: detectar si es BBVA o BCP
            archivo_banco.seek(0)
            preview = pd.read_excel(archivo_banco, nrows=15, header=None)
            archivo_banco.seek(0)

            if preview.iloc[:, 0].astype(str).str.contains('Movimientos del Día', na=False).any():
                st.caption("Formato detectado: EECC BBVA (.xlsx)")
                df_banco, es_crep = cargar_excel_bbva(archivo_banco)
                banco_archivo = "BBVA"
            else:
                st.caption("Formato detectado: EECC BCP (.xlsx)")
                df_banco, es_crep = cargar_excel_bcp(archivo_banco)
                banco_archivo = "BCP"

        st.success(
            f"✅ Archivo del banco cargado con {len(df_banco)} operaciones únicas en "
            f"{round(time.time() - start, 2)} s"
        )
    except Exception as e:
        st.error(f"❌ Error al procesar el archivo del banco: {e}")
        st.stop()


# -------------------------------------------------
# CRUCE CON METABASE: DSN y PSD
# -------------------------------------------------
if archivo_banco and archivo_metabase:
    if banco_archivo is None:
        st.error("❌ No se pudo determinar el banco del archivo cargado (BCP/BBVA).")
        st.stop()

    start = time.time()
    df_meta = cargar_metabase(archivo_metabase)
    st.caption(f"✅ Metabase cargado en {round(time.time() - start, 2)} segundos")

    # --- Detección de columnas en Metabase por CONTENIDO ---
    def detectar_columna_psptin(df):
        for col in df.columns:
            serie = df[col].astype(str).str.strip()
            mask = serie.str.match(r'^2\d{11}$', na=False)
            if mask.sum() > 0:
                return col
        return None

    def detectar_columna_banco(df):
        bancos_conocidos = {"BCP", "BBVA", "SCOTIABANK", "INTERBANK", "BANBIF"}
        for col in df.columns:
            valores = df[col].dropna().astype(str).str.upper().str.strip()
            if len(valores) == 0:
                continue
            unicos = set(valores.unique())
            if len(unicos & bancos_conocidos) >= 1:
                return col
        return None

    def detectar_columna_moneda(df):
        monedas_conocidas = {"PEN", "S/", "USD", "US$", "EUR"}
        for col in df.columns:
            valores = df[col].dropna().astype(str).str.upper().str.strip()
            if len(valores) == 0:
                continue
            unicos = set(valores.unique())
            if len(unicos & monedas_conocidas) >= 1:
                return col
        return None

    def detectar_columna_fecha(df):
        # Preferimos columnas que ya sean datetime
        datetime_cols = [col for col in df.columns if np.issubdtype(df[col].dtype, np.datetime64)]
        if datetime_cols:
            return datetime_cols[0]

        # Si no hay datetime, probamos a convertir columnas candidatas
        for col in df.columns:
            serie = df[col].dropna()
            if len(serie) == 0:
                continue
            muestra = serie.astype(str).head(20)
            try:
                convertida = pd.to_datetime(muestra, errors='coerce', dayfirst=True)
                if convertida.notna().mean() > 0.7:
                    return col
            except Exception:
                continue
        return None

    col_psptin = detectar_columna_psptin(df_meta)
    col_banco = detectar_columna_banco(df_meta)
    col_moneda = detectar_columna_moneda(df_meta)
    col_fecha = detectar_columna_fecha(df_meta)

    if not all([col_psptin, col_banco, col_moneda, col_fecha]):
        st.error(f"""
        ❌ No se pudieron detectar todas las columnas necesarias en el archivo de Metabase.

        Columnas detectadas:
        - PSP_TIN: {col_psptin}
        - Banco: {col_banco}
        - Moneda: {col_moneda}
        - Fecha: {col_fecha}

        Columnas disponibles en el archivo:
        {list(df_meta.columns)}
        """)
        st.stop()

    # Normalizaciones y duplicados
    df_meta[col_psptin] = df_meta[col_psptin].astype(str)
    df_meta = df_meta.drop_duplicates(subset=col_psptin)
    df_meta[col_fecha] = pd.to_datetime(df_meta[col_fecha], errors='coerce', dayfirst=True)

    # Filtrado por banco (BCP/BBVA), PEN y hora de corte si aplica
    if hora_corte:
        df_meta_banco_pen = df_meta[
            (df_meta[col_banco].astype(str).str.upper().str.strip() == banco_archivo) &
            (df_meta[col_moneda].astype(str).str.upper().str.strip().isin(["PEN", "S/"])) &
            (df_meta[col_fecha] <= hora_corte)
        ]
        st.info(
            f"🔍 {len(df_meta_banco_pen)} registros filtrados de Metabase "
            f"({banco_archivo} - PEN) hasta la hora de corte"
        )
    else:
        df_meta_banco_pen = df_meta[
            (df_meta[col_banco].astype(str).str.upper().str.strip() == banco_archivo) &
            (df_meta[col_moneda].astype(str).str.upper().str.strip().isin(["PEN", "S/"]))
        ]
        st.info(
            f"🔍 {len(df_meta_banco_pen)} registros filtrados de Metabase "
            f"({banco_archivo} - PEN)"
        )

    # DSN: están en el banco pero no en Metabase
    dsn = df_banco[~df_banco['PSP_TIN'].isin(df_meta_banco_pen[col_psptin])]
    st.subheader("🟡 DSN encontrados")
    st.write(f"{len(dsn)} DSN detectados")
    if not es_crep:
        dsn['Fecha'] = dsn['Fecha'].dt.strftime('%d/%m/%Y')
    st.dataframe(dsn)

    output_dsn = io.BytesIO()
    with pd.ExcelWriter(output_dsn, engine='openpyxl') as writer:
        dsn.to_excel(writer, index=False)
    st.download_button(
        "⬇️ Descargar DSN",
        data=output_dsn.getvalue(),
        file_name="DSN_encontrados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # PSD: están en Metabase pero no en el banco
    psd = df_meta_banco_pen[~df_meta_banco_pen[col_psptin].isin(df_banco['PSP_TIN'])]
    st.subheader("🔁 PSD encontrados")
    st.write(f"{len(psd)} PSD detectados")
    st.dataframe(psd)

    output_psd = io.BytesIO()
    with pd.ExcelWriter(output_psd, engine='openpyxl') as writer:
        psd.to_excel(writer, index=False)
    st.download_button(
        "⬇️ Descargar PSD",
        data=output_psd.getvalue(),
        file_name="PSD_encontrados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
