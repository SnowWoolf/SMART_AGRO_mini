#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/agro}"
REPO_URL="${REPO_URL:-https://github.com/SnowWoolf/SMART_AGRO_mini.git}"
BRANCH="${BRANCH:-main}"
WEB_SERVICE="${WEB_SERVICE:-agrosmart_web}"
SYNC_SERVICE="${SYNC_SERVICE:-agrosmart_sync}"

TMP_DIR="$(mktemp -d)"
REPO_DIR="$TMP_DIR/repo"
UPDATED_LIST="$TMP_DIR/updated_files.txt"
ADDED_LIST="$TMP_DIR/added_files.txt"
NOUPD_LIST="$TMP_DIR/noupd_files.txt"
BACKUP_TAR="$TMP_DIR/app_backup.tar"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

log() {
    printf '%s\n' "$*"
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

is_excluded() {
    local rel_path="$1"
    local base_name
    base_name="$(basename "$rel_path")"

    case "$base_name" in
        config.py|.env|*.db|main.html|main2.js)
            return 0
            ;;
    esac

    case "$rel_path" in
        .git/*|camera_archive/*)
            return 0
            ;;
    esac

    return 1
}

extract_version() {
    local file_path="$1"
    local first_line

    [ -f "$file_path" ] || return 1
    IFS= read -r first_line < "$file_path" || return 1

    case "$first_line" in
        *UI_VERSION:*)
            printf '%s\n' "${first_line#*UI_VERSION:}" | sed 's/^[[:space:]]*//; s/[[:space:]>*/]*$//'
            ;;
        *VERSION:*)
            printf '%s\n' "${first_line#*VERSION:}" | sed 's/^[[:space:]]*//; s/[[:space:]>*/]*$//'
            ;;
        *)
            return 1
            ;;
    esac
}

extract_file_version() {
    local file_path="$1"
    local first_line

    [ -f "$file_path" ] || return 1
    IFS= read -r first_line < "$file_path" || return 1

    if [[ "$first_line" =~ ^[[:space:]]*(univ-)?[0-9]+\.[0-9]+\.[0-9]{6}([.-][0-9]+)?[[:space:]]*$ ]]; then
        printf '%s\n' "$first_line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
        return 0
    fi

    return 1
}

read_version() {
    local file_path="$1"

    extract_version "$file_path" || extract_file_version "$file_path"
}

version_key() {
    local version="$1"
    local normalized date_part seq_part day month year

    normalized="${version#univ-}"
    normalized="${normalized#v}"
    normalized="${normalized#2.0.}"
    normalized="${normalized//-/.}"

    date_part="${normalized%%.*}"
    seq_part="0"
    if [ "$normalized" != "$date_part" ]; then
        seq_part="${normalized#*.}"
        seq_part="${seq_part%%.*}"
    fi

    if ! [[ "$date_part" =~ ^[0-9]{6}$ ]]; then
        printf '00000000%04d\n' 0
        return
    fi

    day="${date_part:0:2}"
    month="${date_part:2:2}"
    year="${date_part:4:2}"

    if ! [[ "$seq_part" =~ ^[0-9]+$ ]]; then
        seq_part="0"
    fi

    printf '20%s%s%s%04d\n' "$year" "$month" "$day" "$seq_part"
}

is_remote_newer() {
    local local_version="$1"
    local remote_version="$2"
    local local_key remote_key

    local_key="$(version_key "$local_version")"
    remote_key="$(version_key "$remote_version")"

    [ "$remote_key" -gt "$local_key" ]
}

is_noupd_version() {
    local version="$1"

    [[ "$version" == *-noupd ]]
}

stop_services() {
    log "Stopping services..."
    systemctl stop "$WEB_SERVICE"
    systemctl stop "$SYNC_SERVICE"
}

print_service_status() {
    local service_name="$1"

    log "Status for $service_name:"
    systemctl status "$service_name" --no-pager -l || true
}

wait_service_active() {
    local service_name="$1"
    local timeout_sec="${2:-30}"
    local elapsed=0

    while [ "$elapsed" -lt "$timeout_sec" ]; do
        if systemctl is-active --quiet "$service_name"; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    return 1
}

check_services_stable() {
    local delay_sec="${1:-10}"

    log "Waiting ${delay_sec}s to verify services remain active..."
    sleep "$delay_sec"

    if ! systemctl is-active --quiet "$SYNC_SERVICE"; then
        log "$SYNC_SERVICE is not active after ${delay_sec}s."
        print_service_status "$SYNC_SERVICE"
        return 1
    fi

    if ! systemctl is-active --quiet "$WEB_SERVICE"; then
        log "$WEB_SERVICE is not active after ${delay_sec}s."
        print_service_status "$WEB_SERVICE"
        return 1
    fi

    return 0
}

start_and_check_services() {
    log "Starting and checking services..."

    if ! systemctl start "$SYNC_SERVICE"; then
        log "Failed to start $SYNC_SERVICE."
        print_service_status "$SYNC_SERVICE"
        return 1
    fi

    if ! wait_service_active "$SYNC_SERVICE" 30; then
        log "$SYNC_SERVICE did not become active."
        print_service_status "$SYNC_SERVICE"
        return 1
    fi

    if ! systemctl start "$WEB_SERVICE"; then
        log "Failed to start $WEB_SERVICE."
        print_service_status "$WEB_SERVICE"
        return 1
    fi

    if ! wait_service_active "$WEB_SERVICE" 30; then
        log "$WEB_SERVICE did not become active."
        print_service_status "$WEB_SERVICE"
        return 1
    fi

    if ! check_services_stable 10; then
        return 1
    fi

    return 0
}

backup_all_files() {
    log "Creating full file backup..."
    tar -C "$APP_DIR" \
        --exclude='./.git' \
        --exclude='./camera_archive' \
        -cpf "$BACKUP_TAR" .
}

restore_backup() {
    log "Restoring files from backup..."

    while IFS= read -r rel_path; do
        if [ -n "$rel_path" ]; then
            rm -f "$APP_DIR/$rel_path"
        fi
    done < "$ADDED_LIST"

    tar -C "$APP_DIR" -xpf "$BACKUP_TAR"
}

confirm_rollback() {
    local answer

    while true; do
        printf 'Выполнить откат из backup? [yes/no]: '
        IFS= read -r answer

        case "$answer" in
            yes|y|YES|Y)
                return 0
                ;;
            no|n|NO|N)
                return 1
                ;;
            *)
                log "Введите yes или no."
                ;;
        esac
    done
}

rollback_and_fail() {
    local reason="$1"
    local restore_status
    local service_status

    log "ERROR: $reason"

    if ! confirm_rollback; then
        fail "Update failed without rollback: $reason"
    fi

    log "Rolling back update..."

    set +e
    systemctl stop "$WEB_SERVICE"
    systemctl stop "$SYNC_SERVICE"
    restore_backup
    restore_status=$?
    start_and_check_services
    service_status=$?
    set -e

    if [ "$restore_status" -ne 0 ]; then
        log "ERROR: Backup restore failed with code $restore_status."
    else
        log "Backup restored successfully."
    fi

    if [ "$service_status" -ne 0 ]; then
        log "ERROR: Services did not start correctly after rollback."
    else
        log "Services started successfully after rollback."
    fi

    fail "Update failed: $reason"
}

add_update() {
    local rel_path="$1"

    printf '%s\n' "$rel_path" >> "$UPDATED_LIST"
}

add_noupd() {
    local rel_path="$1"

    printf '%s\n' "$rel_path" >> "$NOUPD_LIST"
}

print_noupd_warning() {
    if [ ! -s "$NOUPD_LIST" ]; then
        return
    fi

    log "ВНИМАНИЕ! Необходимо вручную проверить и обновить содержимое файлов:"
    sed 's/^/ - /' "$NOUPD_LIST"
}

require_command git
require_command systemctl
require_command find
require_command sed
require_command tar

[ -d "$APP_DIR" ] || fail "Application directory does not exist: $APP_DIR"

log "Cloning $REPO_URL branch $BRANCH..."
git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR" >/dev/null 2>&1

: > "$UPDATED_LIST"
: > "$ADDED_LIST"
: > "$NOUPD_LIST"

while IFS= read -r -d '' remote_file; do
    rel_path="${remote_file#$REPO_DIR/}"

    if is_excluded "$rel_path"; then
        continue
    fi

    remote_version="$(read_version "$remote_file" || true)"
    if [ -z "$remote_version" ]; then
        continue
    fi

    local_file="$APP_DIR/$rel_path"
    local_version="$(read_version "$local_file" || true)"

    if [ ! -f "$local_file" ]; then
        log "Will add: $rel_path ($remote_version)"
        add_update "$rel_path"
        printf '%s\n' "$rel_path" >> "$ADDED_LIST"
        continue
    fi

    if is_noupd_version "$local_version"; then
        log "Skip update: $rel_path ($local_version)"
        add_noupd "$rel_path"
        continue
    fi

    if [ -z "$local_version" ]; then
        log "Will update: $rel_path (local VERSION missing -> $remote_version)"
        add_update "$rel_path"
        continue
    fi

    if is_remote_newer "$local_version" "$remote_version"; then
        log "Will update: $rel_path ($local_version -> $remote_version)"
        add_update "$rel_path"
    fi
done < <(find "$REPO_DIR" -type f -not -path "$REPO_DIR/.git/*" -print0)

if [ ! -s "$UPDATED_LIST" ]; then
    log "No updates found."
    print_noupd_warning
    exit 0
fi

if ! stop_services; then
    start_and_check_services || true
    fail "Failed to stop services. Update cancelled."
fi

if ! backup_all_files; then
    start_and_check_services || true
    fail "Failed to create backup. Update cancelled."
fi

set +e
while IFS= read -r rel_path; do
    mkdir -p "$(dirname "$APP_DIR/$rel_path")"
    cp -p "$REPO_DIR/$rel_path" "$APP_DIR/$rel_path"
    copy_status=$?
    if [ "$copy_status" -ne 0 ]; then
        break
    fi
done < "$UPDATED_LIST"
set -e

if [ "${copy_status:-0}" -ne 0 ]; then
    rollback_and_fail "File copy failed with code $copy_status."
fi

if ! start_and_check_services; then
    rollback_and_fail "One or more services failed to start after update."
fi

log "Updated files:"
sed 's/^/ - /' "$UPDATED_LIST"
print_noupd_warning
