import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import io

# Configuración de la página
@st.cache_data
def cargar_eecc(archivo):
    return pd.read_excel(archivo, skiprows=7)

@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)

st.title('Prevencion de DSN')
st.subheader('Herramienta para la detección de DSN en EECC del banco')
st.write('Esta herramienta permite detectar DSN en los EECC del banco y compararlos con los metabase.') 
st.divider()

#seccion para subir el EECC del banco en formato excel
archivo = st.file_uploader('Subir el EECC del banco', type = ['xlsx', 'xls'])

#condicional al leer el excel
if archivo is not None:
    start = time.time()
    df = cargar_eecc(archivo)
    st.caption(f"⏱ EECC cargado en {round(time.time() - start, 2)} segundos")

    #df = pd.read_excel(archivo, skiprows= 7) #se lee el excel saltando 7 filas
    df['Descripción operación'] = df['Descripción operación'].str.strip() 
    df['Nº operación'] = df['Nº operación'].astype(str).str.strip()

        # ---- Nueva columna con el código extraído ----
    # # Usar expresiones regulares para extraer códigos que empiezan con 251
    # df['PSP_TIN'] = df['Descripción operación'].str.extract(r'(251\d{9})', expand=False)

    df['PSP_TIN'] = df['Descripción operación'].str.extract(r'(2\d{11})(?!\d)', expand=False)

    # ---- Nueva columna con formato JSON ----
    # Crear una columna con el formato JSON requerido
    df['PSPTIN_JSON'] = df['PSP_TIN'].apply(lambda x: f"'{x}'," if pd.notnull(x) else None)

    # ---- Identificar y eliminar filas duplicadas con extorno ----
    # Identificar duplicados según el "Número de operación"
    duplicados = df[df.duplicated(subset=['Nº operación'], keep=False)]

    # Filtrar los duplicados que contienen "Extorno" en "Descripción operación"
    condicion_extorno = duplicados['Descripción operación'].str.contains('Extorno', case=False, na=False)

    # Obtener los números de operación de las filas que tienen "Extorno"
    numeros_con_extorno = duplicados[condicion_extorno]['Nº operación'].unique()

    # Filtrar todas las filas que tienen esos números de operación (con o sin "Extorno")
    filas_a_eliminar = duplicados[duplicados['Nº operación'].isin(numeros_con_extorno)]

    #mostramos el df con los extornos
    st.dataframe(filas_a_eliminar)

    #almacenamos el df exportado en CSV para que se descargue al presionar el boto
    csv = filas_a_eliminar.to_csv(index=False).encode('utf-8')

    # Ajustar la hora a GMT-5
    utc_now = datetime.utcnow()
    gmt_5_now = utc_now - timedelta(hours=5)
    timestamp = gmt_5_now.strftime("%d%m%H%M")

    #boton para descargar el csv
    descargar = st.download_button(
        label = 'Descargar archivo',
        data = csv,
        file_name = f'BBDD{timestamp}.csv'
    )

    # Eliminar estas filas del DataFrame original
    df_filtrado = df[~df['Nº operación'].isin(numeros_con_extorno)]

    # ---- Eliminar las filas duplicadas en la columna 'PSPTIN' ----
    df_filtrado = df_filtrado.drop_duplicates(subset=['PSP_TIN'])

    # # ---- Eliminar las filas donde PSP_TIN no empieza con 251 o no tiene 12 dígitos ----
    # df_filtrado = df_filtrado[df_filtrado['PSP_TIN'].str.match(r'^251\d{9}$', na=False)]

    df_filtrado = df_filtrado[df_filtrado['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]



    # st.write('EECC del banco')
    #st.dataframe(df_filtrado)

    # st.write()


    # # Guardar el archivo modificado
    # # archivo_salida = 'BBDD11022000.xlsx'
    # archivo_salida = st.text_input('Escribe el nombre del archivo:')
    # salida = st.button(f'Descarga el archivo')
    # if salida:
    #     df_filtrado.to_excel(archivo_salida, index=False)

    #     st.write(f"\nArchivo procesado y guardado como: {archivo_salida}")

        # Especificar los nombres de los archivos previamente subidos a Colab

file_2_name = st.file_uploader('Subir archivo de metabaes', type = ['xlsx', 'xls'] ) #archivo del metabase

if file_2_name is not None:
    # Leer los archivos Excel
    start = time.time()
    data_2 = cargar_metabase(file_2_name)
    st.caption(f"⏱ Metabase cargado en {round(time.time() - start, 2)} segundos")

    #data_2 = pd.read_excel(file_2_name)
    data_2['psp_tin'] = data_2['psp_tin'].astype(str)
    

    #st.dataframe(data_2)
    # Mostrar columnas de los archivos para confirmar que las columnas 8 y 27 están disponibles
    # st.write("Columnas del archivo 1:")
    # st.write(df_filtrado.columns)

    # st.write("Columnas del archivo 2:")
    # st.write(data_2.columns)

    # Especificar las columnas de búsqueda (columna 8 del archivo 1 y columna 27 del archivo 2)
    criteria_column_index_1 = 7  # Índice de la columna 8 en archivo 1 (basado en 0)
    criteria_column_index_2 = 26  # Índice de la columna 27 en archivo 2 (basado en 0)

    if criteria_column_index_1 >= len(df_filtrado.columns):
        raise ValueError(f"La columna con índice {criteria_column_index_1} no se encuentra en el archivo 1.")
    if criteria_column_index_2 >= len(data_2.columns):
        raise ValueError(f"La columna con índice {criteria_column_index_2} no se encuentra en el archivo 2.")

    criteria_column_1 = df_filtrado.columns[criteria_column_index_1]
    criteria_column_2 = data_2.columns[criteria_column_index_2]

    # Identificar datos presentes en el archivo 1 pero no en el archivo 2
    data_not_in_2 = df_filtrado[~df_filtrado[criteria_column_1].isin(data_2[criteria_column_2])]

    count_dsn = len(data_not_in_2)

    # Mostrar la tabla resultante en el mismo Colab con formato
    st.write(f"{count_dsn} DSNs econtrados:")
    # display(data_not_in_2)

    st.dataframe(data_not_in_2)

    # #almacenamos el data_not_in_2 exportado en CSV para que se descargue al presionar el boto
    # csv_dsn = data_not_in_2.to_csv(index=False, sep=',', lineterminator = '\n').encode('utf-8')

    # #boton para descargar el csv de data_not_in_2
    # dsn_descargar = st.download_button(
    #     label = 'Descargar DSN encontrados',
    #     data = csv_dsn,
    #     file_name = f'DSN_encontrados.csv'
    # )

    import io

    # Crear un buffer de memoria para el archivo Excel
    output = io.BytesIO()

    # Exportar DataFrame a Excel sin índice
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        data_not_in_2.to_excel(writer, index=False, sheet_name='Hoja1')

    # Obtener el contenido del archivo en bytes
    excel_data = output.getvalue()

    # Botón para descargar el archivo Excel en Streamlit
    dsn_descargar = st.download_button(
        label='Descargar DSN encontrados (Excel)',
        data=excel_data,
        file_name='DSN_encontrados.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


    # # Exportar resultados a un archivo Excel
    # output_file = "DSN encontrados1200.xlsx"
    # data_not_in_2.to_excel(output_file, index=False)

    # st.write(f"Los DSN se encuentran en el archivo: {output_file}")
