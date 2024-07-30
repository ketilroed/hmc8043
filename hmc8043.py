"""
hmc8043.py
@author: ketilroe
Controlling HMC power supply
"""


import sys
import serial
from serial.tools import list_ports
import time
import logging
import threading
import queue
import argparse
import os
from datetime import datetime

menu_data = {
    'title': "HMC 8043",
    'options': [
        {'title': "set com port", 'desc': "List and choose com port"},
        {'title': "open com port", 'desc': "Open com port"},
        {'title': "close com port", 'desc': "Close com port"},
        {'title': "get id", 'desc': "Get instrument ID"},
        {'title': "reset", 'desc': "Reset instrument"},
        #{'title': "config", 'desc': "Configure instrument"},
        #{'title': "print config", 'desc': "Print configuration settings"},

        {'title': "set channel <#>", 'desc': "Set ouput channel number"},
        {'title': "set ouput <ch#> <V-value> <I-limit> ", 'desc': "Set channel voltage ouput value and current limit"},
        {'title': "output <ch#> <on|off>", 'desc': "Turn output on/off for ch#"},
        {'title': "master output <on|off>", 'desc': "Turn master output on/off"},
        {'title': "off", 'desc': "Turn all outputs off"},
        

        #{'title': "sense prot <value>", 'desc': "Set sense protection limit value"},
        {'title': "set logfile  <name>", 'desc': "Name of logfile for data (default: data.log)"},
        #{'title': "start meas time <time in sec>", 'desc': "Start continuous measurement series (value: time[s],-1=infinite"},
        #{'title': "start meas rep <N>", 'desc': "Start measurement series with N repititions"},
        #{'title': "start meas sweep <start> <stop> <#steps> <slimit>", 'desc': "Start measurement sweep"},

        #        {'title': "enable ramp", 'desc': "Source value will be ramped up/down"},
       ##{'title': "disable ramp", 'desc': "Disable ramp"},
        #{'title': "stop meas", 'desc': "Cancel active  measurement"},
        #{'title': "set no triggers <N>", 'desc': "Set number of triggers"},
    ]
}

def keyboard(cmd_queue,run):
    while run():
        cmd = input("\r\n>")
        cmd_queue.put(cmd.lower())
        time.sleep(0.5)

class HMC8043(threading.Thread):

    def __init__(self,name,log_name):

        threading.Thread.__init__(self)
        self.thread_name = name
        self.log = logging.getLogger(log_name)
        self.menu_data = menu_data
        self.instrument_id = ''
        self.__exitFlag = False
        self.__signal_lock = threading.Lock()
        self._serial_port = None
        self._baud_rate = 57600
        self._sub_cmd = ''
        self._ser = None
        self.config = {"source": "VOLT",
                    "source_value": 0,
                    "sense": "CURR",
                    "source_range": "AUTO ON",
                    "sense_range": "AUTO ON",
                    "source_mode": "FIXED",
                    "sense_protection_limit": 105e-3,
                    "source_delay": 0.1,
                    "no_triggers": 1,
                    "sense_elements": "VOLT,CURR"
                    }
        self.cmd_list = []
        self.datalogfile = "data.log"
        self.data_queue = queue.Queue(1000)
        self.timestamp_start = 0

        self._meas_flag = False
        self.meas_thread = 0
        self._ramp_steps = 10
        self._ramp = False
        self.config_file = ''







    def run(self):
        self.log.debug("Starting HMC 8043 thread \"%s\"", self.thread_name)
        while not self.__exitFlag:
            time.sleep(1)
            continue

    def stop(self):
        self.log.debug("Exiting HMC 8043 thread \"%s\"", self.thread_name)
        if self._meas_flag == True:
            self.meas_thread.join()
            self._meas_flag = False
            #self.datalog_thread.join()
        if (self._ser is not None):
            #self._output_disable()
            self._close_connection()

        with self.__signal_lock:
            self.__exitFlag = True

    def print_menu(self):
        self._sub_cmd = ''
        sys.stdout.write(self.menu_data["title"] + " options:\r\n")
        for opt in self.menu_data["options"]:
            cmd =  "\"" + opt["title"] + "\""
            desc = opt["desc"]
            sys.stdout.write("{:40s}{:s}\r\n".format(cmd,desc))

    def decode_cmd(self,cmd):

        if self._sub_cmd == "com":
            ports = get_serial_ports()
            if cmd.isnumeric():

                if int(cmd) in ports:
                    self._set_serial_port(ports[int(cmd)])
                else:
                    sys.stdout.write("Invalid com port")
            else:
                sys.stdout.write("Invalid com port")
            self._sub_cmd = ''

        elif "get id" == cmd.lower():
            self._get_id()
        elif "set com port" == cmd.lower():
            ports = get_serial_ports()

            sys.stdout.write("\r\nCurrent port: " +  str(self._serial_port))
            sys.stdout.write("\r\nChoose serial port:\r\n")

            for key,value in ports.items():
                sys.stdout.write(str(key) + ". " + value + "\r\n")
            self._sub_cmd = "com"

        elif "open com port" == cmd.lower():
            self._connect()
        elif "close com port" == cmd.lower():
            self._close_connection()

        elif "reset"== cmd.lower():
            self._reset_instrument()
        elif "set channel" == cmd[:len("set channel")].lower():
            cmd_list = cmd.lower().split(" ")
            if len(cmd_list) == 3:
                if cmd_list[2].isnumeric:
                    ch = int(cmd_list[2])
                    if 1 <= ch <= 3:
                        self.set_channel(ch)
        elif "set output" == cmd[:len("set output")].lower():
            cmd_list = cmd.lower().split(" ")
            if len(cmd_list) == 5:
                if cmd_list[2].isnumeric and cmd_list[3].isnumeric and cmd_list[4].isnumeric:
                    ch = int(cmd_list[2])
                    volt = float(cmd_list[3])
                    curr = float(cmd_list[4])

                    print(ch)
                    print(volt)
                    print(curr)

                    if 1 <= ch <= 3:
                        self.set_output_value(ch,volt,curr)
        elif "output" == cmd[:len("output")].lower():
            cmd_list = cmd.lower().split(" ")

            if len(cmd_list) == 3:
                if cmd_list[1].isnumeric():
                    ch = int(cmd_list[1])
                    if not (1 <= ch <= 3):
                        self.log.warning("Incorrect channel number")
                        return 0
                    if cmd_list[2] == "off":
                        self.output_disable(ch)
                    elif cmd_list[2] == "on":
                        self.output_enable(ch)
                elif cmd_list[1] == "all":
                    if cmd_list[2] == "off":
                        for i in range(1,4):
                            self.output_disable(i)
                    elif cmd_list[2] == "on":
                        for i in range(1,4):
                            self.output_enable(i)
        elif "master output" == cmd[:len("master output")].lower():
            cmd_list = cmd.lower().split(" ")
            if len(cmd_list) == 3:
                if cmd_list[2] == "off":
                    self.master_disable()
                if cmd_list[2] == "on":
                    self.master_enable()
                    

        elif "off"== cmd.lower():
             self.master_disable()
             self.output_disable(1)
             self.output_disable(2)
             self.output_disable(3)

    def set_channel(self,ch):
        if not (self._port_is_open()):
            if not self._connect():
                return 0
        self._ser.write("INST OUT{:d}\n".format(ch).encode())

    def set_output_value(self,ch,volt,curr):
        if not (self._port_is_open()):
            if not self._connect():
                return 0
        self._ser.write("INST OUT{0:d}\nVOLT {1:.3f}\nCURR {2:.3f}\n".format(ch,volt,curr).encode())
        self._ser.write(b"FUSE:DEL 0.1\n")
        self._ser.write(b"FUSE ON\n")
        self._ser.write(b"SOUR:VOLT:PROT:LEV 5.4\n")
        self._ser.write(b"SOUR:VOLT:PROT ON\n")


# Port handling

    def _set_serial_port(self,port):
        self._serial_port = port
        self.log.debug("Serial port set to: " + port)



    def _connect(self):
        if (self._port_is_open()):
            self.log.debug("Port is already open!")
            return 1

        if self._serial_port == None:
            self.log.warning("Serial port not set")
            return 0

        try:
            self._ser = serial.Serial(
                port = self._serial_port,
                baudrate = self._baud_rate,
                parity = "N",
                stopbits = 1,
                bytesize = 8,
                timeout = 1,
                )
            self.log.debug("Serial port: " + self._serial_port + " succesfully opened!")
            return 1
        except:
            self.log.error("Failed to open serial port " + self._serial_port)
            return 0


    def _close_connection(self):
        if (self._port_is_open()):
            res = self._ser.close()
            self.log.debug("Serial port: " + self._serial_port + " succesfully closed!")
        else:
            self.log.warning("Failed to close serial port " + str(self._serial_port))


    def _port_is_open(self):
        if (self._ser):
            if self._ser.isOpen():
                return True
            else:
                return False
        else:
            return False

    def _reset_instrument(self):
        if self._connect():
            self.log.info("Resetting instrument!")
            self._ser.write("*RST\n".encode())
            #self._ser.write("SYST:TIME:RES\n")
            time.sleep(1)

    def _get_id(self):


        if self._connect():
            self._ser.write("*IDN?\n".encode())
            time.sleep(0.5)
            self.instrument_id = str(self._ser.readline().decode().rstrip("\r"))
            self.log.debug("Requesting instrument ID")
            sys.stdout.write(self.instrument_id)
            sys.stdout.flush()

        else:
            self.log.error("Cannot open serial port: " + str(self._serial_port) + "!")

    def output_enable(self,ch):
        if(self._port_is_open()):
            self._ser.write("INST OUT{:d}\nOUTP:CHAN ON\n".format(ch).encode())
            self.log.info(f"Enabled output ch {ch} on HMC 8043")
        else:
            self.log.warning("Serial port is not open!")
    def output_disable(self,ch):
        if(self._port_is_open()):
            self._ser.write("INST OUT{:d}\nOUTP:CHAN OFF\n".format(ch).encode())
            self.log.info(f"Disabled output ch {ch} on HMC8043")
        else:
            self.log.warning("Serial port is not open!")

    def master_disable(self):
        if(self._port_is_open()):
            self._ser.write(b"OUTP:MAST OFF\n")
            self.log.info("Disabled master output on HMC 8043")
        else:
            self.log.warning("Serial port is not open!")


    def master_enable(self):
        if(self._port_is_open()):
            self._ser.write(b"OUTP:MAST ON\n")
            self.log.info("Enabled master output on HMC 8043")
        else:
            self.log.warning("Serial port is not open!")
   
    def measure(self, ch):

        if(self._port_is_open()):
          
            self._ser.write("INST OUT{0:d}\nMEAS:CURR?\n".format(ch).encode())
            time.sleep(0.01)
            curr = float(self._ser.readline().decode().rstrip("\r"))
            self._ser.write("INST OUT{0:d}\nMEAS:VOLT?\n".format(ch).encode())
            time.sleep(0.01)
            voltage = float(str(self._ser.readline().decode().rstrip("\r")))

            #self.log.info("Measured: " + str(curr))
            return curr, voltage

        else:
            print("--------2")
            self.log.warning("Serial port is not open!")
            return -1,-1

def get_serial_ports():
    ports = list_ports.comports(include_links=False)
    serial_port_list = {}
    i = 0


    for p in ports:
        i += 1
        serial_port_list[i] = p.device
        #sys.stdout.write(str(i) + " " + p.device)

    return serial_port_list


if __name__ == "__main__":
    # Check arguments

    serial_port = ''
    ports = get_serial_ports()

    parser = argparse.ArgumentParser(description="HMC8043 Control")
    parser.add_argument("--com-port",choices=list(ports.values()),help="Name of com port")
    parser.add_argument("-c",choices=("on","off"),help="Config")


    #parser.add_argument("--config-file",help="Measurement config file (json)")

    args=parser.parse_args()
    if args.com_port == None:
        serial_port = "COM7"
        serial_port = "/dev/ttyACM0"
    else:
        serial_port = args.com_port
    #config_file = args.config_file
    LOG_NAME = "HMC8043"
    cmd_queue = queue.Queue(5)
    config_queue = queue.Queue(20)

    log = logging.getLogger(LOG_NAME)
    log.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)s - %(funcName)s - %(message)s - %(asctime)s","%Y-%m-%d %H:%M:%S")


    log_file_handler = logging.FileHandler(LOG_NAME + ".log")
    log_file_handler.setLevel(logging.DEBUG)
    log_file_handler.setFormatter(formatter)
    log.addHandler(log_file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    log.addHandler(console_handler)

    log.debug("Starting HMC 8043 Control Program")

    # if used stand alone
    menu_data["options"].append({'title': "help", 'desc': "Print this menu"})
    menu_data["options"].append({'title': "quit", 'desc': "Quit program"})


    hmc_thread = HMC8043(name = "HMC",log_name = LOG_NAME)
    hmc_thread.start()
    time.sleep(0.5)

    if serial_port != None:
        hmc_thread._set_serial_port(serial_port)
        hmc_thread._connect()
    config = {}

    hmc_thread.print_menu()
    # Start interactive keyboard thread
    run_app = True
    keyboard_thread = threading.Thread(name="keyboard",target=keyboard,args=[cmd_queue,lambda: run_app])
    keyboard_thread.start()


    ds_start = datetime.timestamp(datetime.now())
    if args.c != None:
        if args.c.lower() == "on":
            hmc_thread._reset_instrument()
            #hmc_thread.set_output_value(1,1,1.6)
            #hmc_thread.set_output_value(2,2,1.6)
            hmc_thread.set_output_value(3,3,0.5)
            #hmc_thread.output_enable(1)
            #hmc_thread.output_enable(2)
            hmc_thread.output_enable(3)
            hmc_thread.master_enable()

        if args.c.lower() == "off":

            hmc_thread.master_disable()
            hmc_thread.output_disable(1)
            hmc_thread.output_disable(2)
            hmc_thread.output_disable(3)
           
           

    if not(os.path.isfile(hmc_thread.datalogfile)):
        with open(hmc_thread.datalogfile,"a") as f:
            f.write("time,volt_ch1, curr_ch1,volt_ch2, curr_ch2,volt_ch3, curr_ch4\n",)

    while run_app:
        while not cmd_queue.empty():

            cmd = cmd_queue.get()
            if "help" == cmd.lower():
                hmc_thread.print_menu()
            elif "quit" == cmd.lower():
                run_app = False
            else:
                hmc_thread.decode_cmd(cmd)
        time.sleep(0.5)
        curr1, voltage1 = hmc_thread.measure(1)
        curr2, voltage2 = hmc_thread.measure(2)
        curr3, voltage3 = hmc_thread.measure(3)
        
     
        dt = datetime.now()
        ts = datetime.timestamp(dt) - ds_start
        with open(hmc_thread.datalogfile,"a") as f:
            f.write("{0:},{1:f},{2:f},{3:f},{4:f},{5:f},{6:f}\n".format(dt, curr1, voltage1, curr2, voltage2, curr3, voltage3))

    hmc_thread.master_disable()
    hmc_thread.output_disable(1)
    hmc_thread.output_disable(2)
    hmc_thread.output_disable(3)
    hmc_thread.stop()
    hmc_thread.join()
    keyboard_thread.join()
    sys.exit(0)
