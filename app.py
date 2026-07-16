from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Piloto Lavado de Jabas", page_icon="🧼", layout="wide")

T = {
    "users": "app_users", "turnos": "turnos", "personal": "personal_labor",
    "inc": "incidencias", "tras": "traslados_personal",
    "prod": "produccion_turno", "audit": "auditoria",
}
LABORES = ["Lavado de jabas", "Secado de jabas", "Limpieza de lámina burbupack"]
INCIDENCIAS = ["Falta de agua", "Falla de equipo", "Falta de energía", "Falta de jabas",
               "Falta de personal", "Limpieza del área", "Desperfecto mecánico",
               "Acumulación de jabas", "Otro"]


@st.cache_resource
def db():
    url = st.secrets.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("Faltan los Secrets de Supabase.")
    return create_client(url, key)


try:
    sb = db()
except Exception as e:
    st.error(f"No se pudo conectar con Supabase: {e}")
    st.stop()


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def timestamp(day, clock):
    return datetime.combine(day, clock).astimezone().isoformat(timespec="seconds")


def get(table, filters=None, order="creado_en"):
    try:
        query = sb.table(table).select("*")
        for key, value in (filters or {}).items():
            query = query.eq(key, value)
        if order:
            query = query.order(order, desc=True)
        return query.execute().data or []
    except Exception as e:
        message = getattr(e, "message", None) or str(e)
        st.error(f"Error de Supabase al consultar '{table}': {message}")
        return []


def frame(table, filters=None, order="creado_en"):
    return pd.DataFrame(get(table, filters, order))


def add(table, data):
    rows = sb.table(table).insert(data).execute().data or []
    return rows[0] if rows else None


def edit(table, data, filters):
    query = sb.table(table).update(data)
    for key, value in filters.items():
        query = query.eq(key, value)
    return query.execute().data or []


def audit(table, record_id, field, old, new, reason, user_id):
    add(T["audit"], {
        "tabla": table, "registro_id": record_id, "campo": field,
        "valor_anterior": "" if old is None else str(old),
        "valor_nuevo": "" if new is None else str(new),
        "motivo": reason, "usuario_id": user_id, "creado_en": now(),
    })


def minutes_between(start, end):
    return max(int((end - start).total_seconds() / 60), 0)


users = frame(T["users"], order="nombre")
if not users.empty and "activo" in users:
    users = users[users["activo"].fillna(False).astype(bool)]
user_by_id = {str(row["id"]): row["nombre"] for _, row in users.iterrows()} if not users.empty else {}

st.sidebar.title("🧼 Lavado de jabas")
role = st.sidebar.selectbox("Ver como", ["ASISTENTE", "SUPERVISOR", "JEFATURA"])
role_users = users[users["rol"].astype(str).str.upper() == role] if not users.empty else pd.DataFrame()
if not role_users.empty:
    options = role_users["nombre"].tolist()
    user_name = st.sidebar.selectbox("Usuario", options)
    user_row = role_users[role_users["nombre"] == user_name].iloc[0]
    user_id = str(user_row["id"])
else:
    st.sidebar.error(f"No hay un usuario activo con rol {role}.")
    st.stop()

menus = {
    "ASISTENTE": ["Inicio", "Abrir turno", "Operación", "Cerrar turno"],
    "SUPERVISOR": ["Panel", "Confirmar apertura", "Seguimiento", "Validar cierre"],
    "JEFATURA": ["Panel", "Turnos", "Incidencias", "Auditoría"],
}
page = st.sidebar.radio("Menú", menus[role])
st.sidebar.caption("Base central: Supabase")


def turn_label(row):
    assistant = user_by_id.get(str(row["asistente_id"]), "Sin asignar")
    return f"{row['fecha']} | {row['tipo_turno']} | {assistant} | {row['estado']}"


def choose_turn(statuses, assistant_id=None):
    data = frame(T["turnos"])
    if not data.empty:
        data = data[data["estado"].isin(statuses)]
    if assistant_id and not data.empty:
        data = data[data["asistente_id"].astype(str) == str(assistant_id)]
    if data.empty:
        return None
    mapping = {turn_label(row): str(row["id"]) for _, row in data.iterrows()}
    return mapping[st.selectbox("Turno", list(mapping))]


if role == "ASISTENTE" and page == "Inicio":
    st.title("Piloto Lavado de Jabas")
    data = frame(T["turnos"], {"asistente_id": user_id})
    if data.empty:
        st.info("Sin turnos registrados.")
    else:
        data["asistente"] = data["asistente_id"].astype(str).map(user_by_id)
        st.dataframe(data, width="stretch", hide_index=True)

elif role == "ASISTENTE" and page == "Abrir turno":
    st.title("Abrir turno")
    with st.form("open"):
        c1, c2 = st.columns(2)
        day = c1.date_input("Fecha", date.today())
        shift = c2.selectbox("Turno", ["Día", "Noche"])
        defaults = {"Día": ("06:00", "18:00"), "Noche": ("18:00", "06:00")}
        c1, c2 = st.columns(2)
        start = c1.time_input("Inicio", time.fromisoformat(defaults[shift][0]))
        end = c2.time_input("Fin programado", time.fromisoformat(defaults[shift][1]))
        quantities = [st.number_input(labor, 0, 200, value) for labor, value in zip(LABORES, [10, 4, 2])]
        observation = st.text_area("Observación")
        if st.form_submit_button("Enviar al supervisor", type="primary", use_container_width=True):
            try:
                row = add(T["turnos"], {
                    "fecha": str(day), "tipo_turno": "DIA" if shift == "Día" else "NOCHE",
                    "hora_programada_inicio": start.strftime("%H:%M"),
                    "hora_programada_fin": end.strftime("%H:%M"),
                    "asistente_id": user_id, "responsable_operacion": user_name,
                    "estado": "ABIERTO", "observacion_apertura": observation,
                    "creado_en": now(), "actualizado_en": now(),
                })
                turn_id = row["id"]
                add(T["personal"], [{
                    "turno_id": turn_id, "labor": labor, "cantidad_personas": quantity,
                    "hora_inicio": timestamp(day, start), "minutos_refrigerio": 45,
                    "creado_en": now(),
                } for labor, quantity in zip(LABORES, quantities)])
                audit("turnos", turn_id, "estado", None, "ABIERTO",
                      f"Personal inicial: {sum(quantities)}", user_id)
                st.success(f"Turno creado en Supabase: {turn_id}")
            except Exception as e:
                st.error(f"No se pudo crear el turno: {getattr(e, 'message', None) or str(e)}")

elif role == "ASISTENTE" and page == "Operación":
    st.title("Operación en curso")
    turn_id = choose_turn(["CONFIRMADO"], user_id)
    if turn_id is None:
        st.info("No tienes turnos en ejecución.")
    else:
        incident_tab, transfer_tab = st.tabs(["Incidencias", "Traslado interno"])
        with incident_tab:
            with st.form("inc"):
                incident_type = st.selectbox("Tipo", INCIDENCIAS)
                c1, c2 = st.columns(2)
                start = c1.time_input("Inicio", datetime.now().time().replace(second=0, microsecond=0))
                close_now = c2.checkbox("Cerrar ahora")
                end = st.time_input("Fin", datetime.now().time().replace(second=0, microsecond=0), disabled=not close_now)
                description = st.text_area("Descripción")
                if st.form_submit_button("Guardar"):
                    start_dt = datetime.combine(date.today(), start).astimezone()
                    end_dt = datetime.combine(date.today(), end).astimezone() if close_now else None
                    if end_dt and end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    add(T["inc"], {
                        "turno_id": turn_id, "tipo": incident_type, "descripcion": description,
                        "hora_inicio": start_dt.isoformat(timespec="seconds"),
                        "hora_fin": end_dt.isoformat(timespec="seconds") if end_dt else None,
                        "duracion_minutos": minutes_between(start_dt, end_dt) if end_dt else None,
                        "estado": "CERRADA" if close_now else "ABIERTA",
                        "registrado_por": user_id, "creado_en": now(),
                    })
                    st.rerun()
            st.dataframe(frame(T["inc"], {"turno_id": turn_id}), width="stretch", hide_index=True)
        with transfer_tab:
            with st.form("move"):
                c1, c2 = st.columns(2)
                origin = c1.selectbox("Origen", LABORES)
                destination = c2.selectbox("Destino", LABORES, index=1)
                amount = st.number_input("Personas", 1, 200, 1)
                reason = st.text_input("Motivo")
                if st.form_submit_button("Registrar"):
                    if origin == destination:
                        st.error("Origen y destino deben ser distintos.")
                    else:
                        add(T["tras"], {
                            "turno_id": turn_id, "hora_traslado": now(),
                            "labor_origen": origin, "labor_destino": destination,
                            "cantidad_personas": amount, "motivo": reason,
                            "registrado_por": user_id, "creado_en": now(),
                        })
                        st.rerun()
            st.dataframe(frame(T["tras"], {"turno_id": turn_id}), width="stretch", hide_index=True)

elif role == "ASISTENTE" and page == "Cerrar turno":
    st.title("Cerrar turno")
    turn_id = choose_turn(["CONFIRMADO"], user_id)
    if turn_id is None:
        st.info("No hay turnos disponibles.")
    else:
        personal = frame(T["personal"], {"turno_id": turn_id})
        turn = frame(T["turnos"], {"id": turn_id}).iloc[0]
        with st.form("close"):
            end = st.time_input("Hora final real", time.fromisoformat(str(turn["hora_programada_fin"])[:5]))
            washed = st.number_input("Jabas lavadas", 0, 1000000, 0, step=100)
            observation = st.text_area("Observación de cierre")
            if st.form_submit_button("Enviar cierre", type="primary"):
                end_dt = datetime.combine(date.fromisoformat(str(turn["fecha"])), end).astimezone()
                start_clock = time.fromisoformat(str(turn["hora_programada_inicio"])[:5])
                start_dt = datetime.combine(date.fromisoformat(str(turn["fecha"])), start_clock).astimezone()
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
                total_hours_person = 0.0
                for _, item in personal.iterrows():
                    initial = pd.to_datetime(item["hora_inicio"]).to_pydatetime()
                    worked_minutes = minutes_between(initial, end_dt)
                    break_minutes = 45 if worked_minutes > 360 else 0
                    effective_hours = max(worked_minutes - break_minutes, 0) / 60
                    hours_person = effective_hours * int(item["cantidad_personas"])
                    total_hours_person += hours_person
                    edit(T["personal"], {
                        "hora_fin": end_dt.isoformat(timespec="seconds"),
                        "minutos_refrigerio": break_minutes,
                        "horas_efectivas": effective_hours, "horas_persona": hours_person,
                    }, {"id": str(item["id"])})
                productivity = washed / total_hours_person if total_hours_person else 0
                payload = {"turno_id": turn_id, "jabas_lavadas": washed,
                           "horas_persona": total_hours_person, "productividad": productivity,
                           "actualizado_en": now()}
                if get(T["prod"], {"turno_id": turn_id}):
                    edit(T["prod"], payload, {"turno_id": turn_id})
                else:
                    payload["creado_en"] = now()
                    add(T["prod"], payload)
                edit(T["turnos"], {"estado": "CERRADO", "hora_real_fin": end_dt.isoformat(timespec="seconds"),
                                    "observacion_cierre": observation, "cerrado_en": now(), "actualizado_en": now()},
                     {"id": turn_id})
                audit("turnos", turn_id, "estado", "CONFIRMADO", "CERRADO",
                      f"Jabas lavadas: {washed}", user_id)
                st.success("Cierre enviado al supervisor.")

elif role == "SUPERVISOR" and page == "Panel":
    st.title("Panel supervisor")
    data = frame(T["turnos"])
    for column, status in zip(st.columns(4), ["ABIERTO", "CONFIRMADO", "CERRADO", "VALIDADO"]):
        column.metric(status, int((data["estado"] == status).sum()) if not data.empty else 0)

elif role == "SUPERVISOR" and page == "Confirmar apertura":
    st.title("Confirmar apertura")
    turn_id = choose_turn(["ABIERTO"])
    if turn_id is None:
        st.info("No hay aperturas pendientes.")
    else:
        st.dataframe(frame(T["personal"], {"turno_id": turn_id}), width="stretch", hide_index=True)
        if st.button("Confirmar inicio", type="primary"):
            edit(T["turnos"], {"estado": "CONFIRMADO", "supervisor_id": user_id,
                                "hora_real_inicio": now(), "confirmado_en": now(), "actualizado_en": now()},
                 {"id": turn_id})
            audit("turnos", turn_id, "estado", "ABIERTO", "CONFIRMADO",
                  "Apertura validada", user_id)
            st.rerun()

elif role == "SUPERVISOR" and page == "Seguimiento":
    st.title("Seguimiento")
    turn_id = choose_turn(["CONFIRMADO", "CERRADO", "VALIDADO"])
    if turn_id is not None:
        for title, table in [("Incidencias", "inc"), ("Traslados", "tras"), ("Auditoría", "audit")]:
            st.subheader(title)
            st.dataframe(frame(T[table], {"turno_id": turn_id}) if table != "audit" else frame(T[table], {"registro_id": turn_id}),
                         width="stretch", hide_index=True)

elif role == "SUPERVISOR" and page == "Validar cierre":
    st.title("Validar cierre")
    turn_id = choose_turn(["CERRADO"])
    if turn_id is None:
        st.info("No hay cierres pendientes.")
    else:
        production = frame(T["prod"], {"turno_id": turn_id}).iloc[0]
        old = int(production["jabas_lavadas"])
        with st.form("validate"):
            new = st.number_input("Jabas lavadas", 0, 1000000, old)
            reason = st.text_area("Motivo obligatorio si corrige")
            if st.form_submit_button("Validar", type="primary"):
                if new != old and not reason.strip():
                    st.error("Debe indicar el motivo.")
                else:
                    hours_person = float(production["horas_persona"] or 0)
                    if new != old:
                        edit(T["prod"], {"jabas_lavadas": new,
                                         "productividad": new / hours_person if hours_person else 0,
                                         "actualizado_en": now()}, {"turno_id": turn_id})
                        audit("produccion_turno", str(production["id"]), "jabas_lavadas", old, new, reason, user_id)
                    edit(T["turnos"], {"estado": "VALIDADO", "supervisor_id": user_id,
                                        "validado_en": now(), "actualizado_en": now()}, {"id": turn_id})
                    audit("turnos", turn_id, "estado", "CERRADO", "VALIDADO",
                          "Cierre validado", user_id)
                    st.rerun()

elif role == "JEFATURA":
    st.title(page)
    table = {"Panel": "turnos", "Turnos": "turnos", "Incidencias": "inc", "Auditoría": "audit"}[page]
    data = frame(T[table])
    if data.empty:
        st.info("Sin datos.")
    else:
        st.dataframe(data, width="stretch", hide_index=True)

st.divider()
st.caption("Piloto Lavado de Jabas · Supabase · Refrigerio automático: 45 min en jornadas mayores a 6 horas")
