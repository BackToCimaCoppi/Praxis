#!/usr/bin/env bash

set -u
set -o pipefail

usage() {
  printf '%s\n' \
    'Usage:' \
    '  cursor-review-runner.sh --action status|models|login --output-file <abs> --log-file <abs> --status-file <abs> [--timeout <seconds>]' \
    '  cursor-review-runner.sh --action review --workspace <abs> --prompt-file <abs> --model <id> --output-file <abs> --log-file <abs> --status-file <abs> [--timeout <seconds>]'
}

fail() {
  printf 'cursor-review-runner: %s\n' "$1" >&2
  exit 2
}

action=''
workspace=''
prompt_file=''
model=''
output_file=''
log_file=''
status_file=''
timeout_seconds=3600

while [[ $# -gt 0 ]]; do
  case "$1" in
    --action)
      [[ $# -ge 2 ]] || fail '--action 缺少值'
      action=$2
      shift 2
      ;;
    --workspace)
      [[ $# -ge 2 ]] || fail '--workspace 缺少值'
      workspace=$2
      shift 2
      ;;
    --prompt-file)
      [[ $# -ge 2 ]] || fail '--prompt-file 缺少值'
      prompt_file=$2
      shift 2
      ;;
    --model)
      [[ $# -ge 2 ]] || fail '--model 缺少值'
      model=$2
      shift 2
      ;;
    --output-file)
      [[ $# -ge 2 ]] || fail '--output-file 缺少值'
      output_file=$2
      shift 2
      ;;
    --log-file)
      [[ $# -ge 2 ]] || fail '--log-file 缺少值'
      log_file=$2
      shift 2
      ;;
    --status-file)
      [[ $# -ge 2 ]] || fail '--status-file 缺少值'
      status_file=$2
      shift 2
      ;;
    --timeout)
      [[ $# -ge 2 ]] || fail '--timeout 缺少值'
      timeout_seconds=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "未知参数：$1"
      ;;
  esac
done

case "$action" in
  status|models|login|review) ;;
  *) fail '--action 只允许 status、models、login、review' ;;
esac

for required_path in "$output_file" "$log_file" "$status_file"; do
  [[ -n "$required_path" ]] || fail '缺少输出、日志或状态文件参数'
  [[ "$required_path" = /* ]] || fail "运行文件必须是绝对路径：$required_path"
  [[ -d "$(dirname "$required_path")" ]] || fail "父目录不存在：$required_path"
done

[[ "$output_file" != "$log_file" && "$output_file" != "$status_file" && "$log_file" != "$status_file" ]] \
  || fail '输出、日志与状态文件必须互不相同'
[[ ! -e "$status_file" ]] || fail "状态文件已存在，请为本轮使用新的临时路径：$status_file"
[[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || fail '--timeout 必须是正整数秒'

if [[ "$action" == 'review' ]]; then
  [[ "$workspace" = /* && -d "$workspace" ]] || fail 'review 必须提供存在的绝对 workspace 路径'
  [[ "$prompt_file" = /* && -f "$prompt_file" ]] || fail 'review 必须提供存在的绝对 prompt 文件'
  [[ "$model" =~ ^[A-Za-z0-9._-]+$ ]] || fail 'model ID 含非法字符或为空'
fi

cursor_bin=$(command -v cursor-agent 2>/dev/null || true)
[[ -n "$cursor_bin" ]] || fail '找不到 cursor-agent'

write_status() {
  local value=$1
  local status_tmp="${status_file}.tmp.$$"
  printf '%s\n' "$value" > "$status_tmp"
  mv "$status_tmp" "$status_file"
}

run_action() {
  case "$action" in
    status)
      "$cursor_bin" status
      ;;
    models)
      "$cursor_bin" --list-models
      ;;
    login)
      NO_OPEN_BROWSER=1 "$cursor_bin" login
      ;;
    review)
      cd "$workspace" || return 2
      "$cursor_bin" \
        --print \
        --mode ask \
        --model "$model" \
        --workspace "$workspace" \
        --output-format text \
        --sandbox enabled \
        --trust \
        < "$prompt_file"
      ;;
  esac
}

run_and_record() {
  local result=0
  run_action > "$output_file" 2> "$log_file" || result=$?
  write_status "$result"
  return "$result"
}

if [[ "${CURSOR_TERMINAL_RELAY_CHILD:-0}" == '1' ]]; then
  run_and_record
  exit $?
fi

probe_output=$($cursor_bin --version 2>&1)
probe_status=$?
if [[ $probe_status -eq 0 ]]; then
  run_and_record
  exit $?
fi

if [[ "$(uname -s)" != 'Darwin' || "$probe_output" != *'login keychain is locked'* ]]; then
  printf '%s\n' "$probe_output" > "$log_file"
  write_status "$probe_status"
  exit "$probe_status"
fi

runner_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
runner_path="$runner_dir/$(basename "${BASH_SOURCE[0]}")"
terminal_args=(
  env CURSOR_TERMINAL_RELAY_CHILD=1
  "$runner_path"
  --action "$action"
  --output-file "$output_file"
  --log-file "$log_file"
  --status-file "$status_file"
  --timeout "$timeout_seconds"
)

if [[ "$action" == 'review' ]]; then
  terminal_args+=(
    --workspace "$workspace"
    --prompt-file "$prompt_file"
    --model "$model"
  )
fi

printf -v terminal_command '%q ' "${terminal_args[@]}"
terminal_command="${terminal_command% }"
terminal_command="$terminal_command; exit"

if ! osascript - "$terminal_command" <<'APPLESCRIPT' >/dev/null
on run argv
  tell application "Terminal"
    do script (item 1 of argv)
  end tell
end run
APPLESCRIPT
then
  printf '%s\n' '无法通过 Terminal 启动 Cursor；请确认 Terminal 可用且已允许自动化。' > "$log_file"
  write_status 2
  exit 2
fi

deadline=$((SECONDS + timeout_seconds))
while [[ ! -f "$status_file" ]]; do
  if [[ $SECONDS -ge $deadline ]]; then
    printf '等待 Terminal 中的 Cursor 超时（%s 秒）。\n' "$timeout_seconds" >> "$log_file"
    exit 124
  fi
  sleep 1
done

recorded_status=$(tr -d '[:space:]' < "$status_file")
[[ "$recorded_status" =~ ^[0-9]+$ ]] || fail "状态文件内容非法：$status_file"
exit "$recorded_status"
