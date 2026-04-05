#!/bin/sh
# Ждём, пока backend станет доступен для резолвинга
echo "Waiting for backend to be resolvable..."
for i in $(seq 1 30); do
    if getent hosts backend > /dev/null 2>&1; then
        echo "Backend resolved!"
        exec nginx -g 'daemon off;'
    fi
    echo "Attempt $i: backend not yet resolvable, waiting..."
    sleep 1
done

echo "ERROR: Could not resolve backend after 30 seconds"
echo "Starting nginx anyway (proxy will fail)..."
exec nginx -g 'daemon off;'
