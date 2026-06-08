#!/bin/sh

# Name:        update-gfw-list.sh
# Desription:  A shell script which convert gfwlist into dnsmasq rules for VyOS/EdgeOS routers.
#              Reference Cokebar Chi's gfwlist2dnsmasq.sh (https://github.com/cokebar)
# Version:     1.0.0 (2024.08.12)
# Author:      Jackson Tong

export PATH="/usr/sbin:/usr/bin:/sbin:/bin"

LOG_FILE="/var/log/gfw.log"
LOG_CAT="gfw"
IPSET_NAME=LIBERTY_ADDRESS_GRP
DNS_IP=8.8.8.8
DNS_PORT=53
CUSTOM_URL="https://raw.githubusercontent.com/creeksidenetworks/gfw/refs/heads/main/dnsmasq/dnsmasq_gfw_custom.conf"
CHINA_URL="https://raw.githubusercontent.com/creeksidenetworks/gfw/refs/heads/main/dnsmasq/dnsmasq_china_custom.conf"

# Check the operating system
if [[ "$(uname -s)" == "Darwin" ]]; then
    BASE64_DECODE='base64 -d -i'
else
    BASE64_DECODE='base64 -d'
fi

SED_ERES='sed -r'

# Function to log messages
log_message() {
    local message=$1
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    printf "%-10s %s %s: %s\n" "$timestamp" "$message" | sudo tee -a "$LOG_FILE" # > /dev/null

    # Ensure the log file does not exceed 1000 lines
    line_count=$(sudo wc -l < "$LOG_FILE")
    if [ "$line_count" -gt 1000 ]; then
        sudo tail -n 500 "$LOG_FILE" | sudo tee "$LOG_FILE.tmp" > /dev/null
        sudo mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
}

download_file() {
    local url=$1
    local output_file=$2

    TMP_FILE=$(mktemp)
    sudo curl -L $CURL_EXTARG -o $TMP_FILE $url
    if grep -q "404: Not Found" "$TMP_FILE"; then
        log_message "Failed to fetch from $url."
        rm -f $TMP_FILE
        clean_and_exit 2
    else
        sudo cp $TMP_FILE $output_file
        sudo chmod 644 $output_file
        rm -f $TMP_FILE
    fi
}

clean_and_exit(){
    # Clean up temp files
    printf '\nCleaning up... '

    rm -rf $TMP_DIR
    printf 'Done\n'
    [ $1 -eq 0 ] && printf 'Job Finished.\n\n' || printf 'Exit with Error code '$1'.\n'
    exit $1
}

# Function to parse command line arguments
parse_args() {
    while getopts ":o:c:" opt; do
        case $opt in
            o)
                CONF_PATH="$OPTARG"
                ;;
            c)
                CUSTOM_URL="$OPTARG"
                ;;
            \?)
                echo "Usage: $0 [-o <output path>] [-c <gfw-custom-url>]"
                exit 1
                ;;
        esac
    done
    shift $((OPTIND -1))
}


main() {
    # get the output file path
    BASE_PATH=$(dirname $(dirname "$(readlink -f "$0")"))
    CONF_PATH="$BASE_PATH/conf"

    parse_args "$@"

    echo "Dnsmasq conf dir: $CONF_PATH"

    mkdir -p "$CONF_PATH"

    OUT_FILE="$CONF_PATH/dnsmasq_gfw_github.conf"

    # Set Global Var
    BASE_URL='https://github.com/gfwlist/gfwlist/raw/master/gfwlist.txt'
    TMP_DIR=$(mktemp -d)

    BASE64_FILE="$TMP_DIR/base64.txt"
    GFWLIST_FILE="$TMP_DIR/gfwlist.txt"
    DOMAIN_TEMP_FILE="$TMP_DIR/gfwlist2domain.tmp"
    DOMAIN_FILE="$TMP_DIR/gfwlist2domain.txt"
    CONF_TMP_FILE="$TMP_DIR/gfwlist.conf.tmp"
    OUT_TMP_FILE="$TMP_DIR/gfwlist.out.tmp"

    # Fetch GfwList and decode it into plain text
    # Determine the interface for routing to 8.8.8.8
    #INTERFACE=$(ip -4 --oneline route show 8.8.8.8 | awk '{print $3}')
    INTERFACE=$(ip route get $DNS_IP | grep -o 'dev [^ ]*' | cut -d' ' -f2)

    # Check if the interface was found
    if [ ! -z "$INTERFACE" ]; then
        # Download the file to the temporary file using the jailbreak route
        CURL_EXTARG="--interface $INTERFACE"
    fi

    echo "Downloading GfwList from github from $INTERFACE"
    download_file "$BASE_URL" "$BASE64_FILE"

    $BASE64_DECODE "$BASE64_FILE" > $GFWLIST_FILE || ( echo 'Failed to decode gfwlist.txt. Quit.\n'; clean_and_exit 2 )

    # Convert
    IGNORE_PATTERN='^\!|\[|^@@|(https?://){0,1}[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'
    HEAD_FILTER_PATTERN='s#^(\|\|?)?(https?://)?##g'
    TAIL_FILTER_PATTERN='s#/.*$|%2F.*$##g'
    DOMAIN_PATTERN='([a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+)'
    HANDLE_WILDCARD_PATTERN='s#^(([a-zA-Z0-9]*\*[-a-zA-Z0-9]*)?(\.))?([a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+)(\*[a-zA-Z0-9]*)?#\4#g'

    #printf 'Converting GfwList to ' && echo $OUT_TYPE && printf ' ...\n' 
    #echo '\nWARNING:\nThe following lines in GfwList contain regex, and might be ignored:\n\n'
    #cat $GFWLIST_FILE | grep -n '^/.*$'
    #echo "\nThis script will try to convert some of the regex rules. But you should know this may not be a equivalent conversion.\nIf there's regex rules which this script do not deal with, you should add the domain manually to the list.\n\n"
    grep -vE $IGNORE_PATTERN $GFWLIST_FILE | $SED_ERES $HEAD_FILTER_PATTERN | $SED_ERES $TAIL_FILTER_PATTERN | grep -E $DOMAIN_PATTERN | $SED_ERES $HANDLE_WILDCARD_PATTERN > $DOMAIN_TEMP_FILE

    printf 'google.com\ngoogle.ad\ngoogle.ae\ngoogle.com.af\ngoogle.com.ag\ngoogle.com.ai\ngoogle.al\ngoogle.am\ngoogle.co.ao\ngoogle.com.ar\ngoogle.as\ngoogle.at\ngoogle.com.au\ngoogle.az\ngoogle.ba\ngoogle.com.bd\ngoogle.be\ngoogle.bf\ngoogle.bg\ngoogle.com.bh\ngoogle.bi\ngoogle.bj\ngoogle.com.bn\ngoogle.com.bo\ngoogle.com.br\ngoogle.bs\ngoogle.bt\ngoogle.co.bw\ngoogle.by\ngoogle.com.bz\ngoogle.ca\ngoogle.cd\ngoogle.cf\ngoogle.cg\ngoogle.ch\ngoogle.ci\ngoogle.co.ck\ngoogle.cl\ngoogle.cm\ngoogle.cn\ngoogle.com.co\ngoogle.co.cr\ngoogle.com.cu\ngoogle.cv\ngoogle.com.cy\ngoogle.cz\ngoogle.de\ngoogle.dj\ngoogle.dk\ngoogle.dm\ngoogle.com.do\ngoogle.dz\ngoogle.com.ec\ngoogle.ee\ngoogle.com.eg\ngoogle.es\ngoogle.com.et\ngoogle.fi\ngoogle.com.fj\ngoogle.fm\ngoogle.fr\ngoogle.ga\ngoogle.ge\ngoogle.gg\ngoogle.com.gh\ngoogle.com.gi\ngoogle.gl\ngoogle.gm\ngoogle.gp\ngoogle.gr\ngoogle.com.gt\ngoogle.gy\ngoogle.com.hk\ngoogle.hn\ngoogle.hr\ngoogle.ht\ngoogle.hu\ngoogle.co.id\ngoogle.ie\ngoogle.co.il\ngoogle.im\ngoogle.co.in\ngoogle.iq\ngoogle.is\ngoogle.it\ngoogle.je\ngoogle.com.jm\ngoogle.jo\ngoogle.co.jp\ngoogle.co.ke\ngoogle.com.kh\ngoogle.ki\ngoogle.kg\ngoogle.co.kr\ngoogle.com.kw\ngoogle.kz\ngoogle.la\ngoogle.com.lb\ngoogle.li\ngoogle.lk\ngoogle.co.ls\ngoogle.lt\ngoogle.lu\ngoogle.lv\ngoogle.com.ly\ngoogle.co.ma\ngoogle.md\ngoogle.me\ngoogle.mg\ngoogle.mk\ngoogle.ml\ngoogle.com.mm\ngoogle.mn\ngoogle.ms\ngoogle.com.mt\ngoogle.mu\ngoogle.mv\ngoogle.mw\ngoogle.com.mx\ngoogle.com.my\ngoogle.co.mz\ngoogle.com.na\ngoogle.com.nf\ngoogle.com.ng\ngoogle.com.ni\ngoogle.ne\ngoogle.nl\ngoogle.no\ngoogle.com.np\ngoogle.nr\ngoogle.nu\ngoogle.co.nz\ngoogle.com.om\ngoogle.com.pa\ngoogle.com.pe\ngoogle.com.pg\ngoogle.com.ph\ngoogle.com.pk\ngoogle.pl\ngoogle.pn\ngoogle.com.pr\ngoogle.ps\ngoogle.pt\ngoogle.com.py\ngoogle.com.qa\ngoogle.ro\ngoogle.ru\ngoogle.rw\ngoogle.com.sa\ngoogle.com.sb\ngoogle.sc\ngoogle.se\ngoogle.com.sg\ngoogle.sh\ngoogle.si\ngoogle.sk\ngoogle.com.sl\ngoogle.sn\ngoogle.so\ngoogle.sm\ngoogle.sr\ngoogle.st\ngoogle.com.sv\ngoogle.td\ngoogle.tg\ngoogle.co.th\ngoogle.com.tj\ngoogle.tk\ngoogle.tl\ngoogle.tm\ngoogle.tn\ngoogle.to\ngoogle.com.tr\ngoogle.tt\ngoogle.com.tw\ngoogle.co.tz\ngoogle.com.ua\ngoogle.co.ug\ngoogle.co.uk\ngoogle.com.uy\ngoogle.co.uz\ngoogle.com.vc\ngoogle.co.ve\ngoogle.vg\ngoogle.co.vi\ngoogle.com.vn\ngoogle.vu\ngoogle.ws\ngoogle.rs\ngoogle.co.za\ngoogle.co.zm\ngoogle.co.zw\ngoogle.cat\n' >> $DOMAIN_TEMP_FILE
    #printf 'Google search domains... ' && echo 'Added\n'

    # Add blogspot domains
    printf 'blogspot.ca\nblogspot.co.uk\nblogspot.com\nblogspot.com.ar\nblogspot.com.au\nblogspot.com.br\nblogspot.com.by\nblogspot.com.co\nblogspot.com.cy\nblogspot.com.ee\nblogspot.com.eg\nblogspot.com.es\nblogspot.com.mt\nblogspot.com.ng\nblogspot.com.tr\nblogspot.com.uy\nblogspot.de\nblogspot.gr\nblogspot.in\nblogspot.mx\nblogspot.ch\nblogspot.fr\nblogspot.ie\nblogspot.it\nblogspot.pt\nblogspot.ro\nblogspot.sg\nblogspot.be\nblogspot.no\nblogspot.se\nblogspot.jp\nblogspot.in\nblogspot.ae\nblogspot.al\nblogspot.am\nblogspot.ba\nblogspot.bg\nblogspot.ch\nblogspot.cl\nblogspot.cz\nblogspot.dk\nblogspot.fi\nblogspot.gr\nblogspot.hk\nblogspot.hr\nblogspot.hu\nblogspot.ie\nblogspot.is\nblogspot.kr\nblogspot.li\nblogspot.lt\nblogspot.lu\nblogspot.md\nblogspot.mk\nblogspot.my\nblogspot.nl\nblogspot.no\nblogspot.pe\nblogspot.qa\nblogspot.ro\nblogspot.ru\nblogspot.se\nblogspot.sg\nblogspot.si\nblogspot.sk\nblogspot.sn\nblogspot.tw\nblogspot.ug\nblogspot.cat\n' >> $DOMAIN_TEMP_FILE
    #printf 'Blogspot domains... ' && echo 'Added\n'

    # Add twimg.edgesuite.net
    printf 'twimg.edgesuite.net\n' >> $DOMAIN_TEMP_FILE
    #printf 'twimg.edgesuite.net... ' && echo 'Added\n'

    #echo 'Ipset rules included.'
    sort -u $DOMAIN_TEMP_FILE | $SED_ERES 's#(.+)#server=/\1/'$DNS_IP'\#'$DNS_PORT'\
ipset=/\1/'$IPSET_NAME'#g' > $CONF_TMP_FILE

    # Generate output file
    echo '# Dnsmasq rules generated from gfwlist' > $OUT_TMP_FILE
    echo "# Updated on $(date "+%Y-%m-%d %H:%M:%S")" >> $OUT_TMP_FILE
    echo '# ' >> $OUT_TMP_FILE
    cat $CONF_TMP_FILE >> $OUT_TMP_FILE
    sudo cp $OUT_TMP_FILE $OUT_FILE
    sudo chmod 755 $OUT_FILE
    #printf '\nConverting GfwList to '$OUT_TYPE'... ' && echo 'Done\n\n'

    # Download custom dnsmasq-ipset rules
    echo "Downloading custom dnsmasq-ipset rules from: $CUSTOM_URL"
    download_file "$CUSTOM_URL" "${CONF_PATH}/dnsmasq_gfw_custom.conf"

    # Download custom dnsmasq-ipset rules
    echo "Downloading China dnsmasq-ipset rules from: $CHINA_URL"
    download_file "$CHINA_URL" "${CONF_PATH}/dnsmasq_china_custom.conf"

    if [ -f /etc/openwrt_release ]; then
        /etc/init.d/dnsmasq restart
    elif [[ "$(uname -s)" == "Linux" ]]; then
        sudo systemctl restart dnsmasq
    fi 

    log_message "Gfw dnsmasq ipset list updated"

    # Clean up
    clean_and_exit 0
}

main "$@"
