from datetime import datetime
from zoneinfo import ZoneInfo
import os

from supabase import create_client


USERNAME = "asistente.pruebas"
PASSWORD_HASH = "fd9d4501ee85122f0d45dc1c5997ec4183da65080520bb9c64c9441ec52f7041"


def main():
    url = os.environ["SUPABASE_URL"].strip()
    key = os.environ["SUPABASE_SERVICE_KEY"].strip()
    client = create_client(url, key)
    current_time = datetime.now(ZoneInfo("America/Lima")).isoformat(timespec="seconds")
    existing = (
        client.table("app_users").select("id").eq("usuario", USERNAME).execute().data or []
    )
    payload = {
        "nombre": "Asistente de Pruebas",
        "usuario": USERNAME,
        "rol": "ASISTENTE",
        "clave_hash": PASSWORD_HASH,
        "activo": True,
    }
    if existing:
        user_id = str(existing[0]["id"])
        client.table("app_users").update(payload).eq("id", user_id).execute()
    else:
        payload["creado_en"] = current_time
        created = client.table("app_users").insert(payload).execute().data or []
        if not created:
            raise RuntimeError("No se pudo crear el asistente global.")
        user_id = str(created[0]["id"])

    settings = (
        (f"operacion_usuario:{user_id}", "Lavado de jabas", "Operación inicial"),
        (f"acceso_global_operaciones:{user_id}", "true", "Acceso global de pruebas"),
        (f"cambio_clave_pendiente:{user_id}", "PENDIENTE", "Contraseña temporal"),
    )
    for config_key, value, description in settings:
        client.table("configuracion").upsert({
            "clave": config_key,
            "valor": value,
            "descripcion": description,
            "actualizado_en": current_time,
        }, on_conflict="clave").execute()
    print(f"OK: {USERNAME} habilitado para todas las operaciones")


if __name__ == "__main__":
    main()
