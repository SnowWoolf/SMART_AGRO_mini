import struct
import minimalmodbus
import time
import sqlite3
from loguru import logger

# ─────────────────────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────────────────────

DB_PATH = "/home/persay/data.db"

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# ─────────────────────────────────────────────────────────────
# TYPE SYSTEM (из столбца Parameter)
# ─────────────────────────────────────────────────────────────

def get_dtype(p):
    if not p["parameter"]:
        return "u16"
    return p["parameter"].strip().lower()


def words_for_dtype(dtype):
    if dtype in ("u16", "s16"):
        return 1
    if dtype in ("u32", "s32", "float32"):
        return 2
    if dtype in ("u64", "s64"):
        return 4
    return 1


# ─────────────────────────────────────────────────────────────
# DECODE
# ─────────────────────────────────────────────────────────────

def decode_value(registers, dtype):

    if dtype == "u16":
        return registers[0]

    if dtype == "s16":
        v = registers[0]
        if v >= 0x8000:
            v -= 0x10000
        return v

    if dtype in ("u32", "s32", "float32"):
        b = registers[0].to_bytes(2,"big") + registers[1].to_bytes(2,"big")

        if dtype == "u32":
            return struct.unpack(">I", b)[0]

        if dtype == "s32":
            return struct.unpack(">i", b)[0]

        if dtype == "float32":
            return struct.unpack(">f", b)[0]

    if dtype in ("u64", "s64"):
        b = b"".join(r.to_bytes(2,"big") for r in registers[:4])

        if dtype == "u64":
            return struct.unpack(">Q", b)[0]

        if dtype == "s64":
            return struct.unpack(">q", b)[0]

    return registers[0]


# ─────────────────────────────────────────────────────────────
# ENCODE
# ─────────────────────────────────────────────────────────────

def encode_value(value, dtype):

    if dtype in ("u16","s16"):
        return [int(value) & 0xFFFF]

    if dtype == "u32":
        b = struct.pack(">I", int(value))
        return [int.from_bytes(b[0:2],"big"), int.from_bytes(b[2:4],"big")]

    if dtype == "s32":
        b = struct.pack(">i", int(value))
        return [int.from_bytes(b[0:2],"big"), int.from_bytes(b[2:4],"big")]

    if dtype == "float32":
        b = struct.pack(">f", float(value))
        return [int.from_bytes(b[0:2],"big"), int.from_bytes(b[2:4],"big")]

    if dtype == "u64":
        b = struct.pack(">Q", int(value))
        return [int.from_bytes(b[i:i+2],"big") for i in range(0,8,2)]

    if dtype == "s64":
        b = struct.pack(">q", int(value))
        return [int.from_bytes(b[i:i+2],"big") for i in range(0,8,2)]

    return [int(value)]


# ─────────────────────────────────────────────────────────────
# MODBUS CLIENT CACHE
# ─────────────────────────────────────────────────────────────

clients = {}

def get_client(port, slave, baud):

    key = f"{port}_{slave}"

    if key in clients:
        return clients[key]

    inst = minimalmodbus.Instrument(port, int(slave))
    inst.serial.baudrate = int(baud)
    inst.serial.timeout = 0.5
    inst.mode = minimalmodbus.MODE_RTU

    clients[key] = inst
    return inst


# ─────────────────────────────────────────────────────────────
# GROUP PARAMETERS
# ─────────────────────────────────────────────────────────────

def group_params(rows):

    groups = []

    for r in rows:
        dtype = get_dtype(r)
        words = words_for_dtype(dtype)

        if not groups:
            groups.append({
                "rows":[r],
                "start": r["register_nu"],
                "count": words,
                "port": r["com"],
                "slave": r["network_a"],
                "baud": r["speed"],
                "rtype": r["register_ty"]
            })
            continue

        g = groups[-1]

        contiguous = (
            r["com"] == g["port"] and
            r["network_a"] == g["slave"] and
            r["register_ty"] == g["rtype"] and
            r["register_nu"] == g["start"] + g["count"]
        )

        if contiguous:
            g["rows"].append(r)
            g["count"] += words
        else:
            groups.append({
                "rows":[r],
                "start": r["register_nu"],
                "count": words,
                "port": r["com"],
                "slave": r["network_a"],
                "baud": r["speed"],
                "rtype": r["register_ty"]
            })

    return groups


# ─────────────────────────────────────────────────────────────
# READ
# ─────────────────────────────────────────────────────────────

def read_all():

    db = get_db()
    db.row_factory = sqlite3.Row

    rows = db.execute("""
        SELECT * FROM parameters
        WHERE operation_type='чтение'
        ORDER BY com, network_a, register_nu
    """).fetchall()

    groups = group_params(rows)

    for g in groups:

        try:
            inst = get_client(g["port"], g["slave"], g["baud"])

            vals = inst.read_registers(
                g["start"],
                g["count"],
                functioncode=int(g["rtype"])
            )

            offset = 0

            for r in g["rows"]:
                dtype = get_dtype(r)
                words = words_for_dtype(dtype)

                raw = decode_value(vals[offset:offset+words], dtype)

                K = float(r["K"]) if r["K"] else 1.0
                value = raw / K

                db.execute(
                    "UPDATE parameters SET value=?, value_date=CURRENT_TIMESTAMP WHERE id=?",
                    (value, r["id"])
                )

                offset += words

        except Exception as e:
            logger.error(f"MODBUS READ ERROR {g['port']} slave {g['slave']} : {e}")

    db.commit()
    db.close()


# ─────────────────────────────────────────────────────────────
# WRITE
# ─────────────────────────────────────────────────────────────

def write_param(param_id, value):

    db = get_db()
    db.row_factory = sqlite3.Row

    p = db.execute(
        "SELECT * FROM parameters WHERE id=?",
        (param_id,)
    ).fetchone()

    if not p:
        return

    dtype = get_dtype(p)
    K = float(p["K"]) if p["K"] else 1.0

    scaled = value * K
    words = encode_value(scaled, dtype)

    inst = get_client(p["com"], p["network_a"], p["speed"])

    try:
        if len(words) == 1:
            inst.write_register(p["register_nu"], words[0], functioncode=6)
        else:
            inst.write_registers(p["register_nu"], words)

    except Exception as e:
        logger.error(f"WRITE ERROR {e}")

    db.close()


# ─────────────────────────────────────────────────────────────
# LOOP
# ─────────────────────────────────────────────────────────────

def sync_loop():

    while True:
        read_all()
        time.sleep(1)
