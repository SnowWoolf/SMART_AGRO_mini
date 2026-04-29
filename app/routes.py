from . import db, login as login_manager
from flask import Blueprint, render_template, flash, redirect, url_for, jsonify, request
from flask_login import current_user, login_user, logout_user, login_required
from .models import User, Parameter, Scenario, ScenarioCycle, Tray, Culture, MixingParameter, Log, DensityRecord, Planting
from .forms import LoginForm, CultureForm
from datetime import datetime, timedelta
from collections import defaultdict
import logging
from functools import wraps
import sqlite3

# === WiFi-адаптер и модем: импорты и определения===
import os
import shutil
import tempfile
import re
import subprocess
import json
import threading
import time
IW_BIN = "/usr/sbin/iw"
WPA_CLI_BIN = "/sbin/wpa_cli"
IP_BIN = "/sbin/ip"
MODEM_CONF_PATH = "/etc/uspd/modem/uspd-modem.conf"
MODEM_SIM_PRIO_PATH = "/etc/uspd/modem/uspd-sim-prio.conf"
MODEM_INFO_PATH = "/run/uspd/modem/modem.info"
ETHERNET_INTERFACES_PATH = "/etc/network/interfaces"
TRAFFIC_STATS_PATH = "/var/lib/agrosmart/traffic_stats.json"
TRAFFIC_POLL_INTERVAL_SEC = 300
_traffic_timer_started = False


# === КАМЕРА: импорты ===
import cv2, glob
import datetime as dt
from flask import send_file
from werkzeug.exceptions import abort

# Для np_from_file
import numpy as np
from typing import Optional

from dotenv import load_dotenv
load_dotenv()  # чтобы os.getenv видел значения из .env при запуске через IDE/uwsgi/gunicorn

from pathlib import Path
from config import DB_NAME


# === КАМЕРА: импорты ===

bp = Blueprint('main', __name__)

# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Декоратор для проверки прав администратора
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('У вас недостаточно прав для выполнения этого действия')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function
    
VERSION_FILE_PATH = Path(__file__).resolve().parent.parent / "version"

def read_firmware_versions():
    result = {
        "software": "Версия ПО не указана",
        "database": DB_NAME,
        "ui": read_ui_version()
    }

    try:
        if not VERSION_FILE_PATH.exists():
            return result

        with open(VERSION_FILE_PATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        if len(lines) >= 1 and lines[0].strip():
            result["software"] = lines[0].strip()

    except Exception:
        pass

    return result
    
MAIN_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "main.html"

def read_ui_version():
    try:
        if not MAIN_TEMPLATE_PATH.exists():
            return "unknown"

        with open(MAIN_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()

        if "UI_VERSION:" in first_line:
            value = first_line.split("UI_VERSION:", 1)[1].strip()

            # убираем закрытие комментария
            value = value.replace("-->", "").strip()

            return value

    except Exception:
        pass

    return "unknown"

# === Настройка WiFi-клиента: функции ===
def read_wifi_conf(path="/etc/smart-wifi/wifi.conf"):
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                    value = value[1:-1]

                data[key] = value
    except FileNotFoundError:
        pass

    return data


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

        print("IW DEV RC:", result.returncode)
        print("IW DEV OUT:", result.stdout)
        print("IW DEV ERR:", result.stderr)

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

        print("AP_IFACE:", ap_iface)
        print("STA_IFACE:", sta_iface)

        return ap_iface, sta_iface

    except Exception as e:
        print("get_wifi_ifaces EXCEPTION:", repr(e))
        return None, None


def get_wifi_client_status() -> str:
    try:
        _, sta_iface = get_wifi_ifaces()

        if not sta_iface:
            return "Адаптер не обнаружен"

        wpa = subprocess.run(
            [WPA_CLI_BIN, "-i", sta_iface, "status"],
            capture_output=True,
            text=True,
            timeout=2
        )

        print("WPA STATUS RC:", wpa.returncode)
        print("WPA STATUS OUT:", wpa.stdout)
        print("WPA STATUS ERR:", wpa.stderr)

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
            return "Подключен, но IP-адрес не получен. Перезагрузите устройство"

        return "Сеть не подключена"

    except Exception as e:
        print("get_wifi_client_status EXCEPTION:", repr(e))
        return "Адаптер не обнаружен"
        
_system_monitor_last_errors = {}


def _log_system_error_once(key, message, cooldown_sec=300):
    now = time.time()
    last = _system_monitor_last_errors.get(key, 0)

    if now - last < cooldown_sec:
        return

    _system_monitor_last_errors[key] = now

    try:
        db.session.add(Log(
            timestamp=datetime.now(),
            level="ERROR",
            message=message
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_disk_usage_percent(path="/"):
    try:
        usage = shutil.disk_usage(path)
        return round((usage.used / usage.total) * 100, 1)
    except Exception:
        return None

def get_ram_usage_percent():
    try:
        data = {}

        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, value = line.split(":", 1)
                data[key] = int(value.strip().split()[0])

        total = data.get("MemTotal")
        available = data.get("MemAvailable")

        if not total or available is None:
            return None

        used = total - available
        return round((used / total) * 100, 1)

    except Exception:
        return None

def get_cpu_temperature():
    paths = [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/class/hwmon/hwmon0/temp1_input",
    ]

    for path in paths:
        try:
            if not os.path.exists(path):
                continue

            with open(path, "r", encoding="utf-8") as f:
                raw = f.read().strip()

            value = float(raw)

            if value > 1000:
                value = value / 1000.0

            return round(value, 1)

        except Exception:
            continue

    return None

def get_cpu_load_percent():
    try:
        load1, _, _ = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        return round((load1 / cpu_count) * 100, 1)
    except Exception:
        return None

def read_system_monitor():
    disk_percent = get_disk_usage_percent("/")
    ram_percent = get_ram_usage_percent()
    cpu_temp = get_cpu_temperature()
    cpu_load = get_cpu_load_percent()

    if disk_percent is not None and disk_percent >= 90:
        _log_system_error_once(
            "disk_usage",
            f"Загрузка постоянной памяти превышает 90%: {disk_percent}%"
        )

    if ram_percent is not None and ram_percent >= 90:
        _log_system_error_once(
            "ram_usage",
            f"Загрузка оперативной памяти превышает 90%: {ram_percent}%"
        )

    return {
        "disk_percent": disk_percent,
        "ram_percent": ram_percent,
        "cpu_temp": cpu_temp,
        "cpu_load": cpu_load,
    }
    
@bp.route('/system_monitor')
@login_required
def system_monitor():
    return jsonify(read_system_monitor())
        
def _read_iface_traffic_bytes(iface):
    base = f"/sys/class/net/{iface}/statistics"
    try:
        with open(os.path.join(base, "rx_bytes"), "r") as f:
            rx = int(f.read().strip())
        with open(os.path.join(base, "tx_bytes"), "r") as f:
            tx = int(f.read().strip())
        return rx + tx
    except Exception:
        return None


def _get_existing_ifaces():
    try:
        return os.listdir("/sys/class/net")
    except Exception:
        return []


def _get_wifi_traffic_ifaces():
    _, sta_iface = get_wifi_ifaces()
    if sta_iface:
        return [sta_iface]

    # fallback
    return [
        i for i in _get_existing_ifaces()
        if i.startswith("wlan") or i.startswith("wlx")
    ]


def _get_traffic_counters():
    ifaces = _get_existing_ifaces()

    ethernet_ifaces = [
        i for i in ifaces
        if i.startswith("eth") or i.startswith("en")
    ]

    wifi_ifaces = _get_wifi_traffic_ifaces()

    gsm_ifaces = [
        i for i in ifaces
        if i.startswith("ppp") or i.startswith("wwan")
    ]

    groups = {
        "ethernet": ethernet_ifaces,
        "wifi": wifi_ifaces,
        "gsm": gsm_ifaces,
    }

    counters = {}

    for group, group_ifaces in groups.items():
        total = 0
        found = False

        for iface in group_ifaces:
            value = _read_iface_traffic_bytes(iface)
            if value is not None:
                total += value
                found = True

        counters[group] = total if found else None

    return counters


def _format_traffic_bytes(value):
    if value is None:
        return "—"

    units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
    size = float(value)

    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "Б":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024


def read_traffic_stats():
    now = datetime.now()
    current_month = now.strftime("%Y-%m")

    first_day = now.replace(day=1)
    prev_month_date = first_day - timedelta(days=1)
    prev_month = prev_month_date.strftime("%Y-%m")

    counters = _get_traffic_counters()

    state = {
        "last_month": current_month,
        "last_counters": {},
        "months": {}
    }

    try:
        if os.path.exists(TRAFFIC_STATS_PATH):
            with open(TRAFFIC_STATS_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
    except Exception:
        pass

    state.setdefault("last_counters", {})
    state.setdefault("months", {})

    # если месяц сменился — начинаем новый месяц с текущих счётчиков
    if state.get("last_month") != current_month:
        state["last_month"] = current_month
        state["last_counters"] = {}

    state["months"].setdefault(current_month, {})
    state["months"].setdefault(prev_month, {})

    for channel, current_counter in counters.items():
        if current_counter is None:
            continue

        last_counter = state["last_counters"].get(channel)

        if last_counter is None:
            delta = 0
        elif current_counter >= last_counter:
            delta = current_counter - last_counter
        else:
            # счётчик интерфейса сбросился после перезагрузки
            delta = current_counter

        state["months"][current_month][channel] = (
            int(state["months"][current_month].get(channel, 0)) + int(delta)
        )

        state["last_counters"][channel] = current_counter

    # храним только последние 3 месяца
    keep_months = sorted(state["months"].keys())[-3:]
    state["months"] = {m: state["months"][m] for m in keep_months}

    try:
        os.makedirs(os.path.dirname(TRAFFIC_STATS_PATH), exist_ok=True)
        with open(TRAFFIC_STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Не удалось сохранить статистику трафика: %s", e)

    labels = {
        "ethernet": "Ethernet",
        "wifi": "WiFi",
        "gsm": "GSM"
    }

    result = []

    for channel in ("ethernet", "wifi", "gsm"):
        result.append({
            "name": labels[channel],
            "current_month": _format_traffic_bytes(
                state["months"].get(current_month, {}).get(channel)
            ),
            "previous_month": _format_traffic_bytes(
                state["months"].get(prev_month, {}).get(channel)
            )
        })

    return result
    
def traffic_stats_worker():
    logger.info("Фоновый сбор статистики трафика запущен")

    while True:
        try:
            read_traffic_stats()
        except Exception as e:
            logger.warning("Ошибка фонового сбора трафика: %s", e)

        time.sleep(TRAFFIC_POLL_INTERVAL_SEC)


def start_traffic_stats_worker():
    global _traffic_timer_started

    if _traffic_timer_started:
        return

    _traffic_timer_started = True

    thread = threading.Thread(
        target=traffic_stats_worker,
        daemon=True
    )
    thread.start()
        
# === КАМЕРА: вспомогалки ===
def _abs(p: str) -> str:
    # не требует существования пути
    return str(Path(p).expanduser().resolve(strict=False))

def _cam_save_dir(cam: Optional[int] = None):
    if cam:
        env = os.getenv(f"CAMERA_SAVE_DIR_{cam}")
        if env:
            return _abs(env)
        base = os.getenv("CAMERA_SAVE_DIR", "./camera_archive")
        return _abs(os.path.join(base, f"cam{cam}"))
    return _abs(os.getenv("CAMERA_SAVE_DIR", "./camera_archive"))

def _cam_tmp_dir():
    return _abs(os.getenv("CAMERA_TIMELAPSE_TMP", "./tmp"))

def _cam_rtsp(cam: Optional[int] = None) -> str:
    if cam:
        env = os.getenv(f"CAMERA_RTSP_URL_{cam}")
        if env:
            return env
    return os.getenv("CAMERA_RTSP_URL", "rtsp://admin:admin123@192.168.202.229:554/live/ch00_0")

def _cam_max_w():
    return int(os.getenv("CAMERA_MAX_PREVIEW_W", "1280"))

def _cam_jpeg_q():
    return int(os.getenv("CAMERA_JPEG_QUALITY", "90"))

def _cam_codec():
    return os.getenv("CAMERA_TIMELAPSE_CODEC", "mp4v")

def _now():
    return dt.datetime.now()

def _ts_to_name(ts: dt.datetime) -> str:
    return ts.strftime("%Y%m%d_%H%M%S") + f"{int(ts.microsecond/1000):03d}.jpg"

def _name_to_ts(fname: str):
    base = os.path.basename(fname)
    stem, ext = os.path.splitext(base)
    if ext.lower() != ".jpg":
        return None
    try:
        date_part, time_part = stem.split("_")
        sec_dt = dt.datetime.strptime(date_part + "_" + time_part[:6], "%Y%m%d_%H%M%S")
        ms = int(time_part[6:9]) if len(time_part) >= 9 else 0
        return sec_dt + dt.timedelta(milliseconds=ms)
    except Exception:
        return None

def _latest_image_path(cam: Optional[int] = None):
    files = sorted(glob.glob(os.path.join(_cam_save_dir(cam), "*.jpg")))
    return files[-1] if files else None

def _find_nearest_image(target: dt.datetime, cam: Optional[int] = None):
    files = sorted(glob.glob(os.path.join(_cam_save_dir(cam), "*.jpg")))
    best, best_delta = None, None
    for p in files:
        ts = _name_to_ts(p)
        if not ts:
            continue
        delta = abs((ts - target).total_seconds())
        if best is None or delta < best_delta:
            best, best_delta = p, delta
    return best

def _list_between(start_dt: dt.datetime, end_dt: dt.datetime, cam: Optional[int] = None):
    files = sorted(glob.glob(os.path.join(_cam_save_dir(cam), "*.jpg")))
    res = []
    for p in files:
        ts = _name_to_ts(p)
        if ts and start_dt <= ts <= end_dt:
            res.append(p)
    return res

def _parse_dt_local(s: str) -> dt.datetime:
    if "T" not in s:
        raise ValueError("Invalid datetime-local")
    # 2025-09-08T11:30[:SS]
    try:
        if len(s) == 16:
            return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M")
        elif len(s) == 19:
            return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        else:
            return dt.datetime.fromisoformat(s)
    except Exception:
        return dt.datetime.fromisoformat(s)

def _save_frame(frame, cam: Optional[int] = None) -> str:
    out_dir = Path(_cam_save_dir(cam))
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = _now()
    fname = _ts_to_name(ts)
    path = out_dir / fname
    tmp  = out_dir / (fname + ".part")

    # ресайз
    h, w = frame.shape[:2]
    max_w = max(1, _cam_max_w())
    if w > max_w:
        scale = max_w / float(w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    # безопасная запись через imencode + os.replace (устойчиво к кириллице/пробелам)
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), _cam_jpeg_q()])
    if not ok:
        abort(500, description="Не удалось закодировать кадр в JPEG")

    try:
        with open(tmp, "wb") as f:
            f.write(buf.tobytes())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try: tmp.unlink()
            except Exception:
                pass

    if not path.exists():
        abort(500, description=f"Файл не появился на диске: {path}")

    return str(path)

def _np_from_file(path: str):
    with open(path, "rb") as f:
        data = f.read()
    return np.frombuffer(data, dtype=np.uint8)

def _build_timelapse(files, fps: int, out_path: str) -> bool:
    if not files:
        return False
    first = cv2.imdecode(_np_from_file(files[0]), cv2.IMREAD_COLOR)
    if first is None:
        return False
    h, w = first.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*_cam_codec())
    vw = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
    if not vw.isOpened():
        return False
    try:
        vw.write(first)
        for p in files[1:]:
            img = cv2.imdecode(_np_from_file(p), cv2.IMREAD_COLOR)
            if img is None:
                continue
            if img.shape[1] != w or img.shape[0] != h:
                img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
            vw.write(img)
    finally:
        vw.release()
    return True

def get_parameter_value_by_name(name, default=''):
    p = Parameter.query.filter_by(controlled_parameter_name=name).first()
    if not p:
        return default

    value = p.value
    if isinstance(value, bytes):
        value = value.decode('utf-8')
    return value
    
def _ui_group_icon(group_name: str) -> str:
    icons = {
        "Управление общее": "🧩",
        "Управление поливом": "💧",
        "Управление освещением": "💡",
    }
    return icons.get(group_name, "⚙️")

def _ui_item_icon(param_name: str, register_type: str) -> str:
    name = (param_name or "").lower()

    # Сначала иконки по смыслу имени
    if "насос" in name:
        return "🔄"
    if "перемеш" in name:
        return "🌀"
    if "режим" in name:
        return "🛠️"
    if "свет" in name:
        return "💡"
    if "яркость" in name:
        return "🌗"
    if "канал" in name:
        return "🔌"
    if "полка" in name or "стеллаж" in name:
        return "🚿"
    if "охлаждение" in name:
        return "❄️"
    if "увлажн" in name:
        return "💨"

    # Потом fallback по типу регистра
    if str(register_type) == "1":
        return "⏻"
    if str(register_type) == "3":
        return "🔢"

    return "⚙️"

def build_control_groups(params):
    allowed_groups = [
        "Управление общее",
        "Управление поливом",
        "Управление освещением",
    ]

    groups = {
        group_name: {
            "title": group_name,
            "icon": _ui_group_icon(group_name),
            "items": []
        }
        for group_name in allowed_groups
    }

    for p in params:
        register_name = (p.register_name or "").strip()
        operation_type = (p.operation_type or "").strip()
        register_type = str(p.register_type or "").strip()
        param_name = (p.controlled_parameter_name or "").strip()

        if not param_name:
            continue

        # manual не выводим сюда
        if register_name == "manual":
            continue

        # только нужные разделы
        if register_name not in groups:
            continue

        # только чтение/запись
        normalized_op = operation_type.lower().replace(" ", "")
        if normalized_op != "чтение/запись":
            continue

        # только кнопка или поле значения
        if register_type not in ("1", "3"):
            continue

        limits = _parse_acceptable_values(p.acceptable_values)

        groups[register_name]["items"].append({
            "name": param_name,
            "value": p.value or "0",
            "register_type": register_type,
            "icon": _ui_item_icon(param_name, register_type),
            "value_class": _ui_value_class(param_name),
            "min_value": limits["min"],
            "max_value": limits["max"],
            "step_value": limits["step"],
        })

    # сортировка по имени
    for group in groups.values():
        group["items"].sort(key=lambda x: x["name"].lower())

    return groups

def _parse_acceptable_values(raw: str):
    s = (raw or "").strip()

    # по умолчанию
    result = {"min": 0, "max": 100, "step": 1}

    if not s:
        return result

    # например: "1 - 100", "10 - 6000", "0 или 1"
    nums = re.findall(r'-?\d+(?:[.,]\d+)?', s)
    nums = [float(x.replace(',', '.')) for x in nums]

    if len(nums) >= 2:
        result["min"] = nums[0]
        result["max"] = nums[1]
    elif len(nums) == 1:
        result["min"] = 0
        result["max"] = nums[0]

    # если есть дроби — шаг 0.1, иначе 1
    if any(float(x) != int(float(x)) for x in nums):
        result["step"] = 0.1

    return result

def _ui_value_class(param_name: str) -> str:
    name = (param_name or "").lower()

    if "синий" in name or "blue" in name:
        return "light-level-blue"
    if "красный" in name or "red" in name:
        return "light-level-red"
    if "white" in name or "белый" in name:
        return "light-level-white"
    if "fr" in name or "дальний красный" in name:
        return "light-level-fr"

    return ""

@bp.route('/')
@bp.route('/index')
@login_required
def index():
    parameters = Parameter.query.all()

    parameters_dict = {}
    for param in parameters:
        key = param.controlled_parameter_name
        if isinstance(key, bytes):
            key = key.decode('utf-8')

        value = param.value
        if isinstance(value, bytes):
            value = value.decode('utf-8')

        parameters_dict[key] = value

    control_groups = build_control_groups(parameters)

    logs_info = Log.query.filter(Log.level == 'INFO').order_by(Log.timestamp.desc()).all()
    logs_errors = Log.query.filter(Log.level == 'ERROR').order_by(Log.timestamp.desc()).all()
    records = DensityRecord.query.order_by(DensityRecord.timestamp.desc()).all()
    time_adjustment = timedelta(hours=3)

    return render_template(
        'main.html',
        parameters=parameters,
        parameters_dict=parameters_dict,
        control_groups=control_groups,
        logs_info=logs_info,
        logs_errors=logs_errors,
        records=records,
        timedelta=time_adjustment,
        title='Главная'
    )

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Неверный логин или пароль')
            return redirect(url_for('main.login'))
        login_user(user)
        return redirect(url_for('main.index'))
    return render_template(
        'login.html',
        title='Sign In',
        form=form,
        firmware_versions=read_firmware_versions()
    )

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))
#    return redirect(url_for('main.login'))

# Вспомогательные функции для нового конструктора сценариев:
def _decode_value(value):
    if isinstance(value, bytes):
        return value.decode('utf-8')
    return value


def _get_constructor_parameters():
    params = Parameter.query.with_entities(
        Parameter.controlled_parameter_name,
        Parameter.scenario_belonging,
        Parameter.acceptable_values
    ).all()

    groups = {
        "Полив": [],
        "Свет": [],
        "Свет уровень": []
    }

    for name, belonging, acceptable_values in params:
        name = (_decode_value(name) or "").strip()
        belonging = (_decode_value(belonging) or "").strip()
        acceptable_values = (_decode_value(acceptable_values) or "").strip()

        if not name:
            continue

        if belonging in groups:
            groups[belonging].append({
                "name": name,
                "acceptable_values": acceptable_values
            })

    for key in groups:
        groups[key].sort(key=lambda x: x["name"].lower())

    return groups


def _parse_hhmm(value):
    return datetime.strptime(value, "%H:%M").time()


def _seconds_to_time(base_time, add_seconds):
    base_dt = datetime.combine(datetime.today(), base_time)
    result_dt = base_dt + timedelta(seconds=add_seconds)
    return result_dt.time()


def _generate_scenarios_for_cycle(cycle):
    steps = json.loads(cycle.steps_json or "[]")

    start_time = _parse_hhmm(cycle.first_time)
    period_minutes = int(cycle.period_minutes)

    if period_minutes < 0:
        raise ValueError("Период не может быть отрицательным")

    generated = []

    first_start_dt = datetime.combine(datetime.today(), start_time)
    day_start_dt = datetime.combine(datetime.today(), datetime.min.time())

    def add_cycle_steps(cycle_start_dt):
        offset_sec = 0

        for step_index, step in enumerate(steps):
            delay_sec = int(step.get("delay_sec", 0) or 0)
            offset_sec += delay_sec

            event_dt = cycle_start_dt + timedelta(seconds=offset_sec)

            # ВАЖНО:
            # если событие ушло за 24:00, переносим его в начало суток.
            seconds_from_day_start = int((event_dt - day_start_dt).total_seconds())
            normalized_seconds = seconds_from_day_start % 86400

            event_time = (
                day_start_dt + timedelta(seconds=normalized_seconds)
            ).time().replace(microsecond=0)

            generated.append(Scenario(
                type=cycle.cycle_type,
                time=event_time,
                parameter=str(step.get("parameter", "")).strip(),
                value=str(step.get("value", "")).strip(),
                result="",
                last_execution=datetime.now() - timedelta(days=1),
                cycle_id=cycle.id,
                cycle_step_index=step_index
            ))

    if period_minutes == 0:
        add_cycle_steps(first_start_dt)
        return generated

    cycle_start_dt = first_start_dt

    while (cycle_start_dt - day_start_dt).total_seconds() < 86400:
        add_cycle_steps(cycle_start_dt)
        cycle_start_dt += timedelta(minutes=period_minutes)

    return generated


def _regenerate_scenarios_for_cycle(cycle):
    Scenario.query.filter_by(cycle_id=cycle.id).delete()

    if cycle.enabled:
        rows = _generate_scenarios_for_cycle(cycle)
        for row in rows:
            db.session.add(row)

# Вспомогательные функции для импорта-экспорта БД
def is_sqlite_file(path):
    try:
        with open(path, 'rb') as f:
            header = f.read(16)
        return header.startswith(b'SQLite format 3')
    except:
        return False


def can_open_sqlite(path):
    try:
        conn = sqlite3.connect(path)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1;")
        conn.close()
        return True
    except:
        return False


def get_tables(path):
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table'
        AND name NOT LIKE 'sqlite_%'
    """)

    tables = sorted([row[0] for row in cur.fetchall()])
    conn.close()
    return tables


def compare_db_structure(old_db, new_db):
    try:
        return set(get_tables(old_db)) == set(get_tables(new_db))
    except Exception:
        return False
        
def update_config_db_name(db_name):
    from config import DB_PATH

    project_dir = os.path.dirname(DB_PATH)
    config_path = os.path.join(project_dir, "config.py")

    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = re.sub(
        r'DB_NAME\s*=\s*os\.getenv\("DB_NAME",\s*"[^"]*"\)',
        f'DB_NAME = os.getenv("DB_NAME", "{db_name}")',
        content
    )

    if new_content == content:
        raise RuntimeError("Не удалось найти строку DB_NAME в config.py")

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def is_service_active(service_name):
    result = subprocess.run(
        ["/bin/systemctl", "is-active", service_name],
        capture_output=True,
        text=True,
        timeout=10
    )
    return result.stdout.strip() == "active"


def restart_service_and_wait(service_name, timeout_sec=30):
    subprocess.run(
        ["/bin/systemctl", "restart", service_name],
        capture_output=True,
        text=True,
        timeout=30
    )

    for _ in range(timeout_sec):
        if is_service_active(service_name):
            return True
        time.sleep(1)

    return False
    
def cleanup_old_dbs(project_dir, current_db_name, keep_old=3):
    current_db_path = os.path.join(project_dir, current_db_name)

    db_files = []
    for name in os.listdir(project_dir):
        if not name.endswith(".db"):
            continue

        path = os.path.join(project_dir, name)

        if os.path.abspath(path) == os.path.abspath(current_db_path):
            continue

        if not os.path.isfile(path):
            continue

        db_files.append(path)

    db_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    for path in db_files[keep_old:]:
        try:
            os.remove(path)
        except Exception as e:
            logger.warning("Не удалось удалить старую БД %s: %s", path, e)


@bp.route('/scenarios')
@login_required
def scenarios():
    irrigation_scenarios = Scenario.query.filter_by(type='Полив').order_by(Scenario.time).all()
    light_scenarios = Scenario.query.filter_by(type='Свет').order_by(Scenario.time).all()
    return render_template('scenarios.html',
                           irrigation_scenarios=irrigation_scenarios,
                           light_scenarios=light_scenarios,
                           title='Сценарии')
                           
@bp.route('/scenario_constructor')
@login_required
def scenario_constructor():
    return render_template(
        'scenario_constructor.html',
        title='Конструктор сценариев'
    )
    
@bp.route('/scenario_constructor/data')
@login_required
def scenario_constructor_data():
    cycles = ScenarioCycle.query.order_by(ScenarioCycle.name).all()
    parameter_groups = _get_constructor_parameters()

    return jsonify({
        "cycles": [
            {
                "id": c.id,
                "name": c.name,
                "cycle_type": c.cycle_type,
                "first_time": c.first_time,
                "period_minutes": c.period_minutes,
                "enabled": c.enabled,
                "steps": json.loads(c.steps_json or "[]")
            }
            for c in cycles
        ],
        "parameters": parameter_groups
    })
    
@bp.route('/scenario_constructor/save_cycle', methods=['POST'])
@login_required
def save_cycle():
    if current_user.username != "admin" and current_user.role != "admin":
        return jsonify({"success": False, "error": "Недостаточно прав"}), 403

    data = request.get_json(force=True)

    cycle_id = data.get("id")
    name = str(data.get("name", "")).strip()
    cycle_type = str(data.get("cycle_type", "Полив")).strip()
    first_time = str(data.get("first_time", "")).strip()
    period_minutes = int(data.get("period_minutes", 0) or 0)
    enabled = bool(data.get("enabled", True))
    steps = data.get("steps", [])

    if not name:
        return jsonify({"success": False, "error": "Не указано имя цикла"}), 400

    if cycle_type not in ("Полив", "Свет", "Свет уровень"):
        return jsonify({"success": False, "error": "Некорректный тип цикла"}), 400

    try:
        datetime.strptime(first_time, "%H:%M")
    except ValueError:
        return jsonify({"success": False, "error": "Некорректное время первого запуска"}), 400

    if period_minutes < 0 or period_minutes > 1440:
        return jsonify({"success": False, "error": "Период должен быть от 0 до 1440 минут"}), 400

    if not steps:
        return jsonify({"success": False, "error": "В цикле нет шагов"}), 400

    for i, step in enumerate(steps):
        if not str(step.get("parameter", "")).strip():
            return jsonify({"success": False, "error": f"В шаге {i + 1} не выбран параметр"}), 400

        try:
            delay_sec = int(step.get("delay_sec", 0) or 0)
        except ValueError:
            return jsonify({"success": False, "error": f"Некорректная задержка в шаге {i + 1}"}), 400

        if delay_sec < 0:
            return jsonify({"success": False, "error": f"Задержка в шаге {i + 1} не может быть отрицательной"}), 400

        step["delay_sec"] = delay_sec
        step["parameter"] = str(step.get("parameter", "")).strip()
        step["value"] = str(step.get("value", "")).strip()

    try:
        if cycle_id:
            cycle = ScenarioCycle.query.get(int(cycle_id))
            if not cycle:
                return jsonify({"success": False, "error": "Цикл не найден"}), 404
        else:
            cycle = ScenarioCycle()
            db.session.add(cycle)

        cycle.name = name
        cycle.cycle_type = cycle_type
        cycle.first_time = first_time
        cycle.period_minutes = period_minutes
        cycle.enabled = enabled
        cycle.steps_json = json.dumps(steps, ensure_ascii=False)
        cycle.updated_at = datetime.utcnow()

        db.session.flush()

        _regenerate_scenarios_for_cycle(cycle)

        db.session.commit()

        return jsonify({"success": True, "id": cycle.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
        
@bp.route('/scenario_constructor/delete_cycle', methods=['POST'])
@login_required
def delete_cycle():
    if current_user.username != "admin" and current_user.role != "admin":
        return jsonify({"success": False, "error": "Недостаточно прав"}), 403

    data = request.get_json(force=True)
    cycle_id = data.get("id")

    cycle = ScenarioCycle.query.get(cycle_id)
    if not cycle:
        return jsonify({"success": False, "error": "Цикл не найден"}), 404

    try:
        db.session.delete(cycle)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@bp.route('/scenario_parameters')
@login_required
def scenario_parameters():
    params = Parameter.query.with_entities(
        Parameter.controlled_parameter_name,
        Parameter.scenario_belonging
    ).all()

    # Готовим словарь списков
    groups = {
        'Полив': [],
        'Свет': [],
        'Свет уровень': []
    }

    for name, belong in params:
        # на всякий случай декодируем bytes
        if isinstance(name, bytes):
            name = name.decode('utf-8')
        if isinstance(belong, bytes):
            belong = belong.decode('utf-8')
        if belong in groups:
            groups[belong].append(name)

    # Отдадим фронту ровно то, что ему нужно
    return jsonify({
        'poliv': groups['Полив'],
        'svet': groups['Свет'],
        'svet_level': groups['Свет уровень']
    })


@bp.route('/add_scenario', methods=['POST'])
@login_required
def add_scenario():
    data = request.get_json()
    scenario_time = datetime.strptime(data['time'], '%H:%M').time()
    new_scenario = Scenario(
        type=data['type'],
        time=scenario_time,
        parameter=data['parameter'],
        value=data['value'],
        result='',
        last_execution=datetime.now() - timedelta(days=1)
    )
    db.session.add(new_scenario)
    db.session.commit()
    return jsonify(success=True)

@bp.route('/delete_scenario', methods=['POST'])
@login_required
def delete_scenario():
    data = request.get_json()
    scenario = Scenario.query.get(data['id'])
    if scenario:
        db.session.delete(scenario)
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 400

@bp.route('/get_parameters')
@login_required
def get_parameters():
    parameters = Parameter.query.all()
    parameters_dict = {}
    for param in parameters:
        key = param.controlled_parameter_name
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        value = param.value
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        parameters_dict[key] = value
    if parameters and parameters[0].value_date:
        parameters_dict['дата'] = parameters[0].value_date.strftime('%d.%m.%Y %H:%M:%S')
    return jsonify(parameters_dict)

@bp.route('/toggle_parameter', methods=['POST'])
@login_required
def toggle_parameter():
    data = request.get_json()
    parameter_name = data.get('parameter')
    parameter = Parameter.query.filter_by(controlled_parameter_name=parameter_name).first()
    if parameter:
        parameter.value = '0' if parameter.value == '1' else '1'
        parameter.value_date = datetime.now()
        db.session.commit()
    return jsonify({'status': 'success'})

@bp.route('/set_parameter_value', methods=['POST'])
@login_required
def set_parameter_value():
    data = request.get_json()
    parameter_name = data['parameter']
    parameter_value = data['value']
    parameter = Parameter.query.filter_by(controlled_parameter_name=parameter_name).first()
    if parameter:
        parameter.value = parameter_value
        parameter.value_date = datetime.now()
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 400

@bp.route('/cultures')
@login_required
def cultures():
    cultures = Culture.query.all()
    form = CultureForm()
    return render_template('cultures.html', cultures=cultures, form=form, title='Справочник культур')

@bp.route('/save_culture', methods=['POST'])
@login_required
def save_culture():
    form = CultureForm()
    if form.validate_on_submit():
        culture_id = request.form.get('culture_id')
        if culture_id:
            culture = Culture.query.get(culture_id)
            if culture:
                culture.name = form.name.data
                culture.sprouting_in_chamber_days = form.sprouting_in_chamber_days.data
                culture.sprouting_on_shelf_days = form.sprouting_on_shelf_days.data
                culture.seedling_days = form.seedling_days.data
                culture.pots_at_sprouting = form.pots_at_sprouting.data
                culture.pots_at_seedling = form.pots_at_seedling.data
                culture.pots_at_main_stage = form.pots_at_main_stage.data
                culture.min_days_from_planting = form.min_days_from_planting.data
                culture.min_weight_from_planting = form.min_weight_from_planting.data
                culture.max_days_from_planting = form.max_days_from_planting.data
                culture.max_weight_from_planting = form.max_weight_from_planting.data
                culture.min_days_from_cutting = form.min_days_from_cutting.data
                culture.min_weight_from_cutting = form.min_weight_from_cutting.data
                culture.max_days_from_cutting = form.max_days_from_cutting.data
                culture.max_weight_from_cutting = form.max_weight_from_cutting.data
            else:
                flash('Культура не найдена.', 'error')
                return redirect(url_for('main.cultures'))
        else:
            new_culture = Culture(
                name=form.name.data,
                sprouting_in_chamber_days=form.sprouting_in_chamber_days.data,
                sprouting_on_shelf_days=form.sprouting_on_shelf_days.data,
                seedling_days=form.seedling_days.data,
                pots_at_sprouting=form.pots_at_sprouting.data,
                pots_at_seedling=form.pots_at_seedling.data,
                pots_at_main_stage=form.pots_at_main_stage.data,
                min_days_from_planting=form.min_days_from_planting.data,
                min_weight_from_planting=form.min_weight_from_planting.data,
                max_days_from_planting=form.max_days_from_planting.data,
                max_weight_from_planting=form.max_weight_from_planting.data,
                min_days_from_cutting=form.min_days_from_cutting.data,
                min_weight_from_cutting=form.min_weight_from_cutting.data,
                max_days_from_cutting=form.max_days_from_cutting.data,
                max_weight_from_cutting=form.max_weight_from_cutting.data
            )
            db.session.add(new_culture)
        db.session.commit()
        flash('Культура успешно сохранена!', 'success')
    else:
        flash('Ошибка при сохранении культуры. Пожалуйста, проверьте введенные данные.', 'error')
    return redirect(url_for('main.cultures'))

@bp.route('/get_culture/<int:culture_id>')
@login_required
def get_culture(culture_id):
    culture = Culture.query.get(culture_id)
    if culture:
        return jsonify({
            'culture_id': culture.culture_id,
            'name': culture.name,
            'sprouting_in_chamber_days': culture.sprouting_in_chamber_days,
            'sprouting_on_shelf_days': culture.sprouting_on_shelf_days,
            'seedling_days': culture.seedling_days,
            'pots_at_sprouting': culture.pots_at_sprouting,
            'pots_at_seedling': culture.pots_at_seedling,
            'pots_at_main_stage': culture.pots_at_main_stage,
            'min_days_from_planting': culture.min_days_from_planting,
            'min_weight_from_planting': culture.min_weight_from_planting,
            'max_days_from_planting': culture.max_days_from_planting,
            'max_weight_from_planting': culture.max_weight_from_planting,
            'min_days_from_cutting': culture.min_days_from_cutting,
            'min_weight_from_cutting': culture.min_weight_from_cutting,
            'max_days_from_cutting': culture.max_days_from_cutting,
            'max_weight_from_cutting': culture.max_weight_from_cutting
        })
    return jsonify({'error': 'Культура не найдена'}), 404

@bp.route('/delete_culture/<int:culture_id>', methods=['POST'])
@login_required
def delete_culture(culture_id):
    culture = Culture.query.get(culture_id)
    if culture:
        db.session.delete(culture)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Культура не найдена'}), 404

@bp.route('/mixing_parameters')
@login_required
def mixing_parameters():
    mixing_params = MixingParameter.query.first()

    calibration_params = {
        'ph_buffer_1': get_parameter_value_by_name('ph_buffer_1', ''),
        'ph_buffer_2': get_parameter_value_by_name('ph_buffer_2', ''),
        'ph_calibration_status': get_parameter_value_by_name('PH Calibration Status', 'Не выполнялась'),
        'ph_calibration_updated': get_parameter_value_by_name('PH Calibration Updated', '—'),

        'ec_calibration_temperature': get_parameter_value_by_name('ec_calibration_temperature', ''),
        'ec_solution_1': get_parameter_value_by_name('ec_solution_1', ''),
        'ec_solution_2': get_parameter_value_by_name('ec_solution_2', ''),
        'ec_calibration_status': get_parameter_value_by_name('EC Calibration Status', 'Не выполнялась'),
        'ec_calibration_updated': get_parameter_value_by_name('EC Calibration Updated', '—'),
    }

    wifi_client = None
    conf_path = "/etc/smart-wifi/wifi.conf"
    wifi_available = os.path.exists(conf_path)

    if os.path.exists(conf_path):
        wifi_conf = read_wifi_conf(conf_path)
        wifi_client = {
            "status": get_wifi_client_status(),
            "sta_enabled": wifi_conf.get("STA_ENABLED", "0") == "1",
            "sta_ssid": wifi_conf.get("STA_SSID", ""),
            "sta_psk": wifi_conf.get("STA_PSK", ""),
            "sta_hidden": wifi_conf.get("STA_HIDDEN", "0") == "1",
        }

    parameters_dict = {}
    for p in Parameter.query.all():
        key = p.controlled_parameter_name
        value = p.value

        if isinstance(key, bytes):
            key = key.decode("utf-8")
        if isinstance(value, bytes):
            value = value.decode("utf-8")

        parameters_dict[key] = value
        
    return render_template(
        'mixing_parameters.html',
        mixing_params=mixing_params,
        calibration_params=calibration_params,
        wifi_client=wifi_client,
        wifi_available=wifi_available,
        modem_state=read_modem_state() or {},
        modem_config=read_modem_config() or {},
        firmware_versions=read_firmware_versions(),
        traffic_stats=read_traffic_stats(),
        ethernet_config=read_ethernet_config(),
        system_monitor=read_system_monitor(),
        parameters_dict=parameters_dict,
        title='Параметры'
       )

@bp.route('/update_mixing_parameter', methods=['POST'])
@login_required
def update_mixing_parameter():
    data = request.get_json()
    parameter_name = data.get('parameter_name')
    parameter_value = data.get('parameter_value')
    if not parameter_name or parameter_value is None:
        return jsonify({'error': 'Неверные данные'}), 400
    try:
        mixing_param = MixingParameter.query.first()
        if not mixing_param:
            return jsonify({'error': 'Параметры не найдены'}), 404
        valid_parameters = [
            'target_ec', 'target_ph', 'ec_deviation', 'ph_deviation',
            'mixing_speed', 'stabilization_time', 'pump_flow_rate',
            'density_a', 'density_b', 'density_acid', 'tank_volume',
            'bf', 'maxtime'
        ]
        if parameter_name in valid_parameters:
            new_value = float(parameter_value)
            setattr(mixing_param, parameter_name, new_value)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'error': 'Неверное имя параметра'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error("Ошибка обновления mixing_parameter: %s", e)
        return jsonify({'error': str(e)}), 500
        
# Функционал калибровки датчиков PH и EC из веб-интерфейса - запись параметров буферных растворов 
@bp.route('/update_calibration_parameter', methods=['POST'])
@login_required
def update_calibration_parameter():
    try:
        import minimalmodbus

        data = request.get_json()
        name = data.get('parameter_name')
        value = data.get('parameter_value')

        if not name:
            return jsonify({"error": "No parameter_name"}), 400

        p = Parameter.query.filter_by(controlled_parameter_name=name).first()
        if not p:
            return jsonify({"error": f"Parameter {name} not found"}), 404

        # helper для записи Modbus
        def write_modbus_param(param_obj, human_value):
            inst = minimalmodbus.Instrument(str(param_obj.com), int(param_obj.network_address), mode=minimalmodbus.MODE_RTU)
            inst.serial.baudrate = int(param_obj.speed)
            inst.serial.timeout = float(getattr(param_obj, "timeout", 1.0) or 1.0)
            inst.serial.bytesize = 8
            inst.serial.parity = minimalmodbus.serial.PARITY_NONE
            inst.serial.stopbits = 1
            inst.handle_local_echo = True

            k = float(param_obj.K) if param_obj.K else 1.0
            raw = int(float(human_value) * k)

            if str(param_obj.register_type) == "1":
                inst.write_bit(int(param_obj.register_number), raw, functioncode=5)
            elif str(param_obj.register_type) == "3":
                inst.write_register(int(param_obj.register_number), raw, functioncode=6)
            else:
                raise ValueError(f"Unsupported register_type {param_obj.register_type} for {param_obj.controlled_parameter_name}")

        # pH растворы
        if name in ("ph_buffer_1", "ph_buffer_2"):
            unlock = Parameter.query.filter_by(controlled_parameter_name="PH_CALC_SAVE").first()
            if not unlock:
                return jsonify({"error": "PH_CALC_SAVE not found"}), 500

            write_modbus_param(unlock, 0x2709)
            write_modbus_param(p, value)

        # EC растворы
        elif name in ("ec_solution_1", "ec_solution_2"):
            unlock = Parameter.query.filter_by(controlled_parameter_name="EC_CALC_SAVE").first()
            if not unlock:
                return jsonify({"error": "EC_CALC_SAVE not found"}), 500

            write_modbus_param(unlock, 0x2709)
            write_modbus_param(p, value)

        # температура EC
        elif name == "ec_calibration_temperature":
            write_modbus_param(p, value)

        else:
            return jsonify({"error": f"Unsupported calibration parameter: {name}"}), 400

        # Только если Modbus-запись прошла успешно — обновляем БД
        p.value = str(value)
        p.value_date = datetime.now()
        db.session.commit()

        return jsonify({"status": "ok"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# Функционал калибровки датчиков PH и EC из веб-интерфейса - кнопка запуска калибровки
@bp.route('/start_sensor_calibration', methods=['POST'])
@login_required
def start_sensor_calibration():
    try:
        data = request.get_json()
        sensor_type = data.get('sensor_type')

        if sensor_type not in ('ph', 'ec'):
            return jsonify({'error': 'invalid sensor_type'}), 400

        now = datetime.now()

        if sensor_type == 'ph':
            start_name = 'PH Calibration Start'
            status_name = 'PH Calibration Status'
            updated_name = 'PH Calibration Updated'
        else:
            start_name = 'EC Calibration Start'
            status_name = 'EC Calibration Status'
            updated_name = 'EC Calibration Updated'

        start_param = Parameter.query.filter_by(controlled_parameter_name=start_name).first()
        status_param = Parameter.query.filter_by(controlled_parameter_name=status_name).first()

        if not start_param or not status_param:
            return jsonify({'error': 'Calibration parameters not found'}), 404

        start_param.value = '1'
        start_param.value_date = now

        status_param.value = 'Выполняется'
        status_param.value_date = now

        db.session.commit()

        return jsonify({'success': True, 'status': f'{sensor_type} calibration started'})

    except Exception as e:
        db.session.rollback()
        logger.error("Ошибка start_sensor_calibration: %s", e)
        return jsonify({'error': str(e)}), 500 

def get_tray_status(tray, date):
    if not tray or not tray.culture_id or not tray.sprouting_date:
        status = 'пуст'
        background_image = url_for('static', filename='images/empty.jpg')
        return {'status': status, 'backgroundImage': background_image}
    if tray.harvest_date:
        cut_status = 'С'
        min_days = tray.culture.min_days_from_cutting
        max_days = tray.culture.max_days_from_cutting
        min_weight = tray.culture.min_weight_from_cutting
        max_weight = tray.culture.max_weight_from_cutting
        start_date = tray.harvest_date
    else:
        cut_status = 'М'
        min_days = tray.culture.min_days_from_planting
        max_days = tray.culture.max_days_from_planting
        min_weight = tray.culture.min_weight_from_planting
        max_weight = tray.culture.max_weight_from_planting
        start_date = tray.sprouting_date
    min_ready_date = start_date + timedelta(days=min_days)
    max_ready_date = start_date + timedelta(days=max_days)
    if date < min_ready_date:
        days_to_min_ready = (min_ready_date - date).days
        growth_stage = (tray.growth_stage[0].upper() if tray.growth_stage else '')
        status = f"{cut_status} {tray.culture.name} {days_to_min_ready}д. ({growth_stage})"
        background_image = url_for('static', filename='images/growing.jpg')
    elif min_ready_date <= date <= max_ready_date:
        total_days = (max_ready_date - min_ready_date).days
        days_into_period = (date - min_ready_date).days
        weight = min_weight + ((max_weight - min_weight) * days_into_period / total_days) if total_days > 0 else max_weight
        total_weight = weight * tray.pots_planted / 1000
        status = f"{cut_status} {tray.culture.name} {total_weight:.1f}кг"
        background_image = url_for('static', filename='images/ready.jpg')
    elif date > max_ready_date:
        days_over = (date - max_ready_date).days
        status = f"{cut_status} {tray.culture.name} -{days_over}д."
        background_image = url_for('static', filename='images/overgrown.png')
    else:
        status = 'ошибка'
        background_image = url_for('static', filename='images/error.png')
    return {'status': status, 'backgroundImage': background_image}

@bp.route('/plantings')
@login_required
def plantings():
    plantings = Planting.query.all()
    cultures = Culture.query.all()
    total_trays = 12
    free_trays = 0
    ready_cultures = defaultdict(lambda: {'pots': 0, 'weight': 0})
    current_date = datetime.now().date()
    plantings_dict = {p.tray_name: p for p in plantings}
    for tray in plantings:
        if not tray.culture_id or not tray.sprouting_date:
            free_trays += 1
        else:
            tray_status_info = get_tray_status(tray, current_date)
            if "кг" in tray_status_info['status']:
                culture_name = tray.culture.name
                ready_cultures[culture_name]['pots'] += tray.pots_planted
                weight_text = tray_status_info['status'].split()[-1].replace('кг', '')
                ready_cultures[culture_name]['weight'] += float(weight_text)
    percent_occupied = ((total_trays - free_trays) / total_trays) * 100
    lines = []
    for i in range(1, 5):
        line = {'number': i, 'zones': []}
        for j in range(1, 4):
            zone_name = f'Лоток-{i}-{j}'
            zone = {'name': zone_name, 'shelves': []}
            shelf = {'number': 1, 'trays': []}
            tray = plantings_dict.get(zone_name)
            if tray:
                tray_status_info = get_tray_status(tray, current_date)
            else:
                tray_status_info = {
                    'status': 'пуст',
                    'backgroundImage': url_for('static', filename='images/empty.jpg')
                }
            shelf['trays'].append({
                'id': zone_name,
                'status': tray_status_info['status'],
                'backgroundImage': tray_status_info['backgroundImage']
            })
            zone['shelves'].append(shelf)
            line['zones'].append(zone)
        lines.append(line)
    return render_template('plantings.html',
                           lines=lines,
                           cultures=cultures,
                           default_date=current_date.strftime('%Y-%m-%d'),
                           free_trays=free_trays,
                           percent_occupied=percent_occupied,
                           ready_cultures=ready_cultures)

@bp.route('/get_tray_status')
@login_required
def get_tray_status_route():
    date_str = request.args.get('date')
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    logger.info("Выбранная дата: %s", date)
    plantings = Planting.query.all()
    tray_statuses = {}
    for tray in plantings:
        tray_status_info = get_tray_status(tray, date)
        tray_statuses[tray.tray_name] = {
            'status': tray_status_info['status'],
            'backgroundImage': tray_status_info['backgroundImage']
        }
    return jsonify(tray_statuses)

@bp.route('/planting_action', methods=['POST'])
@login_required
def planting_action():
    data = request.get_json()
    culture_id = data['culture_id']
    trays = data['trays']
    growth_stage = data.get('growth_stage')
    sprouting_date_str = data.get('sprouting_date')
    sprouting_date = datetime.strptime(sprouting_date_str, '%Y-%m-%d').date() if sprouting_date_str else datetime.now().date()
    culture = Culture.query.get(culture_id)
    for tray_name in trays:
        tray = Planting.query.filter_by(tray_name=tray_name).first()
        if tray:
            tray.sprouting_date = sprouting_date
            tray.culture_id = culture_id
            tray.pots_planted = culture.pots_at_main_stage
            tray.growth_stage = growth_stage
            logger.info("Обновлен лоток %s с культурой %s", tray_name, culture.name)
        else:
            new_tray = Planting(
                tray_name=tray_name,
                culture_id=culture_id,
                sprouting_date=sprouting_date,
                pots_planted=culture.pots_at_main_stage,
                growth_stage=growth_stage
            )
            db.session.add(new_tray)
            logger.info("Создан новый лоток %s с культурой %s", tray_name, culture.name)
    db.session.commit()
    return jsonify(success=True)

@bp.route('/collect_trays', methods=['POST'])
@login_required
def collect_trays():
    data = request.get_json()
    trays = data['trays']
    for tray_name in trays:
        tray = Planting.query.filter_by(tray_name=tray_name).first()
        if tray:
            tray.culture_id = None
            tray.pots_planted = 0
            tray.sprouting_date = None
            tray.harvest_date = None
            tray.previous_harvest_date = None
            tray.growth_stage = 'Unknown'
            logger.info("Лоток %s собран и очищен.", tray_name)
        else:
            logger.warning("Лоток %s не найден для сбора.", tray_name)
    db.session.commit()
    return jsonify(success=True)

@bp.route('/harvest_action', methods=['POST'])
@login_required
def harvest_action():
    data = request.get_json()
    harvest_date_str = data['harvest_date']
    trays = data['trays']
    harvest_date = datetime.strptime(harvest_date_str, '%Y-%m-%d').date()
    for tray_name in trays:
        tray = Planting.query.filter_by(tray_name=tray_name).first()
        if tray:
            if tray.harvest_date:
                tray.previous_harvest_date = tray.harvest_date
            tray.harvest_date = harvest_date
            logger.info("Обновлена дата срезки для лотка %s", tray_name)
        else:
            logger.warning("Лоток %s не найден для срезки.", tray_name)
    db.session.commit()
    return jsonify(success=True)

@bp.route('/get_tray/<string:tray_name>')
@login_required
def get_tray(tray_name):
    tray = Planting.query.filter_by(tray_name=tray_name).first()
    if tray:
        return jsonify({
            'tray_name': tray.tray_name,
            'culture_id': tray.culture_id,
            'pots_planted': tray.pots_planted,
            'sprouting_date': tray.sprouting_date.strftime('%Y-%m-%d') if tray.sprouting_date else '',
            'harvest_date': tray.harvest_date.strftime('%Y-%m-%d') if tray.harvest_date else '',
            'previous_harvest_date': tray.previous_harvest_date.strftime('%Y-%m-%d') if tray.previous_harvest_date else '',
            'growth_stage': tray.growth_stage
        })
    return jsonify({'error': 'Лоток не найден'}), 404

@bp.route('/update_tray', methods=['POST'])
@login_required
def update_tray():
    data = request.get_json()
    tray_name = data['tray_name']
    tray = Planting.query.filter_by(tray_name=tray_name).first()
    if tray:
        new_harvest_date = datetime.strptime(data.get('harvest_date'), '%Y-%m-%d').date() if data.get('harvest_date') else None
        if new_harvest_date and tray.harvest_date != new_harvest_date:
            tray.previous_harvest_date = tray.harvest_date
        tray.culture_id = data.get('culture_id') or None
        tray.pots_planted = data.get('pots_planted') or 0
        tray.sprouting_date = datetime.strptime(data.get('sprouting_date'), '%Y-%m-%d').date() if data.get('sprouting_date') else None
        tray.harvest_date = new_harvest_date
        tray.growth_stage = data.get('growth_stage') or None
        db.session.commit()
        logger.info("Лоток %s успешно обновлен, previous_harvest_date = %s", tray_name, tray.previous_harvest_date)
        return jsonify(success=True)
    logger.error("Лоток %s не найден", tray_name)
    return jsonify({'error': 'Лоток не найден'}), 404

@bp.route('/check_trays_not_empty', methods=['POST'])
@login_required
def check_trays_not_empty():
    data = request.get_json()
    trays = data.get('trays', [])
    all_not_empty = True
    for tray_name in trays:
        tray = Planting.query.filter_by(tray_name=tray_name).first()
        if not tray or not tray.culture_id:
            all_not_empty = False
            logger.info("Лоток %s пустой или не существует.", tray_name)
            break
        else:
            logger.info("Лоток %s не пустой.", tray_name)
    return jsonify({'all_not_empty': all_not_empty})

@bp.route('/check_trays_empty', methods=['POST'])
@login_required
def check_trays_empty():
    data = request.get_json()
    trays = data.get('trays', [])
    all_empty = True
    for tray_name in trays:
        tray = Planting.query.filter_by(tray_name=tray_name).first()
        if tray and tray.culture_id:
            all_empty = False
            logger.info("Лоток %s не пустой.", tray_name)
            break
        else:
            logger.info("Лоток %s пустой или не существует.", tray_name)
    return jsonify({'all_empty': all_empty})

@bp.route('/check_tray_not_empty', methods=['POST'])
@login_required
def check_tray_not_empty():
    data = request.get_json()
    tray_name = data.get('tray')
    tray = Planting.query.filter_by(tray_name=tray_name).first()
    not_empty = bool(tray and tray.culture_id)
    logger.info("Лоток %s %s.", tray_name, "не пустой" if not_empty else "пустой или не существует")
    return jsonify({'not_empty': not_empty})

@bp.route('/get_analysis')
@login_required
def get_analysis():
    date_str = request.args.get('date')
    selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    plantings = Planting.query.all()
    total_trays = 12
    free_trays = 0
    ready_cultures = defaultdict(lambda: {'pots': 0, 'weight': 0})
    for tray in plantings:
        if not tray.culture_id or not tray.sprouting_date:
            free_trays += 1
        else:
            tray_status_info = get_tray_status(tray, selected_date)
            if "кг" in tray_status_info['status']:
                culture_name = tray.culture.name
                ready_cultures[culture_name]['pots'] += tray.pots_planted
                weight_text = tray_status_info['status'].split()[-1].replace('кг', '')
                ready_cultures[culture_name]['weight'] += float(weight_text)
    percent_occupied = ((total_trays - free_trays) / total_trays) * 100
    analysis_data = {
        'free_trays': free_trays,
        'percent_occupied': round(percent_occupied, 2),
        'ready_cultures': [
            {'name': culture, 'pots': data['pots'], 'weight': round(data['weight'], 2)}
            for culture, data in ready_cultures.items()
        ]
    }
    return jsonify(analysis_data)

@bp.route('/control')
@login_required
def control():
    trays = Tray.query.all()
    lines = [
        {
            'number': i,
            'zones': [
                {
                    'name': f'Лоток-{i}-{j}',
                    'shelves': [
                        {
                            'number': 1,
                            'trays': [
                                next((t for t in trays if t.shelf == f'Лоток-{i}-{j}'), Tray(shelf=f'Лоток-{i}-{j}', action='', plant_type='', growth_days=0))
                            ]
                        }
                    ]
                } for j in range(1, 4)
            ]
        } for i in range(1, 5)
    ]
    default_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('control.html', lines=lines, default_date=default_date, title='Контроль посадки')

# === КАМЕРА: роуты ===

@bp.route('/camera/latest_info')
@login_required
def camera_latest_info():
    cam = int(request.args.get('cam', '1'))
    p = _latest_image_path(cam)
    if not p:
        abort(404, description="Нет кадров")
    ts = _name_to_ts(p)
    iso = ts.replace(microsecond=0).isoformat() if ts else _now().replace(microsecond=0).isoformat()
    return jsonify({"filename": os.path.basename(p), "iso": iso})

@bp.route('/camera/latest.jpg')
@login_required
def camera_latest_jpg():
    cam = int(request.args.get('cam', '1'))
    p = _latest_image_path(cam)
    if not p:
        abort(404, description="Нет кадров в архиве")
    return send_file(p, mimetype="image/jpeg", conditional=True)

@bp.route('/camera/download_latest')
@login_required
def camera_download_latest():
    cam = int(request.args.get('cam', '1'))
    p = _latest_image_path(cam)
    if not p:
        abort(404, description="Нет кадров")
    return send_file(p, mimetype="image/jpeg", as_attachment=True, download_name="latest.jpg", conditional=True)

@bp.route('/camera/image_at')
@login_required
def camera_image_at():
    cam = int(request.args.get('cam', '1'))
    dt_str = request.args.get("dt", "")
    if not dt_str:
        abort(400, description="Параметр dt обязателен")
    target = _parse_dt_local(dt_str)
    p = _find_nearest_image(target, cam)
    if not p:
        abort(404, description="Подходящих кадров не найдено")
    return send_file(p, mimetype="image/jpeg", conditional=True)

@bp.route('/camera/download_at')
@login_required
def camera_download_at():
    cam = int(request.args.get('cam', '1'))
    dt_str = request.args.get("dt", "")
    if not dt_str:
        abort(400, description="Параметр dt обязателен")
    target = _parse_dt_local(dt_str)
    p = _find_nearest_image(target, cam)
    if not p:
        abort(404, description="Подходящих кадров не найдено")
    name = f"frame_{dt_str.replace(':','-').replace('T','_')}.jpg"
    return send_file(p, mimetype="image/jpeg", as_attachment=True, download_name=name, conditional=True)

@bp.route('/camera/capture_now', methods=['POST'])
@login_required
def camera_capture_now():
    cam = int(request.args.get('cam', '1'))
    # Отключаем ручной снимок, если нужно, через .env
    if os.getenv("CAMERA_ENABLE_CAPTURE_NOW", "true").lower() != "true":
        abort(403, description="Ручной снимок отключён")

    # минимальные задержки для ffmpeg-бекенда
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|reorder_queue_size;0|stimeout;5000000"
    )
    cap = cv2.VideoCapture(_cam_rtsp(cam), cv2.CAP_FFMPEG)

    if not cap.isOpened():
        abort(500, description="Камера недоступна")

    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        for _ in range(15):
            cap.read()
        ok, frame = cap.read()
        if not ok or frame is None:
            abort(500, description="Не удалось получить кадр")
        path = _save_frame(frame, cam)  # ваш helper сохранения в архив
    finally:
        try: cap.release()
        except Exception:
            pass

    return jsonify({
        "ok": True,
        "filename": os.path.basename(path),
        "path": path,
        "exists": os.path.exists(path),
        "save_dir": _cam_save_dir()
    })

@bp.route('/camera/timelapse.mp4')
@login_required
def camera_timelapse_mp4():
    cam = int(request.args.get('cam', '1'))
    s = request.args.get("start", "")
    e = request.args.get("end", "")
    fps = int(request.args.get("fps", "20"))
    dl = request.args.get("dl", "0") == "1"

    if not s or not e:
        abort(400, description="Нужны start и end")

    start_dt = _parse_dt_local(s)
    end_dt = _parse_dt_local(e)
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    files = _list_between(start_dt, end_dt, cam)

    if not files:
        abort(404, description="Кадров за указанный период нет")

    fname = f"timelapse_{s.replace(':','-').replace('T','_')}_to_{e.replace(':','-').replace('T','_')}_{fps}fps.mp4"
    out_path = os.path.join(_cam_tmp_dir(), fname)
    os.makedirs(_cam_tmp_dir(), exist_ok=True)

    ok = _build_timelapse(files, fps, out_path)
    if not ok or not os.path.exists(out_path):
        abort(500, description="Не удалось собрать клип")

    return send_file(out_path, mimetype="video/mp4", as_attachment=dl, download_name=fname, conditional=True)

@bp.route('/light')
@login_required
def light_control():
    params = Parameter.query.all()

    d = {}
    for p in params:
        key = p.controlled_parameter_name
        val = p.value
        if isinstance(key, bytes):
            key = key.decode('utf-8')
        if isinstance(val, bytes):
            val = val.decode('utf-8')
        d[key] = val

    return render_template("light.html", p=d)

# Функция записи параметров клиента для WIFi-адаптера    
@bp.route('/update_wifi_client_settings', methods=['POST'])
@login_required
def update_wifi_client_settings():
    data = request.get_json(force=True)

    sta_enabled = "1" if int(data.get("sta_enabled", 0)) else "0"
    sta_ssid = str(data.get("sta_ssid", "")).strip()
    sta_psk = str(data.get("sta_psk", ""))
    sta_hidden = "1" if int(data.get("sta_hidden", 0)) else "0"

    conf_path = "/etc/smart-wifi/wifi.conf"

    try:
        with open(conf_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        updates = {
            "STA_ENABLED": sta_enabled,
            "STA_SSID": f'"{sta_ssid}"',
            "STA_PSK": f'"{sta_psk}"',
            "STA_HIDDEN": sta_hidden,
        }

        found = set()
        new_lines = []

        for line in lines:
            stripped = line.strip()
            replaced = False

            for key, value in updates.items():
                if stripped.startswith(f"{key}="):
                    new_lines.append(f"{key}={value}\n")
                    found.add(key)
                    replaced = True
                    break

            if not replaced:
                new_lines.append(line)

        for key, value in updates.items():
            if key not in found:
                new_lines.append(f"{key}={value}\n")

        fd, tmp_path = tempfile.mkstemp()
        os.close(fd)

        with open(tmp_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        shutil.move(tmp_path, conf_path)

        res = subprocess.run(
            ["/bin/systemctl", "restart", "smart-wifi.service"],
            capture_output=True,
            text=True
        )

        if res.returncode != 0:
            status_res = subprocess.run(
                ["/bin/systemctl", "status", "smart-wifi.service", "--no-pager", "-l"],
                capture_output=True,
                text=True
            )

            message = "Настройки записаны, но сервис не удалось перезапустить."
            if "No Wi-Fi interfaces found" in status_res.stdout:
                message = "Настройки записаны, но Wi-Fi адаптер не подключён, поэтому сервис не перезапущен."

            return jsonify({
                "status": "warning",
                "message": message
            }), 200

        return jsonify({
            "status": "ok",
            "message": "Настройки записаны и сервис Wi-Fi перезапущен."
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# Функция для кнопки перезапуска сервиса WiFi      
@bp.route('/restart_wifi_service', methods=['POST'])
@login_required
def restart_wifi_service():
    try:
        res = subprocess.run(
            ["/bin/systemctl", "restart", "smart-wifi.service"],
            capture_output=True,
            text=True
        )

        if res.returncode != 0:
            status_res = subprocess.run(
                ["/bin/systemctl", "status", "smart-wifi.service", "--no-pager", "-l"],
                capture_output=True,
                text=True
            )

            message = "Сервис не удалось перезапустить"

            if "No Wi-Fi interfaces found" in status_res.stdout:
                message = "Wi-Fi адаптер не подключён"

            return jsonify({
                "status": "warning",
                "message": message
            }), 200

        return jsonify({
            "status": "ok",
            "message": "Сервис успешно перезапущен"
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
        
@bp.route('/update_modem_settings', methods=['POST'])
@login_required
def update_modem_settings():
    if not current_user.is_authenticated or current_user.role != "admin":
        return jsonify({"status": "error", "message": "Недостаточно прав"}), 403

    data = request.get_json(silent=True) or {}

    try:
        write_modem_config(data)
        return jsonify({
            "status": "ok",
            "message": "Настройки модема записаны. Для применения перезапустите модем."
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@bp.route('/restart_modem_service', methods=['POST'])
@login_required
def restart_modem_service():
    if not current_user.is_authenticated or current_user.role != "admin":
        return jsonify({"status": "error", "message": "Недостаточно прав"}), 403

    try:
        res = subprocess.run(
            ["/bin/systemctl", "restart", "uspd-modem.service"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if res.returncode != 0:
            return jsonify({
                "status": "error",
                "message": res.stderr or res.stdout or "Не удалось перезапустить uspd-modem"
            }), 500

        return jsonify({
            "status": "ok",
            "message": "Сервис модема перезапущен."
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
        
def get_iface_ip(iface):
    try:
        result = subprocess.run(
            [IP_BIN, "-4", "addr", "show", iface],
            capture_output=True,
            text=True,
            timeout=3
        )

        match = re.search(r"inet\s+([0-9.]+)/", result.stdout)
        return match.group(1) if match else ""
    except Exception:
        return ""


def read_ethernet_config():
    result = {
        "lan1": {"iface": "eth0", "mode": "dhcp", "ip": "", "netmask": "", "gateway": "", "dns": "", "current_ip": get_iface_ip("eth0")},
        "lan2": {"iface": "eth1", "mode": "static", "ip": "192.168.0.1", "netmask": "255.255.255.0", "gateway": "", "dns": "", "current_ip": get_iface_ip("eth1")},
    }

    if not os.path.exists(ETHERNET_INTERFACES_PATH):
        return result

    current = None

    try:
        with open(ETHERNET_INTERFACES_PATH, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()

                if line.startswith("iface eth0 inet"):
                    current = "lan1"
                    result[current]["mode"] = "dhcp" if "dhcp" in line else "static"

                elif line.startswith("iface eth1 inet"):
                    current = "lan2"
                    result[current]["mode"] = "dhcp" if "dhcp" in line else "static"

                elif current and line.startswith("address "):
                    result[current]["ip"] = line.split(None, 1)[1]

                elif current and line.startswith("netmask "):
                    result[current]["netmask"] = line.split(None, 1)[1]

                elif current and line.startswith("gateway "):
                    result[current]["gateway"] = line.split(None, 1)[1]

                elif current and line.startswith("dns-nameservers "):
                    parts = line.split(None, 1)
                    dns_raw = parts[1].strip() if len(parts) > 1 else ""
                    result[current]["dns"] = dns_raw.split()[0] if dns_raw else ""

    except Exception as e:
        logger.warning("Не удалось прочитать Ethernet config: %s", e)

    return result

def write_ethernet_config(data):
    def section(lan_key, iface):
        cfg = data.get(lan_key, {})
        mode = cfg.get("mode", "dhcp")

        lines = [
            f"auto {iface}",
            f"iface {iface} inet {'dhcp' if mode == 'dhcp' else 'static'}"
        ]

        if mode == "static":
            lines.append(f"    address {cfg.get('ip', '').strip()}")
            lines.append(f"    netmask {cfg.get('netmask', '').strip()}")

            gateway = cfg.get("gateway", "").strip()
            dns = cfg.get("dns", "").strip()

            if gateway:
                lines.append(f"    gateway {gateway}")

            if dns:
                lines.append(f"    dns-nameservers {dns}")

        metric = "0" if lan_key == "lan1" else "1"
        lines.append(f"    metric {metric}")

        return "\n".join(lines)

    content = section("lan1", "eth0") + "\n\n" + section("lan2", "eth1") + "\n"

    with open(ETHERNET_INTERFACES_PATH, "w", encoding="utf-8") as f:
        f.write(content)
        
@bp.route('/update_ethernet_settings', methods=['POST'])
@login_required
def update_ethernet_settings():
    if current_user.username != "admin" and current_user.role != "admin":
        return jsonify({"status": "error", "message": "Недостаточно прав"}), 403

    data = request.get_json(silent=True) or {}

    try:
        write_ethernet_config(data)
        return jsonify({
            "status": "ok",
            "message": "Настройки Ethernet записаны. Для применения перезагрузите устройство."
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# Функция для кнопки перезагрузки  устройства        
@bp.route('/reboot_device', methods=['POST'])
@login_required
def reboot_device():
    try:
        subprocess.Popen(["/usr/sbin/reboot"])
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
        
def _yes_no(value):
    return "Да" if str(value) in ("1", "5") else "Нет"


def get_ppp0_ip():
    try:
        result = subprocess.run(
            [IP_BIN, "-4", "addr", "show", "ppp0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3
        )

        # сначала вариант с peer (как у тебя)
        match = re.search(r"inet\s+([0-9.]+)\s+peer", result.stdout)
        if match:
            return match.group(1)

        # fallback (для обычных интерфейсов)
        match = re.search(r"inet\s+([0-9.]+)/", result.stdout)
        if match:
            return match.group(1)

        return ""

    except Exception:
        return ""


def read_modem_state():
    if not os.path.exists(MODEM_INFO_PATH):
        return None

    try:
        with open(MODEM_INFO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {
            "ipaddr": get_ppp0_ip(),
            "last_update": data.get("last_update", ""),
            "type": data.get("info", ""),
            "fw": data.get("fw", ""),
            "imei": data.get("imei", ""),
            "iccid": data.get("iccid", ""),
            "operator": data.get("ops", ""),
            "creg": _yes_no(data.get("creg", "")),
            "cereg": _yes_no(data.get("cereg", "")),
            "cgreg": _yes_no(data.get("cgreg", "")),
            "signal": data.get("csq", ""),
            "level": data.get("level", ""),
            "pin_ok": "Да" if data.get("cpin") == "READY" else "Нет",
            "net_type": data.get("mode", ""),
            "submode": data.get("submode", ""),
            "band": data.get("band", ""),
            "rssi": data.get("rssi", ""),
            "rsrp": data.get("rsrp", ""),
            "rsrq": data.get("rsrq", ""),
            "sinr": data.get("sinr", "")
        }
    except Exception:
        return None


def read_modem_config():
    if not os.path.exists(MODEM_CONF_PATH):
        return None

    config = {}

    try:
        with open(MODEM_CONF_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().rstrip(";").strip()

                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]

                config[key] = value

        return {
            "enable": int(config.get("enable", "0")),
            "pin": config.get("pin", ""),
            "apn_user": config.get("apn_user", ""),
            "apn_password": config.get("apn_password", ""),
            "apn_server": config.get("apn_server", ""),
            "apn_auth": int(config.get("apn_auth", "0")),

            "enable2": int(config.get("enable2", "0")),
            "pin2": config.get("pin2", ""),
            "apn_user2": config.get("apn_user2", ""),
            "apn_password2": config.get("apn_password2", ""),
            "apn_server2": config.get("apn_server2", ""),
            "apn_auth2": int(config.get("apn_auth2", "0")),

            "en_2g": int(config.get("en_2g", "1")),
            "en_3g": int(config.get("en_3g", "1")),
            "en_4g": int(config.get("en_4g", "1")),
            "net_timeout": int(config.get("net_timeout", "60")),
            "modem_route_priority": int(config.get("modem_route_priority", "0"))
        }
    except Exception:
        return None


def write_modem_config(data):
    def b(name):
        return 1 if data.get(name) in (1, "1", True, "true", "on") else 0

    def s(name):
        return str(data.get(name, "")).replace('"', '').replace('\n', '').replace('\r', '')

    content = f'''enable={b("enable")};
pin="{s("pin")}";
apn_user="{s("apn_user")}";
apn_password="{s("apn_password")}";
apn_server="{s("apn_server")}";
apn_auth={b("apn_auth")};

enable2={b("enable2")};
pin2="{s("pin2")}";
apn_user2="{s("apn_user2")}";
apn_password2="{s("apn_password2")}";
apn_server2="{s("apn_server2")}";
apn_auth2={b("apn_auth2")};

en_2g={b("en_2g")};
en_3g={b("en_3g")};
en_4g={b("en_4g")};
net_timeout={int(data.get("net_timeout", 60) or 60)};

modem_route_priority={1 if str(data.get("modem_route_priority", "0")) == "1" else 0};
'''

    with open(MODEM_CONF_PATH, "w", encoding="utf-8") as f:
        f.write(content)
        
@bp.route('/status_summary')
@login_required
def status_summary():
    # WiFi
    wifi_status = get_wifi_client_status()

    if "Подключен, получен IP" in wifi_status:
        wifi_state = "ok"
    elif "Подключен" in wifi_status:
        wifi_state = "warn"
    elif "Адаптер не обнаружен" in wifi_status:
        wifi_state = "unknown"
    else:
        wifi_state = "error"

    # GSM
    modem_state = read_modem_state()

    gsm_state = "unknown"
    gsm_text = "Нет данных"

    if modem_state:
        gsm_ip = modem_state.get("ipaddr", "")
        level = (modem_state.get("level") or "").lower()
        net_type = modem_state.get("net_type") or "GSM"

        if gsm_ip:
            if level in ("excellent", "good"):
                gsm_state = "ok"
            elif level in ("fair",):
                gsm_state = "warn"
            elif level in ("poor", "no signal"):
                gsm_state = "error"
            else:
                gsm_state = "ok"

            gsm_text = f"{net_type}: {level or 'подключен'}, IP {gsm_ip}"
        else:
            gsm_state = "error"
            gsm_text = f"{net_type}: нет IP"
    else:
        gsm_state = "unknown"
        gsm_text = "Модем не обнаружен или нет данных"

    return jsonify({
        "wifi": wifi_state,
        "wifi_text": wifi_status,
        "gsm": gsm_state,
        "gsm_text": gsm_text
    })
    
    
@bp.app_context_processor
def inject_status_flags():
    return {
        "wifi_available": os.path.exists("/etc/smart-wifi/wifi.conf"),
        "modem_available": os.path.exists(MODEM_INFO_PATH)
    }
    
    
if not _traffic_timer_started:
    start_traffic_stats_worker()
    
# Импорт/экспорт БД из веб
@bp.route('/settings/export-db')
@login_required
def export_db():
    from config import DB_PATH

    if current_user.username != "admin" and current_user.role != "admin":
        return jsonify({"error": "Недостаточно прав"}), 403

    return send_file(
        DB_PATH,
        as_attachment=True,
        download_name=os.path.basename(DB_PATH)
    )
    
@bp.route('/settings/import-db', methods=['POST'])
@login_required
def import_db():
    from config import DB_PATH

    if current_user.username != "admin" and current_user.role != "admin":
        return jsonify({"error": "Недостаточно прав"}), 403

    file = request.files.get('file')
    if not file or not file.filename.endswith('.db'):
        return jsonify({'error': 'Неверный файл'}), 400

    project_dir = os.path.dirname(DB_PATH)

    old_db_path = DB_PATH
    old_db_name = os.path.basename(DB_PATH)

    current_base_name = os.path.splitext(os.path.basename(file.filename))[0]
    date_str = datetime.now().strftime('%d%m%y')

    # Если текущая БД уже вида mini-demo-270426 или mini-demo-270426-1,
    # берём исходное имя mini-demo
    base_name = re.sub(r'-\d{6}(?:-\d+)?$', '', current_base_name)

    new_name = f"{base_name}-{date_str}.db"
    new_path = os.path.join(project_dir, new_name)

    i = 1
    while os.path.exists(new_path):
        new_name = f"{base_name}-{date_str}-{i}.db"
        new_path = os.path.join(project_dir, new_name)
        i += 1

    file.save(new_path)

    # === ВАЛИДАЦИЯ ===
    if not is_sqlite_file(new_path):
        os.remove(new_path)
        return jsonify({"error": "Файл не является SQLite базой"}), 400

    if not can_open_sqlite(new_path):
        os.remove(new_path)
        return jsonify({"error": "БД повреждена"}), 400

    if not compare_db_structure(old_db_path, new_path):
        os.remove(new_path)
        return jsonify({"error": "Структура БД не совпадает"}), 400

    # === ПЕРЕКЛЮЧАЕМ config.py НА НОВУЮ БД ===
    try:
        update_config_db_name(new_name)
    except Exception as e:
        os.remove(new_path)
        return jsonify({"error": f"Не удалось обновить config.py: {e}"}), 500

    # === ПРОВЕРЯЕМ agrosmart_sync НА НОВОЙ БД ===
    sync_ok = restart_service_and_wait("agrosmart_sync", timeout_sec=30)

    if not sync_ok:
        # ОТКАТ config.py НА СТАРУЮ БД
        try:
            update_config_db_name(old_db_name)
            rollback_ok = restart_service_and_wait("agrosmart_sync", timeout_sec=30)
        except Exception:
            rollback_ok = False

        # web НЕ перезапускаем
        if rollback_ok:
            return jsonify({
                "error": "Не удалось загрузить БД, т.к она содержит ошибки. Произошло восстановление предыдущей версии"
            }), 500
        else:
            return jsonify({
            "error": "Не удалось загрузить БД. Также не удалось автоматически восстановить agrosmart_sync. Требуется ручная проверка."
            }), 500

    # === sync поднялся — теперь можно перезапускать web ===
    web_ok = subprocess.Popen(["/bin/systemctl", "restart", "agrosmart_web"])

    if not web_ok:
        return jsonify({
            "error": "БД загружена, agrosmart_sync запущен, но agrosmart_web не поднялся. Обновите страницу позже или проверьте сервис вручную."
        }), 500

    # === чистим старые БД: активная + не более 3 старых ===
    cleanup_old_dbs(project_dir, new_name, keep_old=3)

    return jsonify({
        "message": "БД успешно загружена. Веб-сервис перезапущен. Обновите страницу через 1 минуту."
    }), 200
    
@bp.route('/get_logs')
@login_required
def get_logs():
    logs_info = (
        Log.query
        .filter(Log.level == 'INFO')
        .order_by(Log.timestamp.desc())
        .limit(30)
        .all()
    )

    logs_errors = (
        Log.query
        .filter(Log.level.in_(['ERROR', 'CRITICAL', 'WARNING']))
        .order_by(Log.timestamp.desc())
        .limit(30)
        .all()
    )

    def serialize_log(log):
        return {
            'timestamp': log.timestamp.strftime('%d.%m.%Y %H:%M:%S'),
            'message': log.message
        }

    return jsonify({
        'info': [serialize_log(log) for log in logs_info],
        'errors': [serialize_log(log) for log in logs_errors]
    })
