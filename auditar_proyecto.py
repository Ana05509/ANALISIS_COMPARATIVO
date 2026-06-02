import os

def generar_arbol(ruta_inicial, carpetas_ignoradas=None, prefijo=""):
    if carpetas_ignoradas is None:
        # Ignoramos el entorno virtual, git y la caché de python
        carpetas_ignoradas = {'.git', 'venv', '.venv', 'env', '__pycache__', '.vscode'}
    
    # Obtener contenido ordenado (carpetas primero, luego archivos)
    try:
        contenido = sorted(os.listdir(ruta_inicial), key=lambda x: (not os.path.isdir(os.path.join(ruta_inicial, x)), x.lower()))
    except PermissionError:
        return ""

    resultado = ""
    for i, elemento in enumerate(contenido):
        if elemento in carpetas_ignoradas:
            continue
        
        ruta_completa = os.path.join(ruta_inicial, elemento)
        es_ultimo = (i == len(contenido) - 1)
        
        # Símbolos visuales para el árbol
        conector = "└── " if es_ultimo else "├── "
        resultado += f"{prefijo}{conector}{elemento}\n"
        
        if os.path.isdir(ruta_completa):
            # Extender el prefijo para las subcarpetas
            siguiente_prefijo = prefijo + ("    " if es_ultimo else "│   ")
            resultado += generar_arbol(ruta_completa, carpetas_ignoradas, siguiente_prefijo)
            
    return resultado

if __name__ == "__main__":
    ruta_proyecto = os.getcwd() # Obtiene la carpeta actual donde estás parado
    print(f"Analizando estructura en: {ruta_proyecto}\n")
    
    estructura = generar_arbol(ruta_proyecto)
    
    # Guardar el reporte en un archivo de texto
    with open("estructura_proyecto.txt", "w", encoding="utf-8") as f:
        f.write(f"Estructura del Proyecto:\n{ruta_proyecto}\n\n")
        f.write(estructura)
        
    print("¡Listo! Se ha guardado la estructura en 'estructura_proyecto.txt'")