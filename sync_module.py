# VERSION: 2.0.040526-3
# ─────────────────────────────────────────────────────────────────────────────
# sync_module.py              
# ─────────────────────────────────────────────────────────────────────────────
import os
import time
import logging
from datetime import datetime, date
from dotenv import load_dotenv
import minimalmodbus
import requests
from sqlalchemy import and_, func
import threading
import queue
import time as _time
import subprocess
import json
import re

from app import db
from app_instance import app
from app.models import Parameter, Scenario, MixingParameter, Log, DensityRecord

# ─────────────────────────────────────────────────────────────────────────────
#                           Загрузка конфигурации
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()

DEBUG_MODE               = os.getenv("DEBUG_MODE", "False").lower() == "true"
DEBUG_COM_PORT           = os.getenv("DEBUG_COM_PORT", "COM4")
DEBUG_BAUDRATE           = int(os.getenv("DEBUG_BAUDRATE", "115200"))
DEBUG_TIMEOUT_COM        = float(os.getenv("DEBUG_TIMEOUT_COM", "0.1"))
DEBUG_HANDLE_ECHO        = os.getenv("DEBUG_HANDLE_ECHO", "True").lower() == "true"

MAX_TOKEN              = os.getenv("MAX_TOKEN")
MAX_CHAT_ID            = os.getenv("MAX_CHAT_ID")
MAX_USER_ID            = os.getenv("MAX_USER_ID")
MAX_BATCH_INTERVAL     = int(os.getenv("MAX_BATCH_INTERVAL", "10"))
MAX_API_BASE           = os.getenv("MAX_API_BASE", "https://platform-api.max.ru")
MAX_DISABLE_LINK_PREVIEW = os.getenv("MAX_DISABLE_LINK_PREVIEW", "true").lower() == "true"
MAX_MESSAGE_LIMIT      = 3999
MAX_MESSAGE_PART_DELAY = 2
VERSION_FILE_PATH      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version")

CRITICAL_ALERT_INTERVAL  = int(os.getenv("CRITICAL_ALERT_INTERVAL", "60"))  # в минутах
OFFLINE_ALERT_THRESHOLDS = [5, 10, 30, 60]  # в минутах

PH_LOW, PH_HIGH          = 5.5, 7.5
EC_LOW, EC_HIGH          = 1.5, 2.5

WATER_FLOW_THRESHOLD     = float(os.getenv("WATER_FLOW_THRESHOLD", "10"))  # л/м

IW_BIN = "/usr/sbin/iw"
WPA_CLI_BIN = "/sbin/wpa_cli"
IP_BIN = "/sbin/ip"
MODEM_INFO_PATH = "/run/uspd/modem/modem.info"
WIFI_CONF_PATH = "/etc/smart-wifi/wifi.conf"

NETWORK_STATUS_POLL_INTERVAL = int(os.getenv("NETWORK_STATUS_POLL_INTERVAL", "30"))

# ─────────────────────────────────────────────────────────────────────────────
#                             Логирование & Сессия
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
session = db.session

# ─────────────────────────────────────────────────────────────────────────────
#                         Глобальные структуры
# ─────────────────────────────────────────────────────────────────────────────
# Очередь для сообщений в мессенджер
notify_queue = queue.Queue()

modbus_clients          = {}   # name -> minimalmodbus.Instrument
offline_counters        = {}   # name -> {"start": datetime, "sent": set()}
low_level_notifications = {}   # param.id -> last_sent_datetime
last_critical_alerts    = {"PH": None, "EC": None}
feed_started_flags      = set()
previous_device_values  = {}
previous_db_values      = {}
first_run               = True
previous_maintenance_mode   = None
last_critical_links     = {}
_prev_water_flow        = None
_prev_total_volume      = None
pending_change_sources = {}  # param.id -> {"source": str, "value": float, "value_date": datetime}

mix_state = {
    "mix_start":   None,
    "stabilized":  False,
    "prev_ec":     None,
    "prev_ph":     None,
    "expected_ec": None,
    "expected_ph": None,
}

calibration_prev_states = {
    "PH": {"state": "idle", "seen_active": False, "watch": False},
    "EC": {"state": "idle", "seen_active": False, "watch": False},
}

# Словарь связанных критических условий:
# формат: (параметр1, должен_быть_включен1, параметр2, должен_быть_включен2)
CRITICAL_LINKS = [
    ("Насос", True, "Уровень 1 минимум", False),
    ("Подача А в бак", True, "Уровень А", False),
    ("Подача В в бак", True, "Уровень В", False),
    ("Подача кислоты в бак", True, "Уровень К", False),
]

STIRRER_PARAM = "Перемешивание"
CLOSE_STIRRER_DURING_FEED_PARAM = "Закрывать клапан перемешивания на время работы растворного узла"
FEED_RELAYS = [
    "Подача А в бак",
    "Подача В в бак",
    "Подача кислоты в бак",
]

previous_network_status = {
    "wifi": None,
    "gsm": None,
}

previous_network_ips = {
    "wifi": None,
    "gsm": None,
}

last_network_status_check = None

# ─────────────────────────────────────────────────────────────────────────────
#                          Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────
def to_str(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def norm_op_type(value) -> str:
    return to_str(value).replace(" ", "").lower()


def is_calibration_readonly_param(name: str) -> bool:
    """
    Параметры калибровки, которые sync_module не должен писать
    через обычную двустороннюю синхронизацию.

    Для растворов:
      - sync только читает из датчика
      - запись делает только web endpoint /update_calibration_parameter

    Для служебных флагов калибровки:
      - ими управляет только handle_calibration()
      - обычный sync не должен их откатывать назад
    """
    return name in {
        "ph_buffer_1",
        "ph_buffer_2",

        "ec_solution_1",
        "ec_solution_2",
        "ec_calibration_temperature",

        "PH_CALC_SAVE",
        "PH_CALC_DO",
        "PH Calibration Start",

        "EC_CALC_SAVE",
        "EC_CALC_DO",
        "EC Calibration Start",
    }
    
# ─────────────────────────────────────────────────────────────────────────────
#                          Вспомогательные функции DB
# ─────────────────────────────────────────────────────────────────────────────
def monitor_water_flow(current_flow: float):
    """
    Отслеживает параметр «Расход чистой воды» (л/м):
      • при переходе через WATER_FLOW_THRESHOLD вверх — лог «Зафиксирован расход Xл/м»
      • при падении ниже порога — лог «Расход воды прекратился»
    """
    global _prev_water_flow
    if _prev_water_flow is None:
        _prev_water_flow = current_flow
        return

    if _prev_water_flow <= WATER_FLOW_THRESHOLD < current_flow:
        insert_log_message(f"Зафиксирован расход воды {current_flow:.1f}л/м", "INFO")
    elif _prev_water_flow > WATER_FLOW_THRESHOLD >= current_flow:
        insert_log_message("Расход воды прекратился", "INFO")

    _prev_water_flow = current_flow


def monitor_total_volume(current_volume: float):
    """
    Отслеживает параметр «Объем чистой воды» (л):
      • при увеличении — лог «Вылито +Δ л воды. Всего X л.»
    """
    global _prev_total_volume
    if _prev_total_volume is None:
        _prev_total_volume = current_volume
        return

    delta = current_volume - _prev_total_volume
    if delta > 0:
        d_int = int(round(delta))
        insert_log_message(f"Вылито +{d_int} л воды. Всего {current_volume:.1f} л.", "INFO")

    _prev_total_volume = current_volume


def read_software_version():
    try:
        with open(VERSION_FILE_PATH, "r", encoding="utf-8") as f:
            version = f.readline().strip()
        return version or "не указана"
    except Exception:
        return "не указана"


def add_software_version_to_message(text: str) -> str:
    version_line = f"Версия ПО: {read_software_version()}"
    if text.startswith("Версия ПО:"):
        return text
    return f"{version_line}\n{text}"


def split_message_by_limit(text: str, limit: int = MAX_MESSAGE_LIMIT):
    if limit <= 0 or len(text) <= limit:
        return [text]

    parts = []
    current = ""

    for line in text.splitlines():
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            parts.append(current)
            current = ""

        while len(line) > limit:
            parts.append(line[:limit])
            line = line[limit:]

        if line:
            current = line

    if current:
        parts.append(current)

    return parts or [text[:limit]]


def send_max_message(text: str, level: str = "INFO"):
    if not MAX_TOKEN:
        logger.error("MAX_TOKEN не задан")
        return False

    if not MAX_CHAT_ID and not MAX_USER_ID:
        logger.error("Не задан ни MAX_CHAT_ID, ни MAX_USER_ID")
        return False

    url = f"{MAX_API_BASE}/messages"

    params = {}
    if MAX_CHAT_ID:
        params["chat_id"] = MAX_CHAT_ID
    elif MAX_USER_ID:
        params["user_id"] = MAX_USER_ID

    # 🔴 логика уведомлений
    notify = True if level in ("ERROR", "CRITICAL") else False

    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json",
    }

    message_parts = split_message_by_limit(add_software_version_to_message(text), MAX_MESSAGE_LIMIT)

    try:
        for index, message_part in enumerate(message_parts):
            payload = {
                "text": message_part,
                "disable_link_preview": MAX_DISABLE_LINK_PREVIEW,
                "notify": notify,
            }

            r = requests.post(
                url,
                params=params,
                headers=headers,
                json=payload,
                timeout=5,
            )
            if r.status_code not in (200, 201):
                logger.error(f"MAX error {r.status_code}: {r.text}")
                return False

            if index < len(message_parts) - 1:
                _time.sleep(MAX_MESSAGE_PART_DELAY)

        return True
    except Exception as e:
        logger.error(f"MAX exception: {e}")
        return False


def insert_log_message(message: str, level: str="INFO", queue_for_max: bool=True):
    """
    Записывает лог в БД и, при необходимости, ставит в очередь для пакетной отправки.
    """
    try:
        entry = Log(message=message, level=level, timestamp=datetime.now())
        session.add(entry)
        session.commit()
        # Ограничиваем размер БД-логов
        total = session.query(Log).count()
        if total > 1000:
            for old in session.query(Log).order_by(Log.timestamp).limit(total-1000):
                session.delete(old)
            session.commit()
        if queue_for_max:
            notify_queue.put((level, message))

    except Exception as e:
        logger.error(f"Ошибка логирования: {e}")
        session.rollback()


def get_parameter(name: str) -> Parameter:
    p = session.query(Parameter).filter_by(controlled_parameter_name=name).first()
    if not p:
        raise ValueError(f"Параметр '{name}' не найден")
    return p


def get_parameter_value(name: str) -> str:
    p = get_parameter(name)
    return p.value
    
def get_maintenance_mode_value() -> str:
    """
    Режим ТО:
    1 = сценарии запрещены
    0 = сценарии разрешены
    """
    p = session.query(Parameter).filter_by(
        controlled_parameter_name="Режим ТО"
    ).first()

    if not p:
        logger.warning("Параметр 'Режим ТО' не найден. Сценарии будут разрешены.")
        return "0"

    return str(p.value or "0")


def update_parameter_value(name: str, value: str):
    p = get_parameter(name)
    p.value = value
    p.value_date = datetime.now()
    session.commit()
    
def should_close_stirrer_during_feed() -> bool:
    try:
        return float(get_parameter_value(CLOSE_STIRRER_DURING_FEED_PARAM) or 0) > 0
    except Exception as e:
        logger.warning(
            f"Параметр '{CLOSE_STIRRER_DURING_FEED_PARAM}' не найден или некорректен — "
            f"клапан перемешивания не будет закрываться. Ошибка: {e}"
        )
        return False
    
def update_text_parameter(name: str, value: str):
    p = session.query(Parameter).filter_by(controlled_parameter_name=name).first()
    if not p:
        logger.warning(f"Текстовый параметр '{name}' не найден")
        return

    if str(p.value or "") != value:
        p.value = value
        p.value_date = datetime.now()
        session.commit()
        
def get_wifi_ifaces():
    ap_iface = None
    sta_iface = None

    try:
        result = subprocess.run(
            [IW_BIN, "dev"],
            capture_output=True,
            text=True,
            timeout=2
        )

        if result.returncode != 0:
            return ap_iface, sta_iface

        current_iface = None

        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()

            if line.startswith("Interface "):
                current_iface = line.split("Interface ", 1)[1].strip()

            elif line.startswith("type ") and current_iface:
                iface_type = line.split("type ", 1)[1].strip()

                if iface_type == "AP" and ap_iface is None:
                    ap_iface = current_iface
                elif iface_type == "managed" and sta_iface is None:
                    sta_iface = current_iface

        return ap_iface, sta_iface

    except Exception:
        return None, None


def get_wifi_client_status() -> str:
    try:
        if not os.path.exists(WIFI_CONF_PATH):
            return "WiFi не настроен"

        _, sta_iface = get_wifi_ifaces()

        if not sta_iface:
            return "Адаптер не обнаружен"

        wpa = subprocess.run(
            [WPA_CLI_BIN, "-i", sta_iface, "status"],
            capture_output=True,
            text=True,
            timeout=2
        )

        if wpa.returncode != 0:
            return "Сеть не подключена"

        status = {}
        for line in wpa.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                status[key.strip()] = value.strip()

        if status.get("wpa_state") == "COMPLETED":
            ip_addr = status.get("ip_address")
            if ip_addr:
                return f"Подключен, получен IP:  {ip_addr}"
            return "Подключен, но IP-адрес не получен. Перезапуск сервиса.."

        return "Сеть не подключена"

    except Exception:
        return "Адаптер не обнаружен"


def get_ppp0_ip():
    try:
        result = subprocess.run(
            [IP_BIN, "-4", "addr", "show", "ppp0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3
        )

        match = re.search(r"inet\s+([0-9.]+)\s+peer", result.stdout)
        if match:
            return match.group(1)

        match = re.search(r"inet\s+([0-9.]+)/", result.stdout)
        if match:
            return match.group(1)

        return ""

    except Exception:
        return ""


def read_modem_state_for_log():
    if not os.path.exists(MODEM_INFO_PATH):
        return None

    try:
        with open(MODEM_INFO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {
            "ipaddr": get_ppp0_ip(),
            "level": data.get("level", ""),
            "net_type": data.get("mode", "") or "GSM",
        }

    except Exception:
        return None


def get_gsm_status_state():
    modem_state = read_modem_state_for_log()

    if not modem_state:
        return {
            "connected": False,
            "ip": "",
            "text": "Нет связи или SIM отсутствует. Перезапуск модема…"
        }

    gsm_ip = modem_state.get("ipaddr", "")
    net_type = modem_state.get("net_type") or "GSM"

    if gsm_ip:
        return {
            "connected": True,
            "ip": gsm_ip,
            "text": f"{net_type}: соединение восстановлено, IP {gsm_ip}"
        }

    return {
        "connected": False,
        "ip": "",
        "text": f"{net_type}: соединение потеряно"
    }


def extract_ipv4_address(text: str) -> str:
    match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text or "")
    return match.group(0) if match else ""


def monitor_network_status():
    global previous_network_status, previous_network_ips, last_network_status_check

    now = datetime.now()

    if last_network_status_check:
        elapsed = (now - last_network_status_check).total_seconds()
        if elapsed < NETWORK_STATUS_POLL_INTERVAL:
            return

    last_network_status_check = now

    wifi_text = get_wifi_client_status()
    wifi_connected = wifi_text.startswith("Подключен, получен IP:")
    wifi_ip = extract_ipv4_address(wifi_text) if wifi_connected else ""

    gsm_state = get_gsm_status_state()
    gsm_connected = gsm_state["connected"]
    gsm_ip = gsm_state.get("ip", "") if gsm_connected else ""
    gsm_text = gsm_state["text"]

    # Первый проход только запоминаем состояние
    if previous_network_status["wifi"] is None:
        previous_network_status["wifi"] = wifi_connected
        if wifi_ip:
            previous_network_ips["wifi"] = wifi_ip
    elif previous_network_status["wifi"] != wifi_connected:
        if wifi_connected:
            ip_changed = previous_network_ips["wifi"] != wifi_ip
            insert_log_message(
                f"WiFi: соединение восстановлено, {wifi_text}",
                "INFO",
                queue_for_max=ip_changed
            )
            if wifi_ip:
                previous_network_ips["wifi"] = wifi_ip
        else:
            insert_log_message("WiFi: соединение потеряно", "ERROR")

        previous_network_status["wifi"] = wifi_connected

    if previous_network_status["gsm"] is None:
        previous_network_status["gsm"] = gsm_connected
        if gsm_ip:
            previous_network_ips["gsm"] = gsm_ip
    elif previous_network_status["gsm"] != gsm_connected:
        if gsm_connected:
            ip_changed = previous_network_ips["gsm"] != gsm_ip
            insert_log_message(
                f"GSM: {gsm_text}",
                "INFO",
                queue_for_max=ip_changed
            )
            if gsm_ip:
                previous_network_ips["gsm"] = gsm_ip
        else:
            insert_log_message(f"GSM: {gsm_text}", "INFO")

        previous_network_status["gsm"] = gsm_connected

def read_calibration_status_direct(prefix: str, sensor_name: str):
    state = calibration_prev_states.setdefault(
        prefix,
        {"state": "idle", "seen_active": False, "watch": False}
    )

    # Статус калибровки трогаем только после нажатия кнопки Старт
    if not state.get("watch"):
        return

    base = get_parameter(f"{prefix}_CALC_SAVE")
    dev_name = f"{base.device_type}_addr{base.network_address}"

    if dev_name not in modbus_clients:
        modbus_clients[dev_name] = setup_modbus_client(base)

    inst = modbus_clients[dev_name]
    bits = inst.read_bits(0, 4, functioncode=2)

    err = int(bits[0])
    stage1 = int(bits[1])
    stay = int(bits[2])
    stage2 = int(bits[3])

    is_active = bool(stage1 or stay or stage2)
    is_idle = not err and not is_active

    if err:
        update_text_parameter(f"{prefix} Calibration Status", f"Калибровка {sensor_name}: ошибка")
        state["state"] = "error"
        state["seen_active"] = False
        state["watch"] = False
        return

    if stage1:
        update_text_parameter(f"{prefix} Calibration Status", f"Калибровка {sensor_name}: стадия 1")
        state["state"] = "active"
        state["seen_active"] = True
        return

    if stay:
        update_text_parameter(f"{prefix} Calibration Status", f"Калибровка {sensor_name}: ожидание смены жидкости")
        state["state"] = "active"
        state["seen_active"] = True
        return

    if stage2:
        update_text_parameter(f"{prefix} Calibration Status", f"Калибровка {sensor_name}: стадия 2")
        state["state"] = "active"
        state["seen_active"] = True
        return

    if is_idle and state.get("seen_active"):
        success_status = f"Калибровка {sensor_name}: успешно"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        update_text_parameter(f"{prefix} Calibration Status", success_status)
        update_text_parameter(f"{prefix} Calibration Updated", now_str)

        insert_log_message(f"Калибровка {sensor_name} завершена успешно", "INFO")

        state["state"] = "idle"
        state["seen_active"] = False
        state["watch"] = False
        return

    return


def get_mixing_parameters() -> MixingParameter:
    mp = session.query(MixingParameter).first()
    if not mp:
        raise ValueError("MixingParameter не найден")
    return mp


def insert_density_record(name: str, value: float):
    dr = DensityRecord(density_name=name, value=value, timestamp=datetime.now())
    session.add(dr)
    session.commit()

    count = session.query(DensityRecord).count()
    if count > 150:
        old = session.query(DensityRecord).order_by(DensityRecord.timestamp).limit(count - 150).all()
        for r in old:
            session.delete(r)
        session.commit()


def insert_buffer_capacity_record(bf_value: float):
    dr = DensityRecord(density_name="buffer_capacity", value=bf_value, timestamp=datetime.now())
    session.add(dr)
    session.commit()


def format_value(param: Parameter, raw_val: str) -> str:
    try:
        v = float(raw_val)
        t = param.parameter_type.lower()
        name = param.controlled_parameter_name
        if t == "bool":
            return "включен" if v != 0 else "отключен"
        if name in ("Уровень PH", "Уровень EC"):
            return f"{v:.1f}"
        return str(int(round(v)))
    except Exception:
        return str(raw_val)


def remember_pending_change_source(param: Parameter, source: str):
    try:
        target_value = float(param.value or 0)
    except Exception:
        target_value = None

    pending_change_sources[param.id] = {
        "source": source,
        "value": target_value,
        "value_date": param.value_date,
    }


def consume_pending_change_source(param: Parameter, current_value: float) -> str:
    entry = pending_change_sources.get(param.id)
    if not entry:
        return "WEB"

    if not isinstance(entry, dict):
        pending_change_sources.pop(param.id, None)
        return str(entry or "WEB")

    expected_value = entry.get("value")
    expected_date = entry.get("value_date")

    value_matches = False
    if expected_value is not None:
        try:
            value_matches = abs(float(expected_value) - float(current_value)) < 1e-9
        except Exception:
            value_matches = False

    date_matches = expected_date is None or param.value_date == expected_date

    if value_matches and date_matches:
        pending_change_sources.pop(param.id, None)
        return entry.get("source") or "WEB"

    pending_change_sources.pop(param.id, None)
    return "WEB"

# Отбор сообщений для отправки в мессенджер
def should_send_to_max(level: str, msg: str) -> bool:
    return (
        level in ("ERROR", "CRITICAL")
        or "IP" in msg
        or "ip" in msg
        or msg.startswith("По завершении цикла регулирования получили:")
        or msg.startswith("Запуск синхронизации:")
    )
    
def _max_dispatcher():
    """
    Каждые MAX_BATCH_INTERVAL секунд забираем всю очередь
    и отсылаем одним сообщением в MAX.
    """
    while True:
        _time.sleep(MAX_BATCH_INTERVAL)

        batch = []
        while True:
            try:
                level, msg = notify_queue.get_nowait()

                if should_send_to_max(level, msg):
                    batch.append((level, msg))

            except queue.Empty:
                break

        if not batch:
            continue

        levels = {lvl for lvl, _ in batch}

        # если хоть одна ошибка — считаем ERROR
        if "ERROR" in levels:
            level = "ERROR"
        elif "WARNING" in levels:
            level = "WARNING"
        else:
            level = "INFO"

        text = "\n".join(f"[{lvl}] {m}" for lvl, m in batch)

        ok = send_max_message(text, level=level)

        if not ok:
            logger.error("Не удалось отправить пакет сообщений в MAX")


# ─────────────────────────────────────────────────────────────────────────────
#                           Вспомогательные Modbus
# ─────────────────────────────────────────────────────────────────────────────
def setup_modbus_client(param: Parameter) -> minimalmodbus.Instrument:
    mode = param.mode
    addr = int(param.network_address)

    if mode == "com":
        port = DEBUG_COM_PORT if DEBUG_MODE else str(param.com)
        baud = DEBUG_BAUDRATE if DEBUG_MODE else int(param.speed)
        to = DEBUG_TIMEOUT_COM if DEBUG_MODE else float(getattr(param, "timeout", 1.0))

        inst = minimalmodbus.Instrument(port, addr, mode=minimalmodbus.MODE_RTU)
        inst.serial.baudrate = baud
        inst.serial.timeout = to
        inst.serial.bytesize = 8
        inst.serial.parity = minimalmodbus.serial.PARITY_NONE
        inst.serial.stopbits = 1
        inst.handle_local_echo = DEBUG_HANDLE_ECHO
        return inst

    if mode == "tcp":
        host = param.ip_address
        inst = minimalmodbus.Instrument(host, addr, mode=minimalmodbus.MODE_TCP)
        inst.serial.timeout = 1
        return inst

    raise ValueError(f"Unknown mode {mode}")


def read_registers_batch(group: dict):
    name = group["device_name"]
    regs = group["parameters"]
    start = group["start_address"]
    cnt = group["count"]
    rtype = group["register_type"]

    if name not in modbus_clients:
        try:
            modbus_clients[name] = setup_modbus_client(regs[0])
        except Exception:
            update_offline_counter(name)
            return None

    inst = modbus_clients[name]

    try:
        if rtype == "1":
            vals = inst.read_bits(start, cnt, functioncode=1)
        elif rtype == "2":
            vals = inst.read_bits(start, cnt, functioncode=2)
        elif rtype == "3":
            vals = inst.read_registers(start, cnt, functioncode=3)
        elif rtype == "4":
            vals = inst.read_registers(start, cnt, functioncode=4)
        else:
            return None

        reset_offline_counter(name)

        out = []
        for i, p in enumerate(regs):
            K = float(p.K) if p.K else 1.0
            out.append(vals[i] / K)
        return out

    except Exception as e:
        logger.error(f"Modbus read error {name}: {e}")
        modbus_clients.pop(name, None)
        update_offline_counter(name)
        return None


def write_parameter_value(param: Parameter, value: float) -> bool:
    """
    value передаётся в человекочитаемом виде.
    Масштабирование делается только здесь через K.
    """
    name = f"{param.device_type}_addr{param.network_address}"

    if name not in modbus_clients:
        try:
            modbus_clients[name] = setup_modbus_client(param)
        except Exception:
            update_offline_counter(name)
            return False

    inst = modbus_clients[name]

    try:
        addr = int(param.register_number)
        K = float(param.K) if param.K else 1.0
        val = int(value * K)

        logger.info(f"[WRITE] {param.controlled_parameter_name} -> raw={val} human={value}")

        if param.register_type == "1":
            inst.write_bit(addr, val, functioncode=5)
        elif param.register_type == "3":
            inst.write_register(addr, val, functioncode=6)
        else:
            logger.error(
                f"Unsupported register_type {param.register_type} for {param.controlled_parameter_name}"
            )
            return False

        reset_offline_counter(name)

        # критично: чтобы sync не откатывал значение назад в этом же цикле
        previous_device_values[param.id] = float(value)
        previous_db_values[param.id] = float(value)

        return True

    except Exception as e:
        logger.error(f"Modbus write error {param.controlled_parameter_name}: {e}")
        update_offline_counter(name)
        return False


def set_parameter_and_sync(param: Parameter, value: float) -> bool:
    """
    Пишем значение сразу в устройство и синхронно обновляем БД/кеш,
    чтобы обычный poll_parameters не воспринял это как конфликт.
    """
    ok = write_parameter_value(param, value)
    if not ok:
        return False

    param.value = str(value)
    param.value_date = datetime.now()
    session.commit()

    previous_device_values[param.id] = float(value)
    previous_db_values[param.id] = float(value)
    return True


def _manage_stirrer_direct():
    """
    Если настройка включена:
      Если открыт хотя бы один дозирующий клапан -> Перемешивание = 0
      Если все дозирующие клапаны закрыты       -> Перемешивание = 1

    Если настройка выключена — перемешивание не трогаем.
    """
    try:
        if not should_close_stirrer_during_feed():
            return

        stirrer = get_parameter(STIRRER_PARAM)

        any_running = any(
            float(get_parameter_value(relay) or 0) > 0
            for relay in FEED_RELAYS
        )

        new_val = 0.0 if any_running else 1.0
        cur_val = float(stirrer.value or 0)

        if cur_val != new_val:
            set_parameter_and_sync(stirrer, new_val)

    except Exception:
        logger.exception("Ошибка прямого управления перемешиванием")


def group_parameters(params):
    grouped = []
    sorted_p = sorted(params, key=lambda p: (
        p.device_type,
        p.network_address,
        p.mode,
        p.com if p.mode == "com" else p.ip_address,
        p.register_type,
        int(p.register_number)
    ))

    grp = {}
    prev = None

    for p in sorted_p:
        name = f"{p.device_type}_addr{p.network_address}"
        chan = p.mode
        comm = p.com if chan == "com" else p.ip_address
        rtype = p.register_type
        addr = int(p.register_number)

        if (
            not prev or
            name != grp.get("device_name") or
            chan != grp.get("mode") or
            comm != grp.get("comm") or
            rtype != grp.get("register_type") or
            addr != grp.get("start_address", 0) + grp.get("count", 0)
        ):
            if prev:
                grouped.append(grp)
            grp = {
                "device_name": name,
                "mode": chan,
                "comm": comm,
                "register_type": rtype,
                "start_address": addr,
                "count": 1,
                "parameters": [p]
            }
        else:
            grp["count"] += 1
            grp["parameters"].append(p)

        prev = p

    if grp:
        grouped.append(grp)

    return grouped


# ─────────────────────────────────────────────────────────────────────────────
#                         Сценарии (execute_scenarios)
# ─────────────────────────────────────────────────────────────────────────────
def skip_due_scenarios(reason: str = "Режим ТО"):
    today = date.today()
    now_t = datetime.now().time()

    scs = session.query(Scenario).filter(
        and_(
            Scenario.time <= now_t,
            (Scenario.last_execution == None) |
            (func.date(Scenario.last_execution) < today)
        )
    ).all()

    for sc in scs:
        sc.result = f"Пропущено: {reason}"
        sc.last_execution = datetime.now()

    session.commit()


def restore_stateful_scenarios_after_maintenance():
    """
    После выхода из режима ТО восстанавливаем текущее состояние
    длительных сценариев: свет, уровни света.
    Полив здесь не восстанавливаем, чтобы не запускать насосы посреди цикла.
    """
    today = date.today()
    now_t = datetime.now().time()

    scs = session.query(Scenario).filter(
        and_(
            Scenario.type.in_(["Свет", "Свет уровень"]),
            Scenario.time <= now_t
        )
    ).order_by(Scenario.parameter, Scenario.time, Scenario.id).all()

    latest_by_param = {}

    for sc in scs:
        latest_by_param[sc.parameter] = sc

    for parameter_name, sc in latest_by_param.items():
        p = session.query(Parameter).filter_by(
            controlled_parameter_name=parameter_name
        ).first()

        if not p:
            logger.error(f"Восстановление после ТО: параметр {parameter_name} не найден")
            continue

        p.value = sc.value
        p.value_date = datetime.now()

        sc.result = "Восстановлено после ТО"
        sc.last_execution = datetime.now()

        insert_log_message(
            f"После выхода из режима ТО восстановлено: {p.controlled_parameter_name} → {format_value(p, p.value)}",
            "INFO"
        )

    session.commit()
    
def execute_scenarios():
    today = date.today()
    now_t = datetime.now().time()

    try:
        scs = session.query(Scenario).filter(
            and_(
                Scenario.time <= now_t,
                (Scenario.last_execution == None) |  # noqa: E711
                (func.date(Scenario.last_execution) < today)
            )
        ).order_by(Scenario.time, Scenario.id).all()

        for sc in scs:
            p = session.query(Parameter).filter_by(controlled_parameter_name=sc.parameter).first()
            if not p:
                logger.error(f"Сценарий: {sc.parameter} not found")
                continue

            old_value = p.value

            p.value = sc.value
            p.value_date = datetime.now().replace(second=0, microsecond=0)
            session.commit()

            remember_pending_change_source(p, "Сценарий")

            p_ph = session.query(Parameter).filter_by(controlled_parameter_name="Уровень PH").first()
            p_ec = session.query(Parameter).filter_by(controlled_parameter_name="Уровень EC").first()

            ph_fmt = format_value(p_ph, p_ph.value)
            ec_fmt = format_value(p_ec, p_ec.value)
            val_fmt = format_value(p, p.value)

            msg = (
                f"Сценарий: {p.controlled_parameter_name} → {val_fmt}. "
                f"PH={ph_fmt}, EC={ec_fmt}"
            )

            sc.result = f"Записано {val_fmt}"
            sc.last_execution = datetime.now()
            session.commit()

#            insert_log_message(msg, "INFO")

    except Exception as e:
        logger.error(f"Scenario error: {e}")
        session.rollback()


# ─────────────────────────────────────────────────────────────────────────────
#                           Off-line уведомления
# ─────────────────────────────────────────────────────────────────────────────
def update_offline_counter(dev):
    now = datetime.now()
    ctr = offline_counters.get(dev)
    if not ctr:
        offline_counters[dev] = {"start": now, "sent": set()}


def reset_offline_counter(dev):
    offline_counters.pop(dev, None)


def check_offline_alarms():
    now = datetime.now()
    for dev, d in list(offline_counters.items()):
        mins = (now - d["start"]).total_seconds() / 60
        for th in OFFLINE_ALERT_THRESHOLDS:
            if mins >= th and th not in d["sent"]:
                insert_log_message(f"Нет связи с устройством {dev} уже {int(mins)} мин.", "ERROR")
                d["sent"].add(th)


# ─────────────────────────────────────────────────────────────────────────────
#                      Управление подачей (handle_feed_timers)
# ─────────────────────────────────────────────────────────────────────────────
def handle_feed_timers(params_dict: dict):
    """
    Управление таймерами подачи и реле по фазам:
      idle → stabilizing → regulating → countdown → post_stabilization → regulating → …
    На время работы любого из клапанов A / В / кислоты клапан перемешивания закрывается.
    После закрытия последнего дозирующего клапана перемешивание открывается обратно.
    """
    now = datetime.now()
    mp = get_mixing_parameters()
    mode = os.getenv("PUMP_ACTIVATION_MODE", "вместе").lower()

    try:
        pump_on = float(get_parameter_value("Растворный узел") or 0) > 0
    except Exception:
        pump_on = False

    if not pump_on:
        if mix_state.get("phase") != "idle":
            for _, _, _, timer_name, relay_name in [
                ("A", "expected_ec", insert_density_record, "Время подачи A в бак", "Подача А в бак"),
                ("В", "expected_ec", insert_density_record, "Время подачи В в бак", "Подача В в бак"),
                ("кислоты", "expected_ph", insert_buffer_capacity_record, "Время подачи кислоты в бак", "Подача кислоты в бак"),
            ]:
                update_parameter_value(timer_name, "0")
                update_parameter_value(relay_name, "0")

            insert_log_message("Растворный узел выключен — сброс фаз и таймеров", "INFO")

        mix_state.clear()
        mix_state["phase"] = "idle"
        return

    phase = mix_state.get("phase", "idle")

    if phase == "idle":
        mix_state["mix_start"] = now
        mix_state["phase"] = "stabilizing"
        insert_log_message(
            f"Растворный узел включен — ждем {mp.stabilization_time}s стабилизации",
            "INFO"
        )
        return

    if phase == "stabilizing":
        elapsed = (now - mix_state["mix_start"]).total_seconds()
        if elapsed >= mp.stabilization_time:
            mix_state["phase"] = "regulating"
            mix_state["prev_ec"] = float(get_parameter_value("Уровень EC") or 0)
            mix_state["prev_ph"] = float(get_parameter_value("Уровень PH") or 0)
            insert_log_message("Стабилизация завершена — начинаем цикл регулирования", "INFO")
        return

    if phase == "regulating":
        curr_ec = float(get_parameter_value("Уровень EC") or 0)
        curr_ph = float(get_parameter_value("Уровень PH") or 0)

        delta_ec = mp.target_ec - curr_ec
        delta_ph = curr_ph - mp.target_ph

        if delta_ec > mp.ec_deviation:
            vol_ec = round(1000 * delta_ec * mp.tank_volume / (mp.density_a + mp.density_b), 0)
            rate_ec = mp.pump_flow_rate * 2 / 60000
            t_full_ec = round(vol_ec / (rate_ec * 1000), 0)
            t_work_ec = min(t_full_ec, mp.maxtime)
            units_ec = int(t_work_ec * 10)
            update_parameter_value("Время подачи A в бак", str(units_ec))
            update_parameter_value("Время подачи В в бак", str(units_ec))
            mix_state["expected_ec"] = (delta_ec * t_work_ec / t_full_ec) if t_full_ec else 0
            mix_state["prev_ec"] = float(get_parameter_value("Уровень EC") or 0)
        else:
            vol_ec = t_full_ec = t_work_ec = units_ec = 0
            mix_state["expected_ec"] = 0

        if delta_ph > mp.ph_deviation:
            vol_ph = round(delta_ph * mp.bf * mp.tank_volume / 1000, 0)
            rate_ph = mp.pump_flow_rate / 60000
            t_full_ph = round(vol_ph / (rate_ph * 1000), 0)
            t_work_ph = min(t_full_ph, mp.maxtime)
            units_ph = int(t_work_ph * 10)
            update_parameter_value("Время подачи кислоты в бак", str(units_ph))
            mix_state["expected_ph"] = (delta_ph * t_work_ph / t_full_ph) if t_full_ph else 0
            mix_state["prev_ph"] = float(get_parameter_value("Уровень PH") or 0)
        else:
            vol_ph = t_full_ph = t_work_ph = units_ph = 0
            mix_state["expected_ph"] = 0

        if mix_state["expected_ec"] == 0 and mix_state["expected_ph"] == 0:
            insert_log_message("Регулирование EC и pH не потребовалось", "INFO")
            mix_state["phase"] = "idle"
            return

        lines = ["Начало цикла регулирования."]

        if mix_state["expected_ec"] == 0:
            if curr_ec > mp.target_ec + mp.ec_deviation:
                lines.append(
                    f"Требуемый EC = {mp.target_ec:.1f}, текущий EC = {curr_ec:.1f} — "
                    f"EC выше заданного, подача A/B невозможна. Требуется разбавление."
                )
            else:
                lines.append(
                    f"Требуемый EC = {mp.target_ec:.1f}, текущий EC = {curr_ec:.1f} — "
                    f"EC в пределах допуска, регулирование по EC не требуется."
                )
        else:
            lines.append(
                f"Требуемый EC = {mp.target_ec:.1f}, текущий EC = {curr_ec:.1f}, "
                f"нужно {vol_ec:.0f} мл ({t_full_ec}s работы насоса)."
            )
            lines.append(
                f"С учётом ограничений включено A и B на {t_work_ec}s. "
                f"Ожидаемое изменение EC на {mix_state['expected_ec']:.3f} "
                f"до уровня EC={curr_ec + mix_state['expected_ec']:.3f}."
            )

        if mix_state["expected_ph"] == 0:
            if curr_ph < mp.target_ph - mp.ph_deviation:
                lines.append(
                    f"Требуемый pH = {mp.target_ph:.1f}, текущий pH = {curr_ph:.1f} — "
                    f"pH ниже заданного, подача кислоты невозможна. Требуется повышение pH."
                )
            else:
                lines.append(
                    f"Требуемый pH = {mp.target_ph:.1f}, текущий pH = {curr_ph:.1f} — "
                    f"pH в пределах допуска, регулирование по pH не требуется."
                )
        else:
            lines.append(
                f"Требуемый pH = {mp.target_ph:.1f}, текущий pH = {curr_ph:.1f}, "
                f"нужно {vol_ph:.1f} мл кислоты ({t_full_ph}s работы насоса)."
            )
            lines.append(
                f"С учётом ограничений включена кислота на {t_work_ph}s. "
                f"Ожидаемое изменение pH на {mix_state['expected_ph']:.3f} "
                f"до уровня pH={curr_ph - mix_state['expected_ph']:.3f}."
            )

        insert_log_message("\n".join(lines), "INFO")
        mix_state["phase"] = "countdown"
        return

    def process_pump(comp, exp_key, record_fn, timer_name, relay_name):
        raw = get_parameter_value(timer_name) or "0"
        rem = int(float(raw))

        relay_param = get_parameter(relay_name)
        stirrer_param = get_parameter(STIRRER_PARAM)

        if rem > 0 and timer_name not in feed_started_flags:
            logger.info(f"[feed] Подготовка к запуску {relay_name}, остаток {rem * 0.1:.1f}s")

            if should_close_stirrer_during_feed():
                set_parameter_and_sync(stirrer_param, 0)
            set_parameter_and_sync(relay_param, 1)
                
            feed_started_flags.add(timer_name)

        if rem > 0:
            new = max(0, rem - 10)
            update_parameter_value(timer_name, str(new))
        else:
            new = 0

        if new == 0 and timer_name in feed_started_flags:
            logger.info(f"[feed] Окончание {relay_name}")

            # 1. закрываем дозирующий клапан
            set_parameter_and_sync(relay_param, 0)
            feed_started_flags.remove(timer_name)

            # 2. если больше нет активных подач — снова открываем перемешивание
            _manage_stirrer_direct()

        return new

    sequence = [
        ("A", "expected_ec", insert_density_record, "Время подачи A в бак", "Подача А в бак"),
        ("В", "expected_ec", insert_density_record, "Время подачи В в бак", "Подача В в бак"),
        ("кислоты", "expected_ph", insert_buffer_capacity_record, "Время подачи кислоты в бак", "Подача кислоты в бак"),
    ]

    if mode == "вместе":
        for args in sequence:
            process_pump(*args)

        _manage_stirrer_direct()

        all_zero = all(
            int(float(get_parameter_value(tn) or "0")) == 0
            for *_, tn, __ in sequence
        )

        if phase == "countdown" and all_zero:
            mix_state["phase"] = "post_stabilization"
            mix_state["mix_start"] = now
            insert_log_message("Подачи завершены — ждем стабилизации перед завершением цикла", "INFO")

    else:
        any_active = False
        for args in sequence:
            if process_pump(*args) > 0:
                any_active = True
                break

        _manage_stirrer_direct()

        if phase == "countdown" and not any_active:
            mix_state["phase"] = "post_stabilization"
            mix_state["mix_start"] = now
            insert_log_message("Подачи по очереди завершены — ждем стабилизации перед завершением цикла", "INFO")

    if mix_state.get("phase") == "post_stabilization":
        elapsed2 = (now - mix_state["mix_start"]).total_seconds()
        if elapsed2 >= mp.stabilization_time:
            curr_ec = float(get_parameter_value("Уровень EC") or 0)
            curr_ph = float(get_parameter_value("Уровень PH") or 0)
            lines = ["По завершении цикла регулирования получили:"]

            if mix_state["expected_ec"] == 0:
                lines.append("Регулирование по EC не выполнялось.")
            else:
                actual_ec_change = curr_ec - mix_state["prev_ec"]
                eff_ec = (actual_ec_change / mix_state["expected_ec"] * 100) if mix_state["expected_ec"] else 0
                lines.append(
                    f"Ожидаемое изменение EC = {mix_state['expected_ec']:.3f}, "
                    f"факт = {actual_ec_change:.3f}, эффективность = {eff_ec:.0f}%"
                )

            if mix_state["expected_ph"] == 0:
                lines.append("Регулирование по pH кислотой не выполнялось.")
            else:
                actual_ph_change = mix_state["prev_ph"] - curr_ph
                eff_ph = (actual_ph_change / mix_state["expected_ph"] * 100) if mix_state["expected_ph"] else 0
                lines.append(
                    f"Ожидаемое изменение pH = {mix_state['expected_ph']:.3f}, "
                    f"факт = {actual_ph_change:.3f}, эффективность = {eff_ph:.0f}%"
                )

            lines.append(f"Текущие значения: PH={curr_ph:.1f}, EC={curr_ec:.1f}")

            insert_log_message("\n".join(lines), "INFO")
            mix_state["phase"] = "regulating"
            mix_state["mix_start"] = None


# ─────────────────────────────────────────────────────────────────────────────
#                        Калибровка датчиков PH и EC
# ─────────────────────────────────────────────────────────────────────────────
def handle_calibration(params_dict):
    try:
        # --- СТАРТ PH ---
        p = params_dict.get("PH Calibration Start")
        if p and str(p.value) == "1":
            logger.info("START PH CALIBRATION")

            calibration_prev_states["PH"] = {
                "state": "starting",
                "seen_active": False,
                "watch": True,
            }
            update_text_parameter("PH Calibration Status", "Калибровка pH: запуск")

            p_save = params_dict.get("PH_CALC_SAVE")
            if p_save:
                ok = write_parameter_value(p_save, 0x2709)
                if not ok:
                    logger.error("PH_CALC_SAVE write failed")

            p_start = params_dict.get("PH_CALC_DO")
            if p_start:
                ok = write_parameter_value(p_start, 1)
                if not ok:
                    logger.error("PH_CALC_DO write failed")

            p.value = "0"
            p.value_date = datetime.now()
            session.commit()

        # --- СТАРТ EC ---
        p = params_dict.get("EC Calibration Start")
        if p and str(p.value) == "1":
            logger.info("START EC CALIBRATION")
            
            calibration_prev_states["EC"] = {
                "state": "starting",
                "seen_active": False,
                "watch": True,
            }
            update_text_parameter("EC Calibration Status", "Калибровка EC: запуск")

            p_save = params_dict.get("EC_CALC_SAVE")
            if p_save:
                ok = write_parameter_value(p_save, 0x2709)
                if not ok:
                    logger.error("EC_CALC_SAVE write failed")

            p_start = params_dict.get("EC_CALC_DO")
            if p_start:
                ok = write_parameter_value(p_start, 1)
                if not ok:
                    logger.error("EC_CALC_DO write failed")

            p.value = "0"
            p.value_date = datetime.now()
            session.commit()

    except Exception as e:
        logger.error(f"Calibration error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#                        Основной опрос параметров
# ─────────────────────────────────────────────────────────────────────────────
def poll_parameters():
    global first_run, previous_device_values, previous_db_values, last_critical_links

    all_params = session.query(Parameter).all()

    monitored_params = {
        to_str(p.controlled_parameter_name)
        for p in all_params
        if norm_op_type(p.operation_type) == "чтение/запись"
    }

    low_level_params = {
        to_str(p.controlled_parameter_name)
        for p in all_params
        if "минимум" in to_str(p.controlled_parameter_name).lower()
    }

    params_dict = {to_str(p.controlled_parameter_name): p for p in all_params}

    ph = float(params_dict["Уровень PH"].value or 0)
    ec = float(params_dict["Уровень EC"].value or 0)
    now = datetime.now()

    if not first_run:
        if ph < PH_LOW or ph > PH_HIGH:
            last = last_critical_alerts["PH"]
            if not last or (now - last).total_seconds() >= CRITICAL_ALERT_INTERVAL * 60:
                insert_log_message(
                    f"Критический PH = {ph:.1f} (мин {PH_LOW}, макс {PH_HIGH})",
                    level="ERROR"
                )
                last_critical_alerts["PH"] = now

        if ec < EC_LOW or ec > EC_HIGH:
            last = last_critical_alerts["EC"]
            if not last or (now - last).total_seconds() >= CRITICAL_ALERT_INTERVAL * 60:
                insert_log_message(
                    f"Критический EC = {ec:.1f} (мин {EC_LOW}, макс {EC_HIGH})",
                    level="ERROR"
                )
                last_critical_alerts["EC"] = now

    for idx, (p1_name, must_on1, p2_name, must_on2) in enumerate(CRITICAL_LINKS):
        p1 = params_dict.get(p1_name)
        p2 = params_dict.get(p2_name)
        if not p1 or not p2:
            continue

        val1 = (float(p1.value or 0) != 0)
        val2 = (float(p2.value or 0) != 0)

        if val1 == must_on1 and val2 == must_on2:
            last = last_critical_links.get(idx)
            if not last or (now - last).total_seconds() >= CRITICAL_ALERT_INTERVAL * 60:
                state1 = format_value(p1, p1.value)
                state2 = format_value(p2, p2.value)
                insert_log_message(
                    f"Критическое событие: {p1_name} — {state1}, {p2_name} — {state2}",
                    level="ERROR"
                )
                last_critical_links[idx] = now

    # Опрос Modbus и синхронизация
    grp_params = [p for p in all_params if p.mode in ("com", "tcp")]
    for grp in group_parameters(grp_params):
        vals = read_registers_batch(grp)
        if vals is None:
            continue

        for i, p in enumerate(grp["parameters"]):
            dev_raw_f = float(vals[i])
            db_raw_f = float(p.value or 0)
            prev_dev_f = previous_device_values.get(p.id)
            prev_db_f = previous_db_values.get(p.id)
            op_type = norm_op_type(p.operation_type)
            param_name = to_str(p.controlled_parameter_name)

            # Калибровочные параметры всегда только читаем из датчика.
            # Их запись в датчик выполняется только вручную через web endpoint.
            if is_calibration_readonly_param(param_name):
                p.value = str(dev_raw_f)
                p.value_date = now
                previous_device_values[p.id] = dev_raw_f
                previous_db_values[p.id] = dev_raw_f
                continue

            if first_run:
                if (
                    op_type == "чтение/запись"
                    and param_name in monitored_params
                    and dev_raw_f != db_raw_f
                ):
                    write_parameter_value(p, db_raw_f)
                    insert_log_message(
                        f"{p.controlled_parameter_name}: первичная синхронизация WEB→Device → "
                        f"{format_value(p, str(db_raw_f))}",
                        level="INFO"
                    )

                previous_device_values[p.id] = db_raw_f
                previous_db_values[p.id] = db_raw_f
                continue

            # только чтение
            if op_type == "чтение":
                p.value = str(dev_raw_f)
                p.value_date = now
                previous_device_values[p.id] = dev_raw_f
                previous_db_values[p.id] = dev_raw_f
                continue

            # если не в monitored — тоже читаем
            if param_name not in monitored_params:
                p.value = str(dev_raw_f)
                p.value_date = now
                previous_device_values[p.id] = dev_raw_f
                previous_db_values[p.id] = dev_raw_f
                continue

            # WEB → Device
            if db_raw_f != prev_db_f and dev_raw_f == prev_dev_f:
                ok = write_parameter_value(p, db_raw_f)
                if ok:
                    source = consume_pending_change_source(p, db_raw_f)

                    try:
                        p_ph = params_dict.get("Уровень PH")
                        p_ec = params_dict.get("Уровень EC")
                        ph_fmt = format_value(p_ph, p_ph.value) if p_ph else "—"
                        ec_fmt = format_value(p_ec, p_ec.value) if p_ec else "—"
                        tail = f". PH={ph_fmt}, EC={ec_fmt}"
                    except Exception:
                        tail = ""

                    insert_log_message(
                        f"{source}: {p.controlled_parameter_name} -> {format_value(p, str(db_raw_f))}{tail}",
                        level="INFO"
                    )

                    previous_db_values[p.id] = db_raw_f
                    previous_device_values[p.id] = db_raw_f

            # Device → DB
            elif dev_raw_f != prev_dev_f and db_raw_f == prev_db_f:
                p.value = str(dev_raw_f)
                p.value_date = now
                session.commit()
                insert_log_message(
                    f"{p.controlled_parameter_name} изменено на устройстве → "
                    f"{format_value(p, str(dev_raw_f))}",
                    level="INFO"
                )
                previous_device_values[p.id] = dev_raw_f
                previous_db_values[p.id] = dev_raw_f

            # Конфликт
            elif db_raw_f != prev_db_f and dev_raw_f != prev_dev_f:
                ok = write_parameter_value(p, db_raw_f)
                if ok:
                    p.value = str(db_raw_f)
                    p.value_date = now
                    session.commit()
                    previous_db_values[p.id] = db_raw_f
                    previous_device_values[p.id] = db_raw_f

            # иначе — ничего не меняем

    session.commit()

    if not first_run:
        for name in low_level_params:
            p = params_dict.get(name)
            if p and p.value == "0":
                last = low_level_notifications.get(p.id)
                if not last or (now - last).total_seconds() >= 300:
                    insert_log_message(f"Низкий уровень {name}", level="WARNING")
                    low_level_notifications[p.id] = now
            else:
                if p:
                    low_level_notifications.pop(p.id, None)

    try:
        flow_param = float(params_dict["Расход чистой воды"].value or 0)
        volume_param = float(params_dict["Объем чистой воды"].value or 0)
        monitor_water_flow(flow_param)
        monitor_total_volume(volume_param)
    except KeyError:
        pass

    # Мониторинг статусов WiFi/GSM
    monitor_network_status()
    
    # Функционал калибровки датчиков
    handle_calibration(params_dict)
    
    # Чтение статуса калибровки из DI-битов датчиков
    try:
        read_calibration_status_direct("PH", "pH")
    except Exception as e:
        logger.error(f"Ошибка чтения статуса калибровки pH: {e}")
        if calibration_prev_states.get("PH", {}).get("watch"):
            update_text_parameter("PH Calibration Status", "Калибровка pH: ошибка чтения статуса")
            calibration_prev_states["PH"]["watch"] = False
            calibration_prev_states["PH"]["state"] = "error"
            calibration_prev_states["PH"]["seen_active"] = False

    try:
        read_calibration_status_direct("EC", "EC")
    except Exception as e:
        logger.error(f"Ошибка чтения статуса калибровки EC: {e}")
        if calibration_prev_states.get("EC", {}).get("watch"):
            update_text_parameter("EC Calibration Status", "Калибровка EC: ошибка чтения статуса")
            calibration_prev_states["EC"]["watch"] = False
            calibration_prev_states["EC"]["state"] = "error"
            calibration_prev_states["EC"]["seen_active"] = False


    # Управление подачей
    handle_feed_timers(params_dict)

    first_run = False


# ─────────────────────────────────────────────────────────────────────────────
#                             Запуск сервиса
# ─────────────────────────────────────────────────────────────────────────────

def run_sync():
    global previous_maintenance_mode
    
    with app.app_context():
        _dispatcher_thread = threading.Thread(target=_max_dispatcher, daemon=True)
        _dispatcher_thread.start()
        last_act = session.query(func.max(Log.timestamp)).scalar()
        last_str = last_act.strftime("%Y-%m-%d %H:%M:%S") if last_act else "—"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        snap = "\n".join(
            f"{p.controlled_parameter_name} = {format_value(p, str(p.value or '0'))}"
            for p in session.query(Parameter).all()
        )

        wifi_text = get_wifi_client_status()
        gsm_state = get_gsm_status_state()
        gsm_text = gsm_state["text"]

        insert_log_message(
            f"Запуск синхронизации: {now_str}\n"
            f"Последняя активность: {last_str}\n"
            f"Сеть:\n"
            f"WiFi: {wifi_text}\n"
            f"GSM: {gsm_text}\n"
            f"Состояние:\n{snap}",
            "INFO"
        )

        while True:
            try:
                poll_parameters()

                mode = get_maintenance_mode_value()

                if mode == "1":
                    skip_due_scenarios("Режим ТО")
                    previous_maintenance_mode = "1"
                else:
                    if previous_maintenance_mode == "1":
                        restore_stateful_scenarios_after_maintenance()

                    execute_scenarios()
                    previous_maintenance_mode = "0"

                check_offline_alarms()

            except Exception as e:
                logger.error(f"Ошибка в основном цикле: {e}", exc_info=True)
                session.rollback()

            time.sleep(1)


if __name__ == "__main__":
    run_sync()
