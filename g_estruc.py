import os
from pathlib import Path

def listar_estructura(ruta_base, archivo, prefijo="", omitir_carpetas=None):
    """
    Recorre de forma recursiva las carpetas y archivos, dibuja el árbol
    y escribe el resultado tanto en la consola como en el archivo.
    """
    if omitir_carpetas is None:
        omitir_carpetas = {
            'venv', '.venv', 'env', '__pycache__', '.git', 
            '.idea', '.vscode', 'staticfiles', 'media'
        }
    
    ruta_base = Path(ruta_base)
    
    try:
        elementos = sorted(
            list(ruta_base.iterdir()), 
            key=lambda x: (not x.is_dir(), x.name.lower())
        )
    except PermissionError:
        return

    elementos = [e for e in elementos if e.name not in omitir_carpetas]
    
    total = len(elementos)
    for i, elemento in enumerate(elementos):
        es_ultimo = (i == total - 1)
        conector = "└── " if es_ultimo else "├── "
        
        # Formatear la línea de texto
        linea = f"{prefijo}{conector}{elemento.name}\n"
        
        # Mostrar en consola y escribir en el archivo txt
        print(linea, end="")
        archivo.write(linea)
        
        if elemento.is_dir():
            nuevo_prefijo = prefijo + ("    " if es_ultimo else "│   ")
            listar_estructura(elemento, archivo, nuevo_prefijo, omitir_carpetas)

if __name__ == "__main__":
    directorio_actual = os.getcwd()
    nombre_archivo_salida = "estructura_proyecto.txt"
    
    # Abrimos el archivo en modo escritura con codificación UTF-8 para no perder los caracteres del árbol
    with open(nombre_archivo_salida, "w", encoding="utf-8") as archivo_txt:
        
        # Encabezados
        linea_encabezado = "="*60 + "\n"
        linea_titulo = f" ESTRUCTURA DEL PROYECTO: {os.path.basename(directorio_actual)}\n"
        
        # Escribir encabezados en consola y archivo
        print("\n" + linea_encabezado + linea_titulo + linea_encabezado + ".")
        archivo_txt.write(linea_encabezado + linea_titulo + linea_encabezado + ".\n")
        
        # Ejecutar la función recursiva pasando el archivo abierto
        listar_estructura(directorio_actual, archivo_txt)
        
        # Cierre
        print(linea_encabezado)
        archivo_txt.write(linea_encabezado)
        
    print(f"¡Listo! La estructura se ha guardado con éxito en: {nombre_archivo_salida}\n")
