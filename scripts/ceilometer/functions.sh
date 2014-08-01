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
    echo $PID
}

check_running_and_amqp_connected () {
    if [ "$(id -u)" != "0" ]; then
        echo "$DAEMON is running but the script must be run as root"
        exit $STATE_WARNING
    fi

    if ! which netstat >/dev/null 2>&1
    then
        echo "netstat is not installed."
        exit $STATE_UNKNOWN
    fi

    # check_running can return multiple PIDs
    for PID in `check_running $1`
    do
        # Need root to "run netstat -p"
        KEY=$(netstat -epta 2>/dev/null | awk "{if (/amqp.*${PID}\/python/) {print ; exit}}")
        if ! test -z "$KEY"
        then
            echo "$DAEMON is working."
            exit $STATE_OK
        fi
    done

    echo "$DAEMON is not connected to AMQP"
    exit $STATE_CRITICAL
}
