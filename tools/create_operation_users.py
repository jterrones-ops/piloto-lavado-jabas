from datetime import datetime
from zoneinfo import ZoneInfo
import os
import sys

from supabase import create_client


USERS = [
    {
        "nombre": "Rafael Zapata", "usuario": "rafael.zapata", "rol": "ASISTENTE",
        "operacion": "Lavado de jabas",
        "clave_hash": "34e52137beee89327fed87df717f8f7465c8a581c70e15c47b0a6c71a33cdf23",
    },
    {
        "nombre": "Luis Macea", "usuario": "luis.macea", "rol": "SUPERVISOR",
        "operacion": "Distribución de jabas",
        "clave_hash": "e8603feae3c2b1e7a0f1c6231e42b943e35862ac234e049092f0f8e3b042bc15",
    },
    {
        "nombre": "Supervisor Luminarias", "usuario": "supervisor.luminarias", "rol": "SUPERVISOR",
        "operacion": "Luminarias",
        "clave_hash": "71c0d2902af6941b81948cbe7ce19b55aa9b2c5e1933c294f567215855cac69a",
    },
    {
        "nombre": "Enisban Calle", "usuario": "enisban.calle", "rol": "SUPERVISOR",
        "operacion": "Acarreo de fruta",
        "clave_hash": "e7c170a3a77ba4c952015a77e83bc1213605627f9a3c2b58d12f9b3114cbc314",
    },
    {
        "nombre": "Juan Cruz", "usuario": "juan.cruz", "rol": "SUPERVISOR",
        "operacion": "Acarreo de fruta",
        "clave_hash": "d6b0ef67506d8f1466151dcd8f322858dd80cd2c8c371662e95a4b335c924a40",
    },
    {
        "nombre": "Andrés Villegas", "usuario": "andres.villegas", "rol": "SUPERVISOR",
        "operacion": "Acopios",
        "clave_hash": "3e2848b8c61aa4ef7b8ecb39926e89840be3aaed748484e6d1fcdb8d387bb598",
    },
]


def main():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("Faltan los secretos de Supabase.")
    client = create_client(url, key)
    now = datetime.now(ZoneInfo("America/Lima")).isoformat(timespec="seconds")

    for spec in USERS:
        existing = client.table("app_users").select("id").eq("usuario", spec["usuario"]).execute().data or []
        payload = {
            "nombre": spec["nombre"], "usuario": spec["usuario"],
            "rol": spec["rol"], "clave_hash": spec["clave_hash"], "activo": True,
        }
        if existing:
            user_id = str(existing[0]["id"])
            client.table("app_users").update(payload).eq("id", user_id).execute()
            action = "actualizado"
        else:
            payload["creado_en"] = now
            created = client.table("app_users").insert(payload).execute().data or []
            if not created:
                raise RuntimeError(f"No se pudo crear {spec['usuario']}.")
            user_id = str(created[0]["id"])
            action = "creado"

        for config_key, value, description in (
            (f"operacion_usuario:{user_id}", spec["operacion"], "Operación principal asignada al usuario"),
            (f"cambio_clave_pendiente:{user_id}", "PENDIENTE", "Cambio de contraseña temporal pendiente"),
        ):
            client.table("configuracion").upsert({
                "clave": config_key, "valor": value,
                "descripcion": description, "actualizado_en": now,
            }, on_conflict="clave").execute()
        print(f"OK: {spec['usuario']} · {spec['rol']} · {spec['operacion']} · {action}")

    print(f"USUARIOS LISTOS: {len(USERS)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)
