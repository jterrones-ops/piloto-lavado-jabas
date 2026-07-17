from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import hashlib
import hmac
import json
from uuid import uuid4

import bcrypt
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(
    page_title="Piloto Lavado de Jabas",
    page_icon="🧼",
    layout="wide",
    initial_sidebar_state="collapsed",
)

T = {
    "users": "app_users", "turnos": "turnos", "personal": "personal_labor",
    "inc": "incidencias", "tras": "traslados_personal",
    "prod": "produccion_turno", "audit": "auditoria", "config": "configuracion",
}
LABORES = ["Lavado", "Secado", "Limpieza de lámina burbupack"]
INCIDENCIAS = ["Falta de agua", "Falla de equipo", "Falta de energía", "Falta de jabas",
               "Falta de personal", "Limpieza del área", "Desperfecto mecánico",
               "Acumulación de jabas", "Otro"]
OPERACIONES = [
    {
        "icon": "🧼", "name": "Lavado de jabas", "enabled": True,
        "responsables": ["Asistente · Rafael Zapata"],
        "labores": ["Lavado", "Secado", "Limpieza de lámina burbupack"],
    },
    {
        "icon": "📦", "name": "Distribución de jabas", "enabled": True,
        "responsables": ["Supervisor · Luis Macea"],
        "labores": ["Colocación de hilo nylon", "Colocación de lámina", "Colocación de burbupack",
                    "Estiba", "Desestiba en puntos de cosecha"],
    },
    {
        "icon": "💡", "name": "Luminarias", "enabled": True,
        "responsables": ["Supervisor · Por definir"],
        "labores": ["Carga", "Distribución", "Recojo"],
    },
    {
        "icon": "🚜", "name": "Acarreo de fruta", "enabled": True,
        "responsables": ["Supervisor · Enisban Calle", "Supervisor · Juan Cruz"],
        "labores": ["Lote → Acopio", "Acopio → Packing"],
    },
    {
        "icon": "🏭", "name": "Acopios", "enabled": True,
        "responsables": ["Supervisor · Andrés Villegas"],
        "labores": ["Asistente (acopiador)", "Estibadores", "Montacarguistas"],
    },
]
SHIFT_SCHEDULES = {
    "Lavado de jabas": [
        {"label": "Mañana", "code": "DIA", "start": "06:00", "end": "18:00"},
        {"label": "Tarde", "code": "NOCHE", "start": "18:00", "end": "06:00"},
    ],
    "Distribución de jabas": [
        {"label": "Mañana", "code": "DIA", "start": "06:00", "end": "14:45"},
        {"label": "Tarde", "code": "DIA", "start": "15:00", "end": "23:45"},
        {"label": "Noche", "code": "NOCHE", "start": "23:45", "end": "06:00"},
    ],
    "Luminarias": [
        {"label": "Mañana", "code": "DIA", "start": "06:00", "end": "14:45"},
        {"label": "Tarde", "code": "DIA", "start": "14:00", "end": "22:45"},
        {"label": "Noche", "code": "NOCHE", "start": "22:00", "end": "06:45"},
    ],
    "Acarreo de fruta": [
        {"label": "Mañana", "code": "DIA", "start": "03:00", "end": "11:45"},
        {"label": "Día", "code": "DIA", "start": "06:00", "end": "14:45"},
        {"label": "Noche", "code": "NOCHE", "start": "16:00", "end": "00:45"},
    ],
    "Acopios": [
        {"label": "Mañana", "code": "DIA", "start": "03:00", "end": "11:45"},
        {"label": "Día", "code": "DIA", "start": "06:00", "end": "14:45"},
        {"label": "Noche", "code": "NOCHE", "start": "16:00", "end": "00:45"},
    ],
}
ACOPIOS = {
    "G3-G4": {"capacidad": 20000, "tipo": "Mecanizado"},
    "F1-F2": {"capacidad": 20000, "tipo": "Mecanizado"},
    "F4-F5": {"capacidad": 20000, "tipo": "Mecanizado"},
    "E4-E5": {"capacidad": 20000, "tipo": "Mecanizado"},
    "D2-D1": {"capacidad": 20000, "tipo": "Mecanizado"},
    "D4-D5": {"capacidad": 20000, "tipo": "Mecanizado"},
    "B2-B3": {"capacidad": 20000, "tipo": "Mecanizado"},
    "G14-H14": {"capacidad": 15000, "tipo": "Manual"},
    "E14-F13": {"capacidad": 20000, "tipo": "Mecanizado"},
    "D15": {"capacidad": 20000, "tipo": "Mecanizado"},
    "B12": {"capacidad": 20000, "tipo": "Mecanizado"},
    "PK2": {"capacidad": 20000, "tipo": "Mecanizado"},
    "B7-B6": {"capacidad": 15000, "tipo": "Manual"},
    "C14-C15": {"capacidad": 15000, "tipo": "Manual"},
    "A13-A12": {"capacidad": 15000, "tipo": "Manual"},
    "D12-D13": {"capacidad": 15000, "tipo": "Manual"},
}
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


def acopio_trips(turn_id):
    prefix = f"viaje_acopio:{turn_id}:"
    trips = []
    for row in get(T["config"], order=None):
        key = str(row.get("clave", ""))
        if not key.startswith(prefix):
            continue
        try:
            trip = json.loads(row.get("valor") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        trip["_key"] = key
        trips.append(trip)
    return sorted(trips, key=lambda item: item.get("salida", ""), reverse=True)


def save_acopio_trip(turn_id, trip):
    key = f"viaje_acopio:{turn_id}:{uuid4()}"
    add(T["config"], {
        "clave": key,
        "valor": json.dumps(trip, ensure_ascii=False),
        "descripcion": "Registro piloto de viaje desde punto de acopio",
        "actualizado_en": now(),
    })
    return key


def update_acopio_trip(key, trip):
    edit(T["config"], {
        "valor": json.dumps(trip, ensure_ascii=False),
        "actualizado_en": now(),
    }, {"clave": key})


def turn_acopio(turn_id):
    turns = frame(T["turnos"], {"id": turn_id})
    if turns.empty:
        return None
    observation = str(turns.iloc[0].get("observacion_apertura") or "")
    marker = "ACOPIO: ubicación="
    if marker not in observation:
        return None
    location = observation.split(marker, 1)[1].split(",", 1)[0].strip()
    return location if location in ACOPIOS else None


def assigned_operation(account_id):
    rows = get(T["config"], {"clave": f"operacion_usuario:{account_id}"}, order=None)
    return rows[0]["valor"] if rows else "Lavado de jabas"


def save_assigned_operation(account_id, operation):
    sb.table(T["config"]).upsert({
        "clave": f"operacion_usuario:{account_id}",
        "valor": operation,
        "descripcion": "Operación principal asignada al usuario",
        "actualizado_en": now(),
    }, on_conflict="clave").execute()


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


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


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
    st.subheader("Ingreso al sistema")
    st.caption("Identifícate para consultar las operaciones disponibles.")
    with st.form("login"):
        login_user = st.text_input(
            "Usuario o nombre",
            placeholder="Ejemplo: asistente.piloto o Asistente Piloto",
        )
        login_password = st.text_input("Contraseña", type="password", placeholder="Escribe tu contraseña")
        login_button = st.form_submit_button("INGRESAR", type="primary", use_container_width=True)
        if login_button:
            entered_identity = login_user.strip().lower()
            matches = users[
                (users["usuario"].astype(str).str.lower() == entered_identity)
                | (users["nombre"].astype(str).str.lower() == entered_identity)
            ] if not users.empty else pd.DataFrame()
            account = None
            for _, candidate in matches.iterrows():
                if password_is_valid(login_password, candidate["clave_hash"]):
                    account = candidate
                    break
            if account is None:
                st.error("Usuario o contraseña incorrectos.")
            else:
                st.session_state["authenticated"] = True
                st.session_state["user_id"] = str(account["id"])
                st.rerun()
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
account_role = role
user_operation = assigned_operation(user_id)

st.sidebar.title("Operaciones Logísticas")
st.sidebar.write(f"**{user_name}**")
st.sidebar.caption(role.title())
if st.sidebar.button("Cerrar sesión", use_container_width=True):
    st.session_state.clear()
    st.rerun()

if role in ("ASISTENTE", "SUPERVISOR"):
    st.session_state["selected_operation"] = user_operation

if not st.session_state.get("selected_operation"):
    st.title("Inicio")
    st.write(f"Bienvenido, **{user_name}**. Selecciona una operación para continuar.")
    for row_start in range(0, len(OPERACIONES), 2):
        columns = st.columns(2)
        for column, operation in zip(columns, OPERACIONES[row_start:row_start + 2]):
            icon = operation["icon"]
            name = operation["name"]
            enabled = operation["enabled"]
            with column.container(border=True):
                st.subheader(f"{icon} {name}")
                for responsible in operation["responsables"]:
                    st.caption(responsible)
                st.markdown("**Labores**")
                for task in operation["labores"]:
                    st.markdown(f"- {task}")
                if enabled:
                    st.success("Disponible")
                    if st.button("Ingresar", key=f"open_{row_start}_{name}",
                                 type="primary", use_container_width=True):
                        st.session_state["selected_operation"] = name
                        st.rerun()
                else:
                    st.caption("En preparación")
                    st.button("Próximamente", key=f"disabled_{row_start}_{name}",
                              disabled=True, use_container_width=True)
    st.stop()

st.sidebar.caption(f"Operación: {st.session_state['selected_operation']}")
if account_role == "JEFATURA" and st.sidebar.button("Cambiar operación", use_container_width=True):
    st.session_state.pop("selected_operation", None)
    st.rerun()

selected_operation = st.session_state["selected_operation"]
operation_config = next(operation for operation in OPERACIONES if operation["name"] == selected_operation)
LABORES = operation_config["labores"]

if account_role == "JEFATURA":
    test_modes = {
        "Jefatura": "JEFATURA",
        "Asistente (pruebas)": "ASISTENTE",
        "Supervisor (pruebas)": "SUPERVISOR",
    }
    selected_mode = st.sidebar.selectbox("Ver sistema como", list(test_modes), key="management_test_mode")
    role = test_modes[selected_mode]
    if role != "JEFATURA":
        st.sidebar.info(f"Modo de pruebas: {selected_mode}")

menus = {
    "ASISTENTE": ["Inicio", "Abrir turno", "Operación", "Cerrar turno"],
    "SUPERVISOR": ["Panel", "Confirmar apertura", "Seguimiento", "Validar cierre"],
    "JEFATURA": ["Panel", "Turnos", "Incidencias", "Auditoría", "Usuarios y accesos"],
}
if role not in menus:
    st.error("El rol de este usuario no está configurado correctamente.")
    st.stop()
page = st.selectbox(
    "Ir a",
    menus[role],
    key=f"main_navigation_{role}",
    help="Selecciona la sección que deseas abrir.",
)
st.sidebar.caption("Base central: Supabase")


def turn_label(row):
    assistant = user_by_id.get(str(row["asistente_id"]), "Sin asignar")
    shift = shift_label_for_row(row)
    status = STATUS_LABELS.get(row["estado"], row["estado"])
    return f"{row['fecha']} | {shift} | {assistant} | {status}"


def filter_current_operation(data):
    if data.empty or "responsable_operacion" not in data:
        return data
    operation_names = [operation["name"] for operation in OPERACIONES]
    values = data["responsable_operacion"].fillna("").astype(str)
    if selected_operation == "Lavado de jabas":
        return data[(values == selected_operation) | (~values.isin(operation_names))]
    return data[values == selected_operation]


STATUS_LABELS = {
    "ABIERTO": "Esperando supervisor",
    "CONFIRMADO": "En ejecución",
    "CERRADO": "Cierre pendiente",
    "VALIDADO": "Finalizado",
}

RESULT_LABELS = {
    "Lavado de jabas": "Jabas lavadas",
    "Distribución de jabas": "Jabas distribuidas",
    "Luminarias": "Luminarias gestionadas",
    "Acarreo de fruta": "Movimientos realizados",
    "Acopios": "Jabas atendidas",
}


def shift_label_for_row(row):
    start = str(row.get("hora_programada_inicio", ""))[:5]
    end = str(row.get("hora_programada_fin", ""))[:5]
    for schedule in SHIFT_SCHEDULES[selected_operation]:
        if schedule["start"] == start and schedule["end"] == end:
            return schedule["label"]
    return str(row.get("tipo_turno", "Turno")).title()


def incident_summary(data):
    if data.empty:
        return data
    columns = ["tipo", "hora_inicio", "hora_fin", "duracion_minutos", "estado"]
    view = data[[column for column in columns if column in data]].copy()
    return view.rename(columns={
        "tipo": "Tipo", "hora_inicio": "Inicio", "hora_fin": "Fin",
        "duracion_minutos": "Duración (min)", "estado": "Estado",
    })


def transfer_summary(data):
    if data.empty:
        return data
    columns = ["hora_traslado", "labor_origen", "labor_destino", "cantidad_personas", "motivo"]
    view = data[[column for column in columns if column in data]].copy()
    return view.rename(columns={
        "hora_traslado": "Hora", "labor_origen": "Origen", "labor_destino": "Destino",
        "cantidad_personas": "Personas", "motivo": "Motivo",
    })


def display_clock(value, fallback=None):
    if value is None or pd.isna(value) or str(value).strip() in ("", "None", "NaT"):
        return fallback or "Pendiente"
    text = str(value)
    if "T" not in text and len(text) >= 5:
        return text[:5]
    try:
        return pd.to_datetime(value).strftime("%H:%M")
    except (TypeError, ValueError):
        return text[:5]


def turn_summary(data):
    rows = []
    for _, item in data.head(30).iterrows():
        personal = frame(T["personal"], {"turno_id": str(item["id"])})
        if personal.empty:
            personal = pd.DataFrame([{"labor": "Sin distribución", "cantidad_personas": 0,
                                      "hora_inicio": None, "hora_fin": None}])
        for _, detail in personal.iterrows():
            quantity = detail.get("cantidad_personas", 0)
            quantity = 0 if pd.isna(quantity) else int(quantity)
            rows.append({
                "Subproceso": detail.get("labor", "Sin distribución"),
                "Personal": quantity,
                "Estado": STATUS_LABELS.get(item["estado"], item["estado"]),
                "Hora inicio": display_clock(
                    detail.get("hora_inicio"), str(item.get("hora_programada_inicio", ""))[:5]
                ),
                "Hora final": display_clock(detail.get("hora_fin")),
            })
    return pd.DataFrame(rows)


def today_turns(data):
    if data.empty or "fecha" not in data:
        return data
    today_value = str(datetime.now(LIMA).date())
    return data[data["fecha"].astype(str) == today_value]


def render_daily_turn_table(data, key):
    today_value = datetime.now(LIMA).date()
    st.markdown(f"**Fecha: {today_value.strftime('%d/%m/%Y')}**")
    daily = today_turns(data)
    if daily.empty:
        st.info("No hay turnos registrados para hoy.")
        return
    daily = daily.copy()
    daily["_turno_visible"] = [shift_label_for_row(row) for _, row in daily.iterrows()]
    ordered_shifts = [item["label"] for item in SHIFT_SCHEDULES[selected_operation]]
    available_shifts = [shift for shift in ordered_shifts if shift in set(daily["_turno_visible"])]
    for shift in daily["_turno_visible"].dropna().unique():
        if shift not in available_shifts:
            available_shifts.append(shift)
    selected_shift = st.selectbox("Turno", available_shifts, key=key)
    selected_rows = daily[daily["_turno_visible"] == selected_shift].drop(columns=["_turno_visible"])
    st.dataframe(turn_summary(selected_rows), width="stretch", hide_index=True)


def choose_turn(statuses, assistant_id=None):
    data = filter_current_operation(frame(T["turnos"]))
    if not data.empty:
        data = data[data["estado"].isin(statuses)]
    if assistant_id and not data.empty:
        data = data[data["asistente_id"].astype(str) == str(assistant_id)]
    if data.empty:
        return None
    mapping = {turn_label(row): str(row["id"]) for _, row in data.iterrows()}
    return mapping[st.selectbox("Turno", list(mapping))]


if role == "ASISTENTE" and page == "Inicio":
    st.title(selected_operation)
    data = filter_current_operation(frame(T["turnos"], {"asistente_id": user_id}))
    render_daily_turn_table(data, "assistant_daily_shift")

elif role == "ASISTENTE" and page == "Abrir turno":
    st.title("Abrir turno")
    opening_result_key = f"opening_result_{user_id}_{selected_operation}"
    if st.session_state.get(opening_result_key):
        result = st.session_state[opening_result_key]
        st.success("Apertura enviada correctamente al supervisor.")
        st.info(
            f"Fecha: {result['fecha']} · Turno: {result['turno']} · "
            f"Estado: {STATUS_LABELS.get(result['estado'], result['estado'])}"
        )
        st.warning("No es necesario volver a enviarla. Espera la confirmación del supervisor.")
        if st.button("Registrar una apertura de otra fecha", use_container_width=True):
            st.session_state.pop(opening_result_key, None)
            st.rerun()
        st.stop()
    with st.form("open"):
        c1, c2 = st.columns(2)
        day = c1.date_input("Fecha", date.today())
        schedules = SHIFT_SCHEDULES[selected_operation]
        schedule_by_label = {item["label"]: item for item in schedules}
        shift = c2.selectbox("Turno", list(schedule_by_label))
        selected_schedule = schedule_by_label[shift]
        c1, c2 = st.columns(2)
        start = c1.time_input("Inicio", time.fromisoformat(selected_schedule["start"]), disabled=True)
        end = c2.time_input("Fin programado", time.fromisoformat(selected_schedule["end"]), disabled=True)
        opening_labors = LABORES
        operation_detail = ""
        if selected_operation == "Acopios":
            st.markdown("#### Punto de acopio")
            selected_acopio = st.selectbox("Ubicación", list(ACOPIOS))
            acopio_data = ACOPIOS[selected_acopio]
            c1, c2 = st.columns(2)
            c1.metric("Tipo", acopio_data["tipo"])
            c2.metric("Capacidad", f"{acopio_data['capacidad']:,} jabas")
            opening_labors = ["Asistente (acopiador)", "Estibadores"]
            if acopio_data["tipo"] == "Mecanizado":
                opening_labors.append("Montacarguistas")
            operation_detail = (
                f"ACOPIO: ubicación={selected_acopio}, tipo={acopio_data['tipo']}, "
                f"capacidad={acopio_data['capacidad']} jabas."
            )
        st.markdown("#### Personal por labor o integrante")
        default_quantities = [10, 4, 2] if selected_operation == "Lavado de jabas" else [0] * len(opening_labors)
        quantities = [
            st.number_input(labor, 0, 200, value)
            for labor, value in zip(opening_labors, default_quantities)
        ]
        if selected_operation == "Acarreo de fruta":
            st.markdown("#### Equipos — Lote → Acopio")
            c1, c2, c3 = st.columns(3)
            la_motofurgones = c1.number_input("Motofurgones", 0, 100, 0, key="la_motofurgones")
            la_personal_moto = c2.number_input("Personal por motofurgón", 0, 10, 1, key="la_personal_moto")
            la_tractores = c3.number_input("Tractores", 0, 100, 0, key="la_tractores")
            c1, c2 = st.columns(2)
            la_personal_tractor = c1.number_input("Personal por tractor", 0, 10, 1, key="la_personal_tractor")
            la_carretas = c2.number_input("Carretas", 0, 200, 0, key="la_carretas")
            st.markdown("#### Equipos — Acopio → Packing")
            c1, c2, c3 = st.columns(3)
            ap_tractores = c1.number_input("Tractores ", 0, 100, 0, key="ap_tractores")
            ap_personal_tractor = c2.number_input("Personal por tractor ", 0, 10, 1, key="ap_personal_tractor")
            ap_carretas = c3.number_input("Carretas ", 0, 200, 0, key="ap_carretas")
            exceptional_moto = st.checkbox("Uso excepcional de motofurgón en Acopio → Packing")
            ap_motofurgones = ap_personal_moto = 0
            exceptional_reason = ""
            if exceptional_moto:
                c1, c2 = st.columns(2)
                ap_motofurgones = c1.number_input("Motofurgones excepcionales", 1, 100, 1)
                ap_personal_moto = c2.number_input("Personal por motofurgón excepcional", 1, 10, 1)
                exceptional_reason = st.text_input("Motivo de la excepción")
            operation_detail = (
                f"RECURSOS Lote-Acopio: motofurgones={la_motofurgones}, personal/motofurgón={la_personal_moto}, "
                f"tractores={la_tractores}, personal/tractor={la_personal_tractor}, carretas={la_carretas}. "
                f"Acopio-Packing: tractores={ap_tractores}, personal/tractor={ap_personal_tractor}, "
                f"carretas={ap_carretas}, motofurgones_excepcionales={ap_motofurgones}, "
                f"personal/motofurgón={ap_personal_moto}, motivo={exceptional_reason or 'No aplica'}."
            )
        observation = st.text_area("Observación")
        if st.form_submit_button("Enviar al supervisor", type="primary", use_container_width=True):
            try:
                shift_code = selected_schedule["code"]
                existing_df = filter_current_operation(pd.DataFrame(get(T["turnos"], {
                    "fecha": str(day), "tipo_turno": shift_code, "asistente_id": user_id,
                })))
                if not existing_df.empty:
                    existing_df = existing_df[
                        existing_df["hora_programada_inicio"].astype(str).str[:5] == selected_schedule["start"]
                    ]
                existing = existing_df.to_dict("records")
                if existing:
                    st.session_state[opening_result_key] = {
                        "fecha": str(day), "turno": shift, "estado": existing[0]["estado"],
                    }
                else:
                    row = add(T["turnos"], {
                        "fecha": str(day), "tipo_turno": shift_code,
                        "hora_programada_inicio": start.strftime("%H:%M"),
                        "hora_programada_fin": end.strftime("%H:%M"),
                        "asistente_id": user_id, "responsable_operacion": selected_operation,
                        "estado": "ABIERTO",
                        "observacion_apertura": "\n".join(filter(None, [observation, operation_detail])),
                        "creado_en": now(), "actualizado_en": now(),
                    })
                    turn_id = row["id"]
                    add(T["personal"], [{
                        "turno_id": turn_id, "labor": labor, "cantidad_personas": quantity,
                        "hora_inicio": timestamp(day, start), "minutos_refrigerio": 45,
                        "creado_en": now(),
                    } for labor, quantity in zip(opening_labors, quantities)])
                    audit("turnos", turn_id, "estado", None, "ABIERTO",
                          f"Personal inicial: {sum(quantities)}", user_id)
                    st.session_state[opening_result_key] = {
                        "fecha": str(day), "turno": shift, "estado": "ABIERTO",
                    }
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo crear el turno: {getattr(e, 'message', None) or str(e)}")

elif role == "ASISTENTE" and page == "Operación":
    st.title("Operación en curso")
    turn_id = choose_turn(["CONFIRMADO"], user_id)
    if turn_id is None:
        st.info("No tienes turnos en ejecución.")
    else:
        tab_names = ["Incidencias", "Traslado interno"]
        if selected_operation == "Acopios":
            tab_names.append("Viajes")
        operation_tabs = st.tabs(tab_names)
        incident_tab, transfer_tab = operation_tabs[:2]
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
                st.dataframe(incident_summary(incidents), width="stretch", hide_index=True)
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
            transfers = frame(T["tras"], {"turno_id": turn_id})
            if transfers.empty:
                st.info("Sin traslados registrados.")
            else:
                st.dataframe(transfer_summary(transfers), width="stretch", hide_index=True)

        if selected_operation == "Acopios":
            trip_tab = operation_tabs[2]
            with trip_tab:
                location = turn_acopio(turn_id)
                if location is None:
                    st.warning("Este turno no tiene un punto de acopio asociado. Selecciónalo para la prueba.")
                    location = st.selectbox("Punto de acopio", list(ACOPIOS), key="trip_fallback_acopio")
                acopio_data = ACOPIOS[location]
                st.subheader(location)
                c1, c2 = st.columns(2)
                c1.metric("Tipo", acopio_data["tipo"])
                c2.metric("Capacidad", f"{acopio_data['capacidad']:,} jabas")

                trips = acopio_trips(turn_id)
                total_jabas = sum(int(item.get("total_jabas", 0) or 0) for item in trips)
                in_transit = [item for item in trips if item.get("estado") == "EN_TRANSITO"]
                c1, c2, c3 = st.columns(3)
                c1.metric("Viajes", len(trips))
                c2.metric("Jabas", f"{total_jabas:,}")
                c3.metric("En tránsito", len(in_transit))

                st.markdown("#### Registrar salida")
                with st.form("register_acopio_trip", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    unit = c1.text_input("Unidad", placeholder="Código o placa")
                    departure_time = c2.time_input(
                        "Hora de salida", datetime.now(LIMA).time().replace(second=0, microsecond=0)
                    )
                    st.caption("Agrega una fila por cada variedad transportada.")
                    varieties_editor = st.data_editor(
                        pd.DataFrame([{"Variedad": "", "Jabas": 0}]),
                        num_rows="dynamic",
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Variedad": st.column_config.TextColumn("Variedad", required=True),
                            "Jabas": st.column_config.NumberColumn("Jabas", min_value=0, step=1, required=True),
                        },
                        key="trip_varieties_editor",
                    )
                    register_trip = st.form_submit_button(
                        "Registrar salida", type="primary", use_container_width=True
                    )
                    if register_trip:
                        details = []
                        for _, detail in varieties_editor.iterrows():
                            variety = str(detail.get("Variedad") or "").strip()
                            amount = detail.get("Jabas", 0)
                            amount = 0 if pd.isna(amount) else int(amount)
                            if variety and amount > 0:
                                details.append({"variedad": variety, "jabas": amount})
                        normalized_unit = unit.strip().upper()
                        duplicate_unit = any(
                            str(item.get("unidad", "")).upper() == normalized_unit for item in in_transit
                        )
                        if not normalized_unit:
                            st.error("Ingresa la unidad que realiza el viaje.")
                        elif duplicate_unit:
                            st.error("Esa unidad ya tiene un viaje en tránsito.")
                        elif not details:
                            st.error("Agrega al menos una variedad con cantidad de jabas.")
                        else:
                            turn = frame(T["turnos"], {"id": turn_id}).iloc[0]
                            turn_day = date.fromisoformat(str(turn["fecha"]))
                            departure = datetime.combine(turn_day, departure_time, tzinfo=LIMA)
                            programmed_start = time.fromisoformat(str(turn["hora_programada_inicio"])[:5])
                            programmed_end = time.fromisoformat(str(turn["hora_programada_fin"])[:5])
                            if programmed_end <= programmed_start and departure_time < programmed_start:
                                departure += timedelta(days=1)
                            next_number = max([int(item.get("numero", 0) or 0) for item in trips] + [0]) + 1
                            trip = {
                                "numero": next_number, "acopio": location,
                                "tipo_acopio": acopio_data["tipo"], "capacidad": acopio_data["capacidad"],
                                "unidad": normalized_unit,
                                "salida": departure.isoformat(timespec="seconds"),
                                "llegada": None, "duracion_minutos": None,
                                "variedades": details,
                                "total_jabas": sum(item["jabas"] for item in details),
                                "estado": "EN_TRANSITO", "registrado_por": user_id,
                            }
                            save_acopio_trip(turn_id, trip)
                            audit("viajes_acopio", turn_id, "salida", None, next_number,
                                  f"Unidad {normalized_unit} · {location}", user_id)
                            st.rerun()

                if in_transit:
                    st.markdown("#### Registrar llegada")
                    trip_options = {
                        f"Viaje {item['numero']} · {item['unidad']} · salida {display_clock(item['salida'])}": item
                        for item in in_transit
                    }
                    selected_trip_label = st.selectbox("Viaje en tránsito", list(trip_options))
                    arrival_time = st.time_input(
                        "Hora de llegada", datetime.now(LIMA).time().replace(second=0, microsecond=0),
                        key="trip_arrival_time",
                    )
                    if st.button("Registrar llegada", type="primary", use_container_width=True):
                        selected_trip = dict(trip_options[selected_trip_label])
                        key = selected_trip.pop("_key")
                        departure = pd.to_datetime(selected_trip["salida"]).to_pydatetime()
                        arrival = datetime.combine(departure.date(), arrival_time, tzinfo=LIMA)
                        if arrival < departure:
                            arrival += timedelta(days=1)
                        selected_trip["llegada"] = arrival.isoformat(timespec="seconds")
                        selected_trip["duracion_minutos"] = minutes_between(departure, arrival)
                        selected_trip["estado"] = "FINALIZADO"
                        update_acopio_trip(key, selected_trip)
                        audit("viajes_acopio", turn_id, "llegada", None, selected_trip["numero"],
                              f"Duración: {selected_trip['duracion_minutos']} minutos", user_id)
                        st.rerun()

                if trips:
                    rows = []
                    for item in trips:
                        varieties = ", ".join(
                            f"{detail['variedad']}: {detail['jabas']}" for detail in item.get("variedades", [])
                        )
                        rows.append({
                            "Viaje": item.get("numero"), "Unidad": item.get("unidad"),
                            "Salida": display_clock(item.get("salida")),
                            "Llegada": display_clock(item.get("llegada")),
                            "Duración (min)": item.get("duracion_minutos") or "Pendiente",
                            "Jabas": item.get("total_jabas", 0), "Variedades": varieties,
                            "Estado": "En tránsito" if item.get("estado") == "EN_TRANSITO" else "Finalizado",
                        })
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

elif role == "ASISTENTE" and page == "Cerrar turno":
    st.title("Cerrar turno")
    turn_id = choose_turn(["CONFIRMADO"], user_id)
    if turn_id is None:
        st.info("No hay turnos disponibles.")
    else:
        personal = frame(T["personal"], {"turno_id": turn_id})
        turn = frame(T["turnos"], {"id": turn_id}).iloc[0]
        result_label = RESULT_LABELS[selected_operation]
        with st.form("close"):
            end = st.time_input("Hora final real", time.fromisoformat(str(turn["hora_programada_fin"])[:5]))
            result_quantity = st.number_input(result_label, 0, 1000000, 0, step=100)
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
                productivity = result_quantity / total_hours_person if total_hours_person else 0
                payload = {"turno_id": turn_id, "jabas_lavadas": result_quantity,
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
                      f"{result_label}: {result_quantity}", user_id)
                st.success("Cierre enviado al supervisor.")

elif role == "SUPERVISOR" and page == "Panel":
    st.title(f"Panel supervisor · {selected_operation}")
    data = today_turns(filter_current_operation(frame(T["turnos"])))
    metric_labels = [("ABIERTO", "Por confirmar"), ("CONFIRMADO", "En ejecución"),
                     ("CERRADO", "Cierres pendientes"), ("VALIDADO", "Finalizados")]
    for column, (status, label_text) in zip(st.columns(4), metric_labels):
        column.metric(label_text, int((data["estado"] == status).sum()) if not data.empty else 0)
    render_daily_turn_table(data, "supervisor_daily_shift")

elif role == "SUPERVISOR" and page == "Confirmar apertura":
    st.title("Confirmar apertura")
    turn_id = choose_turn(["ABIERTO"])
    if turn_id is None:
        st.info("No hay aperturas pendientes.")
    else:
        staff = frame(T["personal"], {"turno_id": turn_id})
        if not staff.empty:
            staff_view = staff[["labor", "cantidad_personas"]].rename(
                columns={"labor": "Labor o integrante", "cantidad_personas": "Personal"}
            )
            st.dataframe(staff_view, width="stretch", hide_index=True)
            st.metric("Personal total", int(staff["cantidad_personas"].fillna(0).sum()))
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
        incidents = frame(T["inc"], {"turno_id": turn_id})
        transfers = frame(T["tras"], {"turno_id": turn_id})
        st.subheader("Incidencias")
        st.dataframe(incident_summary(incidents), width="stretch", hide_index=True) if not incidents.empty else st.info("Sin incidencias.")
        st.subheader("Traslados")
        st.dataframe(transfer_summary(transfers), width="stretch", hide_index=True) if not transfers.empty else st.info("Sin traslados.")
        with st.expander("Ver detalle de auditoría"):
            audit_data = frame(T["audit"], {"registro_id": turn_id})
            st.dataframe(audit_data, width="stretch", hide_index=True) if not audit_data.empty else st.info("Sin movimientos de auditoría.")

elif role == "SUPERVISOR" and page == "Validar cierre":
    st.title("Validar cierre")
    turn_id = choose_turn(["CERRADO"])
    if turn_id is None:
        st.info("No hay cierres pendientes.")
    else:
        production = frame(T["prod"], {"turno_id": turn_id}).iloc[0]
        old = int(production["jabas_lavadas"])
        with st.form("validate"):
            result_label = RESULT_LABELS[selected_operation]
            new = st.number_input(result_label, 0, 1000000, old)
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
                        audit("produccion_turno", str(production["id"]), result_label, old, new, reason, user_id)
                    edit(T["turnos"], {"estado": "VALIDADO", "supervisor_id": user_id,
                                        "validado_en": now(), "actualizado_en": now()}, {"id": turn_id})
                    audit("turnos", turn_id, "estado", "CERRADO", "VALIDADO",
                          "Cierre validado", user_id)
                    st.rerun()

elif role == "JEFATURA" and page == "Usuarios y accesos":
    st.title("Usuarios y accesos")
    st.caption("Jefatura define quién puede ingresar, con qué rol y a qué operación será dirigido.")
    display = all_users[["nombre", "usuario", "rol", "activo"]].copy()
    display["operación"] = [
        "Acceso global" if str(row["rol"]).upper() == "JEFATURA" else assigned_operation(str(row["id"]))
        for _, row in all_users.iterrows()
    ]
    st.dataframe(display, width="stretch", hide_index=True)
    edit_tab, create_tab = st.tabs(["Configurar usuario", "Nuevo usuario"])
    with edit_tab:
        if not all_users.empty:
            user_options = {f"{row['nombre']} · {row['usuario']}": str(row["id"]) for _, row in all_users.iterrows()}
            selected_label = st.selectbox("Usuario a configurar", list(user_options))
            selected_id = user_options[selected_label]
            selected = all_users[all_users["id"].astype(str) == selected_id].iloc[0]
            roles = ["ASISTENTE", "SUPERVISOR", "JEFATURA"]
            selected_name = st.text_input("Nombre", str(selected["nombre"]), key="edit_name")
            selected_username = st.text_input("Usuario", str(selected["usuario"]), key="edit_username")
            selected_role = st.selectbox("Rol", roles, index=roles.index(str(selected["rol"]).upper()))
            selected_active = st.checkbox("Acceso activo", value=bool(selected["activo"]))
            operation_names = [operation["name"] for operation in OPERACIONES]
            current_operation = assigned_operation(selected_id)
            selected_operation = st.selectbox(
                "Operación principal",
                operation_names,
                index=operation_names.index(current_operation) if current_operation in operation_names else 0,
                disabled=selected_role == "JEFATURA",
            )
            if st.button("Guardar cambios", type="primary", use_container_width=True):
                duplicate = all_users[
                    (all_users["usuario"].astype(str).str.lower() == selected_username.strip().lower())
                    & (all_users["id"].astype(str) != selected_id)
                ]
                if not selected_name.strip() or not selected_username.strip():
                    st.error("Nombre y usuario son obligatorios.")
                elif not duplicate.empty:
                    st.error("Ese nombre de usuario ya existe.")
                elif selected_id == user_id and not selected_active:
                    st.error("No puedes desactivar tu propia cuenta mientras estás conectado.")
                else:
                    changes = {"nombre": selected_name.strip(), "usuario": selected_username.strip().lower(),
                               "rol": selected_role, "activo": selected_active}
                    edit(T["users"], changes, {"id": selected_id})
                    old_operation = assigned_operation(selected_id)
                    if selected_role != "JEFATURA":
                        save_assigned_operation(selected_id, selected_operation)
                    for field, old_value, new_value in [
                        ("nombre", selected["nombre"], changes["nombre"]),
                        ("usuario", selected["usuario"], changes["usuario"]),
                        ("rol", str(selected["rol"]).upper(), selected_role),
                        ("activo", bool(selected["activo"]), selected_active),
                    ]:
                        if str(old_value) != str(new_value):
                            audit("app_users", selected_id, field, old_value, new_value,
                                  "Configuración de acceso por Jefatura", user_id)
                    if selected_role != "JEFATURA" and old_operation != selected_operation:
                        audit("app_users", selected_id, "operacion", old_operation, selected_operation,
                              "Asignación de operación por Jefatura", user_id)
                    st.success("Usuario actualizado.")
                    st.rerun()

            st.markdown("#### Restablecer contraseña")
            with st.form(f"reset_password_form_{selected_id}", clear_on_submit=True):
                new_password = st.text_input(
                    "Nueva contraseña", type="password", key=f"reset_password_{selected_id}"
                )
                confirm_password = st.text_input(
                    "Confirmar nueva contraseña", type="password", key=f"confirm_reset_password_{selected_id}"
                )
                reset_password = st.form_submit_button("Restablecer contraseña", use_container_width=True)
                if reset_password:
                    if not new_password:
                        st.error("La contraseña no puede estar vacía.")
                    elif new_password != confirm_password:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        edit(T["users"], {"clave_hash": hash_password(new_password)}, {"id": selected_id})
                        audit("app_users", selected_id, "clave_hash", "Protegido", "Actualizado",
                              "Restablecimiento de contraseña por Jefatura", user_id)
                        st.success("Contraseña restablecida correctamente.")

    with create_tab:
        st.caption("Puedes usar un nombre provisional y reemplazarlo cuando recibas la relación oficial.")
        with st.form("create_user", clear_on_submit=True):
            new_name = st.text_input("Nombre", placeholder="Ejemplo: Asistente Turno Día")
            new_username = st.text_input("Usuario", placeholder="Ejemplo: asistente.dia")
            new_role = st.selectbox("Rol", ["ASISTENTE", "SUPERVISOR", "JEFATURA"], key="new_role")
            new_user_password = st.text_input("Contraseña inicial", type="password")
            new_user_password_confirm = st.text_input("Confirmar contraseña", type="password")
            new_user_operation = st.selectbox(
                "Operación principal", [operation["name"] for operation in OPERACIONES], key="new_operation"
            )
            if st.form_submit_button("Crear usuario", type="primary", use_container_width=True):
                duplicate = all_users[all_users["usuario"].astype(str).str.lower() == new_username.strip().lower()]
                if not new_name.strip() or not new_username.strip():
                    st.error("Nombre y usuario son obligatorios.")
                elif not duplicate.empty:
                    st.error("Ese nombre de usuario ya existe.")
                elif not new_user_password:
                    st.error("La contraseña no puede estar vacía.")
                elif new_user_password != new_user_password_confirm:
                    st.error("Las contraseñas no coinciden.")
                else:
                    created = add(T["users"], {"nombre": new_name.strip(),
                                                "usuario": new_username.strip().lower(),
                                                "clave_hash": hash_password(new_user_password),
                                                "rol": new_role, "activo": True,
                                                "creado_en": now()})
                    if new_role != "JEFATURA":
                        save_assigned_operation(str(created["id"]), new_user_operation)
                    audit("app_users", str(created["id"]), "registro", None, "Creado",
                          "Usuario creado por Jefatura", user_id)
                    st.success("Usuario creado correctamente.")
                    st.rerun()

elif role == "JEFATURA":
    st.title(f"{page} · {selected_operation}")
    if page in ["Panel", "Turnos"]:
        data = today_turns(filter_current_operation(frame(T["turnos"])))
        if page == "Panel":
            metric_labels = [("ABIERTO", "Por confirmar"), ("CONFIRMADO", "En ejecución"),
                             ("CERRADO", "Cierres pendientes"), ("VALIDADO", "Finalizados")]
            for column, (status, label_text) in zip(st.columns(4), metric_labels):
                column.metric(label_text, int((data["estado"] == status).sum()) if not data.empty else 0)
        render_daily_turn_table(data, f"management_daily_shift_{page}")
    elif page == "Incidencias":
        turns = today_turns(filter_current_operation(frame(T["turnos"])))
        incidents = frame(T["inc"])
        if turns.empty or incidents.empty:
            st.info("Sin incidencias registradas en esta operación.")
        else:
            turn_ids = set(turns["id"].astype(str))
            incidents = incidents[incidents["turno_id"].astype(str).isin(turn_ids)]
            st.dataframe(incident_summary(incidents), width="stretch", hide_index=True) if not incidents.empty else st.info("Sin incidencias registradas en esta operación.")
    else:
        data = frame(T["audit"])
        st.caption("Detalle técnico reservado para trazabilidad y revisión.")
        st.dataframe(data, width="stretch", hide_index=True) if not data.empty else st.info("Sin datos de auditoría.")

st.divider()
st.caption("Control de Operaciones Logísticas · Supabase · Refrigerio automático: 45 min en jornadas mayores a 6 horas")
