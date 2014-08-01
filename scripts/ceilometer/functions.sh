STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3
STATE_DEPENDENT=4

check_running () {
    PID=`pidof -x "$1" || true`
    if [ -z "$PID" ]; then
        echo "$DAEMON is not running."
        exit $STATE_CRITICAL
    fi
}
