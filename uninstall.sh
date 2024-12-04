#!/usr/bin/env bash

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Exiting."
    exit 1
fi

pkgname=yawns

rm -rf /usr/share/$pkgname
rm -rf /usr/bin/$pkgname
