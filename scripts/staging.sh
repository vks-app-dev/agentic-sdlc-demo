#!/usr/bin/env bash
# Local staging for the SDLC Pilot Release stage: the committed code runs from its own git worktree
# (.staging/app) on port 8200 with its own database (.staging/expenses.db), separate from your dev copy.
#   scripts/staging.sh deploy     # deploy HEAD (the previous commit is kept for rollback)
#   scripts/staging.sh rollback   # go back to the previously deployed commit
#   scripts/staging.sh stop
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
DIR=.staging
APP=$DIR/app
PORT=${STAGING_PORT:-8200}
mkdir -p "$DIR"

stop() {
  if [[ -f $DIR/pid ]]; then
    kill "$(cat $DIR/pid)" 2>/dev/null || true
    rm -f $DIR/pid
  fi
  # anything else still holding the port (e.g. a run that lost its pid file)
  lsof -ti "tcp:$PORT" 2>/dev/null | xargs -r kill 2>/dev/null || true
}

start() {  # $1 = commit
  [[ -d $APP ]] || git worktree add --detach "$APP" "$1" >/dev/null
  git -C "$APP" checkout --quiet --detach "$1"
  stop
  (cd "$APP" && EXPENSE_DB_PATH="$PWD/../expenses.db" nohup uv run --with uvicorn uvicorn app.main:app \
      --host 127.0.0.1 --port "$PORT" > ../app.log 2>&1 & echo $! > ../pid)
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      echo "$1" > $DIR/current
      echo "staging: $(git rev-parse --short "$1") on http://127.0.0.1:$PORT"
      return 0
    fi
    sleep 1
  done
  echo "staging did not become healthy; last log lines:" >&2
  tail -20 $DIR/app.log >&2
  return 1
}

case "${1:-}" in
  deploy)
    new=$(git rev-parse HEAD)
    if [[ -f $DIR/current && "$(cat $DIR/current)" != "$new" ]]; then cp $DIR/current $DIR/previous; fi
    start "$new" ;;
  rollback)
    [[ -f $DIR/previous ]] || { echo "nothing to roll back to: only one version was deployed" >&2; exit 1; }
    start "$(cat $DIR/previous)" ;;
  stop) stop; echo "staging stopped" ;;
  *) echo "usage: scripts/staging.sh deploy|rollback|stop" >&2; exit 2 ;;
esac
