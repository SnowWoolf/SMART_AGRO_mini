# VERSION: 2.0.290426
# Миграционный скрипт БД для правок под новый конструктор сценариев. 27.04.2026
# Положить в каталог с .db и выполнить: python3 migrate_scenario_cycles.py

import sqlite3
import json
from pathlib import Path
from datetime import datetime

# ТУТ поправь имя БД
DB_PATH = Path("mini-demo.db")


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def time_to_seconds(value):
    if value is None:
        return 0

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    parts = str(value).split(":")

    try:
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
        seconds = int(float(parts[2])) if len(parts) > 2 else 0
    except (TypeError, ValueError):
        return 0

    return hours * 3600 + minutes * 60 + seconds


def ensure_legacy_cycle(cursor, name, cycle_type):
    cursor.execute(
        """
        SELECT id
        FROM scenario_cycle
        WHERE name=? AND cycle_type=?
        ORDER BY id
        LIMIT 1
        """,
        (name, cycle_type)
    )
    row = cursor.fetchone()

    if row:
        return row[0]

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    cursor.execute(
        """
        INSERT INTO scenario_cycle (
            name,
            cycle_type,
            first_time,
            period_minutes,
            enabled,
            steps_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, '00:00', 0, 1, '[]', ?, ?)
        """,
        (name, cycle_type, now, now)
    )

    return cursor.lastrowid


def migrate_legacy_scenarios(cursor, cycle_id, scenario_types):
    placeholders = ",".join("?" for _ in scenario_types)
    params = [*scenario_types, cycle_id]

    cursor.execute(
        f"""
        SELECT id, type, time, parameter, value
        FROM scenario
        WHERE type IN ({placeholders})
          AND (cycle_id IS NULL OR cycle_step_index IS NULL OR cycle_id=?)
        ORDER BY time, id
        """,
        params
    )
    rows = cursor.fetchall()

    if not rows:
        return 0

    steps = []
    previous_seconds = 0

    for step_index, row in enumerate(rows):
        scenario_id, _scenario_type, scenario_time, parameter, value = row
        current_seconds = time_to_seconds(scenario_time)

        delay_sec = current_seconds - previous_seconds
        if delay_sec < 0:
            delay_sec += 24 * 3600

        steps.append({
            "delay_sec": delay_sec,
            "parameter": parameter,
            "value": value
        })

        cursor.execute(
            """
            UPDATE scenario
            SET cycle_id=?, cycle_step_index=?
            WHERE id=?
            """,
            (cycle_id, step_index, scenario_id)
        )

        previous_seconds = current_seconds

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    cursor.execute(
        """
        UPDATE scenario_cycle
        SET steps_json=?, updated_at=?
        WHERE id=?
        """,
        (json.dumps(steps, ensure_ascii=False), now, cycle_id)
    )

    return len(rows)


def main():
    if not DB_PATH.exists():
        print(f"[ERROR] БД не найдена: {DB_PATH.resolve()}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        print("[INFO] Проверка таблицы scenario_cycle")

        if not table_exists(cur, "scenario_cycle"):
            print("[INFO] Создаю таблицу scenario_cycle")

            cur.execute("""
                CREATE TABLE scenario_cycle (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(128) NOT NULL,
                    cycle_type VARCHAR(64) NOT NULL DEFAULT 'Полив',
                    first_time VARCHAR(5) NOT NULL,
                    period_minutes INTEGER NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    steps_json TEXT NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """)
        else:
            print("[OK] Таблица scenario_cycle уже есть")

        print("[INFO] Проверка колонок таблицы scenario")

        if not column_exists(cur, "scenario", "cycle_id"):
            print("[INFO] Добавляю scenario.cycle_id")
            cur.execute("ALTER TABLE scenario ADD COLUMN cycle_id INTEGER")

        if not column_exists(cur, "scenario", "cycle_step_index"):
            print("[INFO] Добавляю scenario.cycle_step_index")
            cur.execute("ALTER TABLE scenario ADD COLUMN cycle_step_index INTEGER")

        print("[INFO] Проверка старых сценариев без связи с циклами")

        irrigation_cycle_id = ensure_legacy_cycle(cur, "Полив", "Полив")
        light_cycle_id = ensure_legacy_cycle(cur, "Освещение", "Свет")

        irrigation_count = migrate_legacy_scenarios(
            cur,
            irrigation_cycle_id,
            ("Полив",)
        )
        light_count = migrate_legacy_scenarios(
            cur,
            light_cycle_id,
            ("Свет", "Свет уровень")
        )

        print(f"[OK] Привязано строк полива: {irrigation_count}")
        print(f"[OK] Привязано строк освещения: {light_count}")

        conn.commit()
        print("[OK] Миграция выполнена")

    except Exception as e:
        conn.rollback()
        print("[ERROR]", e)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
