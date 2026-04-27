# migrate_scenario_cycles.py
# Миграционный скрипт БД для правок под новый конструктор сценариев. 27.04.2026

import sqlite3
from pathlib import Path

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

        conn.commit()
        print("[OK] Миграция выполнена")

    except Exception as e:
        conn.rollback()
        print("[ERROR]", e)

    finally:
        conn.close()


if __name__ == "__main__":
    main()