import subprocess
import sys

def ejecutar_script(nombre_script):
    try:
        print(f"Ejecutando: {nombre_script}...\n")

        subprocess.run([sys.executable, nombre_script], check=True)

        print(f"\n{nombre_script} ejecutado correctamente.")
        return True

    except subprocess.CalledProcessError as e:
        print(f"\nERROR ejecutando {nombre_script}")
        print(f"Código de salida: {e.returncode}")
        return False

    except FileNotFoundError:
        print(f"\nERROR: No se encontró el archivo {nombre_script}")
        return False

def main():
    if not ejecutar_script("data_ingestion.py"):
        print("Pipeline detenido en INGESTION.")
        return

    if not ejecutar_script("data_loading.py"):
        print("Pipeline detenido en LOADING.")
        return

    if not ejecutar_script("data_analysis.py"):
        print("Pipeline detenido en ANALYSIS.")
        return

    print("PIPELINE EJECUTADO CORRECTAMENTE")

if __name__ == "__main__":
    main()