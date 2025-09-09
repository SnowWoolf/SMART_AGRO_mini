# camera_saver.py
import os, time, glob
import cv2
import datetime as dt
from dotenv import load_dotenv

from pathlib import Path
import numpy as np

# грузим .env
load_dotenv()

# --- конфиг из окружения / дефолты ---
RTSP        = os.getenv("CAMERA_RTSP_URL", "rtsp://admin:admin123@192.168.202.229:554/live/ch00_0")
SAVE_DIR    = os.getenv("CAMERA_SAVE_DIR", "./camera_archive")
SAVE_EVERY  = int(os.getenv("CAMERA_SAVE_EVERY_SEC", "300"))
RETAIN_DAYS = float(os.getenv("CAMERA_RETAIN_DAYS", "14"))
MAX_W       = int(os.getenv("CAMERA_MAX_PREVIEW_W", "1280"))
JPEG_Q      = int(os.getenv("CAMERA_JPEG_QUALITY", "90"))

# Новые (опционально в .env):
RTSP_TRANSPORT = os.getenv("CAMERA_RTSP_TRANSPORT", "tcp")  # tcp | udp
WARMUP_MS      = int(os.getenv("CAMERA_WARMUP_MS", "700"))  # сколько «прожигать» поток после открытия

os.makedirs(SAVE_DIR, exist_ok=True)

# минимизация задержек у ffmpeg-бекенда opencv
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    f"rtsp_transport;{RTSP_TRANSPORT}|"
    "fflags;nobuffer|flags;low_delay|reorder_queue_size;0|"
    "stimeout;5000000|rw_timeout;10000000|max_delay;0"
)


def now(): return dt.datetime.now()

def ts_to_name(ts: dt.datetime) -> str:
    return ts.strftime("%Y%m%d_%H%M%S") + f"{int(ts.microsecond/1000):03d}.jpg"

def name_to_ts(fname: str):
    base = os.path.basename(fname)
    stem, ext = os.path.splitext(base)
    if ext.lower() != ".jpg": return None
    try:
        date_part, time_part = stem.split("_")
        sec_dt = dt.datetime.strptime(date_part + "_" + time_part[:6], "%Y%m%d_%H%M%S")
        ms = int(time_part[6:9]) if len(time_part) >= 9 else 0
        return sec_dt + dt.timedelta(milliseconds=ms)
    except: return None

def save_frame(frame):
    out_dir = Path(SAVE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts_name = ts_to_name(now())
    path = out_dir / ts_name
    tmp_path = out_dir / (ts_name + ".part")

    # ресайз при необходимости
    h, w = frame.shape[:2]
    if w > MAX_W:
        scale = MAX_W / float(w)
        frame = cv2.resize(frame, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)

    # кодируем jpg в память и пишем обычным open() — устойчиво к Unicode-путям
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_Q])
    if not ok:
        raise RuntimeError("cv2.imencode('.jpg', ...) вернул False")

    try:
        with open(tmp_path, "wb") as f:
            f.write(buf.tobytes())
        os.replace(tmp_path, path)  # атомарно
    finally:
        # вдруг что-то пошло не так
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except:
                pass

    # доп. проверка
    if not path.exists():
        raise FileNotFoundError(f"Файл не появился на диске: {path}")

    return str(path)


def retention_cleanup():
    cutoff = now() - dt.timedelta(days=RETAIN_DAYS)
    for p in glob.glob(os.path.join(SAVE_DIR, "*.jpg")):
        ts = name_to_ts(p)
        if ts and ts < cutoff:
            try: os.remove(p)
            except: pass

# ====== BEGIN PATCH: per-shot grab ======
def grab_fresh_frame():
    """
    Открываем RTSP, быстро «прожигаем» поток, берём последний кадр и закрываем.
    Это гарантирует свежесть кадра, даже если между снимками большие паузы.
    """
    cap = cv2.VideoCapture(RTSP, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return None

    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Прожигаем поток по времени (WARMUP_MS) и/или по количеству кадров
        t0 = time.time()
        last = None
        reads = 0
        while (time.time() - t0) * 1000 < WARMUP_MS and reads < 60:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            last = frame
            reads += 1

        # На всякий — пара дополнительных чтений
        for _ in range(3):
            ok, frame = cap.read()
            if ok and frame is not None:
                last = frame

        return last
    finally:
        try:
            cap.release()
        except:
            pass
# ====== END PATCH ======

def run():
    last_cleanup = 0.0
    while True:
        try:
            frame = grab_fresh_frame()
            if frame is None:
                print("Камера недоступна, повтор через 5с")
                time.sleep(5)
                continue

            path = save_frame(frame)
            print("Сохранён:", path, "exists:", os.path.exists(path))

            if time.time() - last_cleanup > 3600:
                retention_cleanup()
                last_cleanup = time.time()

            time.sleep(SAVE_EVERY)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print("Ошибка:", e)
            time.sleep(3)


if __name__ == "__main__":
    run()
