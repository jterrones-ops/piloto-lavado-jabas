from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import hashlib
import hmac

import bcrypt
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
LIMA = ZoneInfo("America/Lima")


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
    return datetime.now(LIMA).isoformat(timespec="seconds")


def timestamp(day, clock):
    return datetime.combine(day, clock, tzinfo=LIMA).isoformat(timespec="seconds")


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


def password_is_valid(password, stored_hash):
    stored_hash = str(stored_hash or "").strip()
    if not password or not stored_hash:
        return False
    try:
        if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        if len(stored_hash) == 64:
            calculated = hashlib.sha256(password.encode("utf-8")).hexdigest()
            return hmac.compare_digest(calculated.lower(), stored_hash.lower())
    except (ValueError, TypeError):
        return False
    return False


all_users = frame(T["users"], order="nombre")
users = all_users.copy()
if not users.empty and "activo" in users:
    users = users[users["activo"].fillna(False).astype(bool)]
user_by_id = {str(row["id"]): row["nombre"] for _, row in users.iterrows()} if not users.empty else {}

if not st.session_state.get("authenticated"):
    st.markdown("""
    <style>
    [data-testid="stSidebar"] {display: none;}
    .block-container {max-width: 560px; padding-top: 4rem;}
    </style>
    """, unsafe_allow_html=True)
    st.title("Control de Operaciones Logísticas")
    st.subheader("🧼 Lavado de jabas")
    st.caption("Ingresa con tu cuenta para acceder a la operación asignada.")
    with st.form("login"):
        login_user = st.text_input("Usuario", placeholder="Escribe tu usuario")
        login_password = st.text_input("Contraseña", type="password", placeholder="Escribe tu contraseña")
        login_button = st.form_submit_button("INGRESAR", type="primary", use_container_width=True)
        if login_button:
            match = users[users["usuario"].astype(str).str.lower() == login_user.strip().lower()] if not users.empty else pd.DataFrame()
            if match.empty or not password_is_valid(login_password, match.iloc[0]["clave_hash"]):
                st.error("Usuario o contraseña incorrectos.")
            else:
                account = match.iloc[0]
                st.session_state["authenticated"] = True
                st.session_state["user_id"] = str(account["id"])
                st.rerun()
    st.info("Operación disponible: Lavado de jabas")
    st.stop()

current = users[users["id"].astype(str) == str(st.session_state.get("user_id"))]
if current.empty:
    st.session_state.clear()
    st.warning("Tu acceso ya no está activo. Vuelve a ingresar.")
    st.rerun()

user_row = current.iloc[0]
user_id = str(user_row["id"])
user_name = str(user_row["nombre"])
role = str(user_row["rol"]).upper()

st.sidebar.title("🧼 Lavado de jabas")
st.sidebar.write(f"**{user_name}**")
st.sidebar.caption(f"{role.title()} · Lavado de jabas")
if st.sidebar.button("Cerrar sesión", use_container_width=True):
    st.session_state.clear()
    st.rerun()

menus = {
    "ASISTENTE": ["Inicio", "Abrir turno", "Operación", "Cerrar turno"],
    "SUPERVISOR": ["Panel", "Confirmar apertura", "Seguimiento", "Validar cierre"],
    "JEFATURA": ["Panel", "Turnos", "Incidencias", "Auditoría", "Usuarios y accesos"],
}
if role not in menus:
    st.error("El rol de este usuario no está configurado correctamente.")
    st.stop()
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
                start = c1.time_input("Inicio", datetime.now(LIMA).time().replace(second=0, microsecond=0))
                close_now = c2.checkbox("Cerrar ahora")
                end = st.time_input(
                    "Fin",
                    datetime.now(LIMA).time().replace(second=0, microsecond=0),
                    help="Esta hora solo se guardará si marcas 'Cerrar ahora'.",
                )
                description = st.text_area("Descripción")
                if st.form_submit_button("Guardar"):
                    start_dt = datetime.combine(date.today(), start, tzinfo=LIMA)
                    end_dt = datetime.combine(date.today(), end, tzinfo=LIMA) if close_now else None
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
            incidents = frame(T["inc"], {"turno_id": turn_id})
            if incidents.empty:
                st.info("Sin incidencias registradas.")
            else:
                st.dataframe(incidents, width="stretch", hide_index=True)
                open_incidents = incidents[incidents["estado"] == "ABIERTA"]
                if not open_incidents.empty:
                    st.subheader("Cerrar incidencia abierta")
                    incident_options = {
                        f"{row['tipo']} | Inicio: {pd.to_datetime(row['hora_inicio']).strftime('%H:%M')}": str(row["id"])
                        for _, row in open_incidents.iterrows()
                    }
                    selected_incident = st.selectbox("Incidencia", list(incident_options))
                    closing_time = st.time_input(
                        "Hora final de la incidencia",
                        datetime.now(LIMA).time().replace(second=0, microsecond=0),
                        key="incident_closing_time",
                    )
                    if st.button("Cerrar incidencia", type="primary", use_container_width=True):
                        incident_id = incident_options[selected_incident]
                        incident_row = open_incidents[open_incidents["id"].astype(str) == incident_id].iloc[0]
                        start_dt = pd.to_datetime(incident_row["hora_inicio"]).to_pydatetime()
                        end_dt = datetime.combine(start_dt.date(), closing_time, tzinfo=LIMA)
                        if end_dt <= start_dt:
                            end_dt += timedelta(days=1)
                        duration = minutes_between(start_dt, end_dt)
                        edit(T["inc"], {
                            "hora_fin": end_dt.isoformat(timespec="seconds"),
                            "duracion_minutos": duration,
                            "estado": "CERRADA",
                        }, {"id": incident_id})
                        audit("incidencias", incident_id, "estado", "ABIERTA", "CERRADA",
                              f"Duración: {duration} minutos", user_id)
                        st.rerun()
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
                end_dt = datetime.combine(date.fromisoformat(str(turn["fecha"])), end, tzinfo=LIMA)
                start_clock = time.fromisoformat(str(turn["hora_programada_inicio"])[:5])
                start_dt = datetime.combine(date.fromisoformat(str(turn["fecha"])), start_clock, tzinfo=LIMA)
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

elif role == "JEFATURA" and page == "Usuarios y accesos":
    st.title("Usuarios y accesos")
    st.caption("Jefatura define quién puede ingresar y con qué rol. Operación activa: Lavado de jabas.")
    display = all_users[["nombre", "usuario", "rol", "activo"]].copy()
    display["operación"] = "Lavado de jabas"
    st.dataframe(display, width="stretch", hide_index=True)
    if not all_users.empty:
        user_options = {f"{row['nombre']} · {row['usuario']}": str(row["id"]) for _, row in all_users.iterrows()}
        selected_label = st.selectbox("Usuario a configurar", list(user_options))
        selected_id = user_options[selected_label]
        selected = all_users[all_users["id"].astype(str) == selected_id].iloc[0]
        roles = ["ASISTENTE", "SUPERVISOR", "JEFATURA"]
        selected_role = st.selectbox("Rol", roles, index=roles.index(str(selected["rol"]).upper()))
        selected_active = st.checkbox("Acceso activo", value=bool(selected["activo"]))
        st.text_input("Operación asignada", "Lavado de jabas", disabled=True)
        if st.button("Guardar acceso", type="primary", use_container_width=True):
            if selected_id == user_id and not selected_active:
                st.error("No puedes desactivar tu propia cuenta mientras estás conectado.")
            else:
                old_role = str(selected["rol"]).upper()
                old_active = bool(selected["activo"])
                edit(T["users"], {"rol": selected_role, "activo": selected_active}, {"id": selected_id})
                if old_role != selected_role:
                    audit("app_users", selected_id, "rol", old_role, selected_role,
                          "Configuración de acceso por Jefatura", user_id)
                if old_active != selected_active:
                    audit("app_users", selected_id, "activo", old_active, selected_active,
                          "Configuración de acceso por Jefatura", user_id)
                st.success("Acceso actualizado.")
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
