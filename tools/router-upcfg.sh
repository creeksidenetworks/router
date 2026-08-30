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

CONFIG_FILE=${HOME}/work/$router/config/config.boot

if [[ ! -f ${CONFIG_FILE} ]]; then
    echo "   *** Can not find source: ${CONFIG_FILE}, exits"
    exit
fi

echo "upload ${CONFIG_FILE} to ${router}"

if [[ $port == "" ]]; then
    ssh -o StrictHostKeyChecking=no $userid@$router "sudo rm -f /tmp/config.boot"
    scp -o StrictHostKeyChecking=no ${CONFIG_FILE} $userid@$router:/tmp
else
    ssh -o StrictHostKeyChecking=no -p $port $userid@$router "sudo rm -f /tmp/config.boot"
    scp -o StrictHostKeyChecking=no -P $port ${CONFIG_FILE} $userid@$router:/tmp
fi