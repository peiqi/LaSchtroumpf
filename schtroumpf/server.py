#Copyright PeiqiSHI 2016
 
import os
import sys
import subprocess


from logging import Logger
import logging.config
from ConfigParser import SafeConfigParser, NoSectionError
from optparse import OptionParser

from cli.api import API
from common import logDecorator
 
@logDecorator.log
def runcommand(command):
    process = subprocess.Popen(command, shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    output = []
    while True:
        tmpline = process.stdout.readline().strip("\n")
        if tmpline == '' and process.poll() is not None:
            break
        if tmpline != '':
            output.extend(tmpline)
    exitCode = process.returncode

def laschtroumpf():
    usage = "usage: %prog [options] (see --help)"
    parser = OptionParser(usage)
    parser.add_option("--config-file", dest="configFile",
                      help="config file of LaSchtroumpf",
                      default="/home/LaSchtroumpf/config/config.conf")
    parser.add_option("--log-file", dest="logFile",
                      help="log file of LaSchtroumpf",
                      default="/home/LaSchtroumpf/config/log.conf")
    options, args = parser.parse_args()

    if not os.path.isfile(options.logFile):
        print "log file doesn't found at %s" % options.logFile
        logging.basicConfig()
    else:
        try: 
            logging.config.fileConfig(options.logFile)
        except Exception as e:
            print "log file creation failed, please verify "\
                  "the directory and create it manually if possible"
    
    config = options.configFile
 
if __name__ == '__main__':
    laschtroumpf()
    instance = API()
    print instance._print
    runcommand("sudo ovs-vsctl show")
