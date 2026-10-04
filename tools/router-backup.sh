#!/bin/bash
# VyOS/EdgeRouter configuration utility v1
# Now support interactive 
# (c) 2021 Creekside Networks LLC, Jackson Tong
# Usage: ssh -t ip "$(<./router-setup.sh)"

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

echo "create tar file on $userid@$router:$port"
if [[ $port == "" ]]; then
    ssh -o StrictHostKeyChecking=no $userid@$router "sudo tar --exclude=/config/archive --exclude=/config/config.boot.* --exclude=/config/user-data/ftp -czf /tmp/$router.tar.gz /config"
else
    ssh -p $port -o StrictHostKeyChecking=no $userid@$router "sudo tar --exclude=/config/archive --exclude=/config/config.boot.* --exclude=/config/user-data/ftp -czf /tmp/$router.tar.gz /config"
fi

if [ ! -d ${HOME}/tmp ]; then 
   mkdir ${HOME}/tmp
fi

backupfile=${HOME}/tmp/$router.tar.gz

echo "download tar file from $userid@$router:$port"
if [[ $port == "" ]]; then
    scp -o StrictHostKeyChecking=no $userid@$router:/tmp/$router.tar.gz ${HOME}/tmp/
else
    scp -P $port -o StrictHostKeyChecking=no $userid@$router:/tmp/$router.tar.gz ${HOME}/tmp/
fi

echo "untar to ${HOME}/work/$router"
if [ -f ${backupfile} ]; then
    WORK_DIR="${HOME}/work/$router"
    mkdir -p $WORK_DIR
    echo -e "\nExtract to $WORK_DIR\n"
    tar -xf ${backupfile} -C $WORK_DIR/
else
    echo -e "\n***File download failure, exit\n"
    exit 1
fi

