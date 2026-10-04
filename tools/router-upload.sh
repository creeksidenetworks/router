#!/bin/bash
# ****************************************************************************
# VyOS/EdgeRouter configuration utility v2
# (c) Jackson Tong, Creekside Networks LLC.
# ****************************************************************************

cmd_usage() {
	cat >&2 <<-_EOF

  Usage: $PROGRAM [ OPTIONS ] [user@]router

    router: router's FQDN or IP address  
    -p: port
    -h: Print this help

    written by: Jackson Tong 2022 

	_EOF
}

port=""

while getopts 'p:P:h:' option
do
    case "${option}" in
        p|P) 
            port=${OPTARG};;
        h|H)
            cmd_usage
            exit 0;;
        *)
            exit 1;;
    esac
done

# Remove all options passed by getopts options
shift "$(($OPTIND -1))"

# Reading router fqdn/ip
if [ ! -z $1 ]; then
    router=$1
else
    echo "No router FQDN/IP is given."
    exit 1
fi

if [[ ${router%@*} == $router ]]; then
    userid="jtong"
else
    userid=${router%@*}
    router=${router#*@}
fi

WORK_DIR=${HOME}/work/$router

if [[ ! -d  ${WORK_DIR} ]]; then
    echo "   *** Can not find source: ${WORK_DIR}, exits"
    exit
fi

echo "upload ${WORK_DIR} to "

UPLOAD_FILE=$router.upload.tar.gz
tar -cz -f ${HOME}/tmp/${UPLOAD_FILE} -C ${WORK_DIR} config
if [[ $port == "" ]]; then
    scp  -o StrictHostKeyChecking=no ${HOME}/tmp/${UPLOAD_FILE}  $userid@$router:/tmp
    ssh  -o StrictHostKeyChecking=no -t $userid@$router "tar -xz -f /tmp/${UPLOAD_FILE} -C /tmp/"
else
    scp  -o StrictHostKeyChecking=no -p $port ${HOME}/tmp/${UPLOAD_FILE}  $userid@$router:/tmp
    ssh  -o StrictHostKeyChecking=no -p $port -t $userid@$router "tar -xz -f /tmp/${UPLOAD_FILE} -C /tmp/"
fi