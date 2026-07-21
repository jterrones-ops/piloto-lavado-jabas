from datetime import datetime
from zoneinfo import ZoneInfo
import json
import os

from supabase import create_client


PLAN_DATE = "2026-07-21"


def main():
    client = create_client(
        os.environ["SUPABASE_URL"].strip(),
        os.environ["SUPABASE_SERVICE_KEY"].strip(),
    )
    current_time = datetime.now(ZoneInfo("America/Lima")).isoformat(timespec="seconds")
    detail = [
        {"Fecha": PLAN_DATE, "Lote": "L-101", "Variedad": "Autumn Crisp",
         "Turno": "Mañana", "Centro de acopio": "G3-G4", "Jabas del día": 18000},
        {"Fecha": PLAN_DATE, "Lote": "L-205", "Variedad": "Sweet Globe",
         "Turno": "Día", "Centro de acopio": "F1-F2", "Jabas del día": 15000},
        {"Fecha": PLAN_DATE, "Lote": "L-309", "Variedad": "Red Globe",
         "Turno": "Noche", "Centro de acopio": "G14-H14", "Jabas del día": 12000},
    ]
    plan = {
        "fecha": PLAN_DATE,
        "archivo": "Escenario ficticio integral",
        "hoja": "Plan de pruebas",
        "total_jabas": 45000,
        "jabas_recibidas": 45000,
        "jabas_packing": 43500,
        "jabas_blancas": 18000,
        "jabas_rojas": 4500,
        "jabas_lavado": 22500,
        "variedades": {"Autumn Crisp": 18000, "Sweet Globe": 15000, "Red Globe": 12000},
        "lotes": {"L-101": 18000, "L-205": 15000, "L-309": 12000},
        "acopios": {"G3-G4": 18000, "F1-F2": 15000, "G14-H14": 12000},
        "detalle": detail,
        "procesos": {
            "Lavado de jabas": {
                "personal": 21,
                "meta": 22500,
                "unidad": "jabas",
                "labores": {"Lavado": 15, "Secado": 6},
            },
            "Distribución de jabas": {
                "personal": 18,
                "meta": 45000,
                "unidad": "jabas",
                "labores": {
                    "Colocación de hilo nylon": 3,
                    "Colocación de lámina": 3,
                    "Colocación de burbupack": 3,
                    "Estiba": 5,
                    "Desestiba en puntos de cosecha": 4,
                },
            },
            "Luminarias": {
                "personal": 16,
                "meta": 120,
                "unidad": "luminarias",
                "labores": {"Carga": 4, "Distribución": 6, "Recojo": 6},
            },
            "Acarreo de fruta": {
                "personal": 15,
                "meta": 30,
                "unidad": "viajes",
                "labores": {"Lote → Acopio": 8, "Acopio → Packing": 7},
            },
            "Acopios": {
                "personal": 12,
                "meta": 45000,
                "unidad": "jabas recibidas",
                "labores": {
                    "Asistente (acopiador)": 3,
                    "Estibadores": 6,
                    "Montacarguistas": 3,
                },
            },
        },
    }
    client.table("configuracion").upsert({
        "clave": f"plan_diario:{PLAN_DATE}",
        "valor": json.dumps(plan, ensure_ascii=False),
        "descripcion": "Planificación ficticia integral para pruebas",
        "actualizado_en": current_time,
    }, on_conflict="clave").execute()
    print(f"OK: planificación integral cargada para {PLAN_DATE}")


if __name__ == "__main__":
    main()
