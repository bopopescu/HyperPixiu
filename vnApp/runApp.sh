TOPDIR=$(realpath $(dirname $0)/..)
PYTHON=/usr/bin/python3
PROGRAM=$1
export LANG="en_US.UTF-8"
env "PYTHONPATH=${TOPDIR}:${TOPDIR}/kits/vnpy" "PYTHONIOENCODING=UTF-8" "PYTHONUNBUFFERED=1" ${PYTHON} ${PROGRAM}

