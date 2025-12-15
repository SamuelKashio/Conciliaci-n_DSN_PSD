import streamlit as st
import pandas as pd
import io
import time
from datetime import datetime

# =================================================
# CREP BCP (.txt)
# =================================================
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

                anio = linea[57:61]
                mes = linea[61:63]
                dia = linea[63:65]
                hora = linea[168:170]
                minuto = linea[170:172]
                segundo = linea[172:174]

                fecha_pago = f"{dia}/{mes}/{anio}"
                hora_pago = f"{hora}:{minuto}:{segundo}"
                fecha_hora_pago = datetime.strptime(
                    f"{fecha_pago} {hora_pago}", "%d/%m/%Y %H:%M:%S"
                )

                nro_operacion = linea[124:130].strip()

                registros.append({
                    "PSP_TIN": psp_tin,
                    "Monto": monto,
                    "Fecha": fecha_pago,
                    "Hora": hora_pago,
                    "FechaHora": fecha_hora_pago,
                    "Nº operación": nro_operacion
                })
            except:
                continue

    df = pd.DataFrame(registros)
    df = df[df["PSP_TIN"].str.match(r"^2\d{11}$", na=False)]
    return df.drop_duplicates(subset="PSP_TIN"), True


# =================================================
# EECC BCP (.xlsx)
# =================================================
@st.cache_data
def cargar_excel_bcp(archivo):
    df = pd.read_excel(archivo, skiprows=7)

    df["Descripción operación"] = df["Descripción operación"].astype(str).str.strip()
    df["Nº operación"] = df["Nº operación"].astype(str).str.strip()
    df["Monto"] = pd.to_numeric(df["Monto"], errors="coerce")
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")

    df["PSP_TIN"] = df["Descripción operación"].str.extract(r"(2\d{11})(?!\d)")

    duplicados = df[df.duplicated(subset=["Nº operación"], keep=False)]
    extornos = duplicados["Descripción operación"].str.contains("Extorno", case=False, na=False)
    numeros_extorno = duplicados[extornos]["Nº operación"].unique()

    df = df[~df["Nº operación"].isin(numeros_extorno)]
    df = df[df["PSP_TIN"].str.match(r"^2\d{11}$", na=False)]
    df = df.drop_duplicates(subset="PSP_TIN")

    return df[["PSP_TIN", "Monto", "Fecha", "Nº operación"]], False


# =================================================
# EECC BBVA DIARIO (.xlsx)  (ya existente)
# =================================================
@st.cache_data
def cargar_excel_bbva(archivo):
    df = pd.read_excel(archivo, skiprows=10)
    df.columns = df.columns.str.strip()

    df["Monto"] = pd.to_numeric(df["Importe"], errors="coerce")
    df["Fecha"] = pd.to_datetime(df["F.Operación"], format="%d-%m-%Y", errors="coerce")

    df["Concepto"] = df["Concepto"].astype(str).str.strip()
    df["PSP_TIN"] = df["Concepto"].str.extract(r"(2\d{11})(?!\d)")

    df = df[df["PSP_TIN"].str.match(r"^2\d{11}$", na=False)]

    duplicados = df[df.duplicated(subset=["Núm.Movimiento"], keep=False)]
    extornos = duplicados["Concepto"].str.contains("Extorno", case=False, na=False)
    numeros_extorno = duplicados[extornos]["Núm.Movimiento"].unique()

    df = df[~df["Núm.Movimiento"].isin(numeros_extorno)]
    df = df.drop_duplicates(subset="PSP_TIN")

    df = df.rename(columns={"Núm.Movimiento": "Nº operación"})
    return df[["PSP_TIN", "Monto", "Fecha", "Nº operación"]], False


# =================================================
# EECC BBVA HISTÓRICO (.xlsx)  (NUEVO)
# =================================================
@st.cache_data
def cargar_excel_bbva_historico(archivo):
    # En el histórico, la tabla inicia con headers en la fila 11 (0-indexed 10)
    df = pd.read_excel(archivo, skiprows=10)
    df.columns = df.columns.str.strip()

    # Columnas típicas del histórico (según tu archivo)
    # F. Operación | F. Valor | Código | Nº. Doc. | Concepto | Importe | Oficina
    col_fecha = "F. Operación"
    col_concepto = "Concepto"
    col_nro_op = "Nº. Doc."
    col_importe = "Importe"

    # Asegurar strings
    df[col_concepto] = df[col_concepto].astype(str).str.strip()
    df[col_nro_op] = df[col_nro_op].astype(str).str.strip()

    # Quitar filas de saldo (al inicio y al final de cada día)
    # Ej: "Saldo Inicial: 05-12-2025" / "Saldo Final: 14-12-2025"
    es_saldo = df[col_concepto].str.contains(r"^Saldo (Inicial|Final)\:", case=False, na=False)
    df = df[~es_saldo].copy()

    # Fecha y monto
    df["Monto"] = pd.to_numeric(df[col_importe], errors="coerce")
    df["Fecha"] = pd.to_datetime(df[col_fecha], errors="coerce")

    # PSP_TIN desde Concepto (12 dígitos que empiezan en 2)
    df["PSP_TIN"] = df[col_concepto].str.extract(r"(2\d{11})(?!\d)")

    # Solo PSP_TIN válidos
    df = df[df["PSP_TIN"].str.match(r"^2\d{11}$", na=False)]

    # Extornos: misma lógica base (por Nº. Doc. + texto "Extorno")
    duplicados = df[df.duplicated(subset=[col_nro_op], keep=False)]
    extornos = duplicados[col_concepto].str.contains("Extorno", case=False, na=False)
    numeros_extorno = duplicados[extornos][col_nro_op].unique()
    df = df[~df[col_nro_op].isin(numeros_extorno)]

    # Duplicados por PSP_TIN
    df = df.drop_duplicates(subset="PSP_TIN")

    # Normalizar nombre de operación
    df = df.rename(columns={col_nro_op: "Nº operación"})

    return df[["PSP_TIN", "Monto", "Fecha", "Nº operación"]], False


# =================================================
# METABASE
# =================================================
@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)


# =================================================
# INTERFAZ
# =================================================
st.title("Conciliación de Pagos - Kashio")
st.divider()

archivo_banco = st.file_uploader("📥 Subir EECC del banco", type=["txt", "xlsx", "xls"])
archivo_metabase = st.file_uploader("📥 Subir archivo de Metabase", type=["xlsx", "xls"])

df_banco = None
hora_corte = None
es_crep = False
banco_archivo = None


# =================================================
# CARGA BANCO
# =================================================
if archivo_banco:
    start = time.time()

    if archivo_banco.name.endswith(".txt"):
        df_banco, es_crep = cargar_txt_crep(archivo_banco)
        hora_corte = df_banco["FechaHora"].max()
        banco_archivo = "BCP"
        st.info(f"Hora de corte: {hora_corte}")
    else:
        # Detectar si es BBVA diario / BBVA histórico / BCP
        archivo_banco.seek(0)
        preview = pd.read_excel(archivo_banco, nrows=25, header=None)
        archivo_banco.seek(0)

        # Unimos todo el preview a texto para detectar título
        preview_text = " ".join(preview.fillna("").astype(str).values.flatten()).upper()

        if "HISTÓRICO DE MOVIMIENTOS" in preview_text or "HISTORICO DE MOVIMIENTOS" in preview_text:
            df_banco, es_crep = cargar_excel_bbva_historico(archivo_banco)
            banco_archivo = "BBVA"
            st.caption("Formato detectado: BBVA - Movimientos Históricos (.xlsx)")
        elif "MOVIMIENTOS DEL DÍA" in preview_text or "MOVIMIENTOS DEL DIA" in preview_text:
            df_banco, es_crep = cargar_excel_bbva(archivo_banco)
            banco_archivo = "BBVA"
            st.caption("Formato detectado: BBVA - Movimientos del Día (.xlsx)")
        else:
            df_banco, es_crep = cargar_excel_bcp(archivo_banco)
            banco_archivo = "BCP"
            st.caption("Formato detectado: EECC BCP (.xlsx)")

    st.success(f"EECC cargado con {len(df_banco)} PSP_TIN únicos (en {round(time.time() - start, 2)}s)")
    st.dataframe(df_banco)


# =================================================
# CRUCE
# =================================================
if archivo_banco and archivo_metabase:
    df_meta = cargar_metabase(archivo_metabase)

    col_psptin = "Deuda_PspTin"
    col_banco = "Banco"
    col_moneda = " Moneda"
    col_fecha = "PC_create_date_GMT_Peru"

    df_meta[col_psptin] = df_meta[col_psptin].astype(str)
    df_meta = df_meta.drop_duplicates(subset=col_psptin)
    df_meta[col_fecha] = pd.to_datetime(df_meta[col_fecha], errors="coerce")

    df_meta_filtrado = df_meta[
        (df_meta[col_banco].astype(str).str.upper().str.contains(banco_archivo)) &
        (df_meta[col_moneda].astype(str).str.upper().str.strip() == "PEN")
    ]

    st.info(f"PSP_TIN únicos en Metabase: {df_meta_filtrado[col_psptin].nunique()}")

    # DSN
    dsn = df_banco[~df_banco["PSP_TIN"].isin(df_meta_filtrado[col_psptin])]
    st.subheader("🟡 DSN encontrados")
    st.write(len(dsn))
    st.dataframe(dsn)

    # XLSX DSN
    out_dsn = io.BytesIO()
    with pd.ExcelWriter(out_dsn, engine="openpyxl") as writer:
        dsn.to_excel(writer, index=False)

    st.download_button(
        "⬇️ Descargar DSN (Excel)",
        out_dsn.getvalue(),
        "DSN_encontrados.xlsx"
    )

    # TXT DSN (PSP_TIN concatenados por coma)
    psptin_txt = ",".join(
        dsn["PSP_TIN"].dropna().astype(str).str.strip().unique()
    )

    st.download_button(
        "⬇️ Descargar DSN (PSP_TIN en .txt)",
        data=psptin_txt.encode("utf-8"),
        file_name="DSN_psptin.txt",
        mime="text/plain"
    )

    # PSD
    psd = df_meta_filtrado[~df_meta_filtrado[col_psptin].isin(df_banco["PSP_TIN"])]
    st.subheader("🔁 PSD encontrados")
    st.write(len(psd))
    st.dataframe(psd)
