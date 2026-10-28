import re
from queue import Queue, Empty

class GcodeHandler():
    def __init__(self):
        self.queue = Queue()
        self.callback = None
        self.gcode = None
        self.ack_list = []
        self.axis_pos_list = []
        self.sd_card_files_list = []
        self.ok_flag = False
        self.home_flag = False
        self.temp_report_flag = False
        self.temp_dict = {}
        self.sd_write_flag = False
        self.init_print_flag = False
        self.gcode_ext_tuple = (".gco", ".g", ".gcode")
        self.sd_card_files_list = []
        self.sd_file_open_flag = False
        self.m400_flag = False
        self.sd_abort_flag = False
        self.sd_abort_response_flag = False

        self.gcode_dict = {"linear" : "G1",
                           "lmove1" : "G1",
                           "dwell" : "G4", 
                           "home" : "G28",
                           "absolute" : "G90",
                           "relative" : "G91",
                           "set-pos" : "G92",
                           "ex-pos" : "G92 E0",
                           "list-SD" : "M20",
                           "init-SD" : "M21",
                           "select-SD" : "M23",
                           "start-SD" : "M24",
                           "resume-SD" : "M24",
                           "pause-SD" : "M25",
                           "delete-SD" : "M30",
                           "ext-rel" : "M82",
                           "set-stepsmm" : "M92",
                           "get-pos" : "M114",
                           "laser-com" : "M118 A1 P3",
                           "extruder" : "M302 S0",
                           "finish-move" : "M400",
                           "abort-SD" : "M524"                                                                                 
                           }

    def attachCallback(self, callback_obj):
        if callback_obj:
            self.callback = callback_obj

    def fireCallback(self, code, **kwargs):
        if self.callback:
            self.callback.fire(code, **kwargs)

    def encode(self, cmd):
        self.queue.put(cmd)
        self.parse(cmd)

    def isMotion(self, gcode):
        code = gcode.split(';')[0]
        retval = False

        if code is not None and code != " ":
            code = re.sub(r'G0([0-9])', r'G\1', code)  # normalize G01 → G1
            parts = re.findall(r"([A-Z])([-+]?[0-9]*\.?[0-9]+)", code)

            if parts:
                cmd = parts[0][0] + parts[0][1]

                if cmd:
                    if cmd in ["G0", "G1", "G2", "G3"]:
                        retval = True
                
        return retval   
        
    def parse(self, cmd):
        pass

    def readQueue(self):
        try:
            self.gcode = self.queue.get_nowait()
            print(f"Queue : {self.gcode}")
        except (Empty, Exception):
            self.gcode = None

    def decode(self, response):
        rx_data = response.strip()
        self.append_response_flag = True
        self.temp_report_flag = False

        if "ok" in rx_data:
            self.append_response_flag = False
            self.readQueue()
            self.process(self.gcode, self.ack_list)
            self.ack_list = []
            self.fireCallback("ok")
        
        if "echo:busy" in response:
            self.append_response_flag = False
            if self.sd_abort_flag:
                self.sd_abort_response_flag = True

        if 'T:' in response or 'B:' in response:
            self.decodeTemp(response)

        if 'Done printing file' in response:
            self.append_response_flag = False
            code = "SDdone"            
            self.fireCallback(code)

        if "X:0.00 Y:0.00 Z:5.00" in response and self.sd_abort_response_flag:
            self.append_response_flag = False
            self.sd_abort_response_flag = False
            self.sd_abort_flag = False
            code = "SDabt"
            self.fireCallback(code)
            
        if "echo:V90" in response:
            self.append_response_flag = False
            self.ack_list = []
            
        if all(pattern in response for pattern in ["X:", "Y:", "Z:"]):
            self.decodeAxisPos(response)

        if self.append_response_flag:
            self.ack_list.append(rx_data)

    def process(self, gcode, response_list):
        print(f"Gcode : {gcode}")
        print(f"ACK : {response_list}")

        if not gcode:
            return

        try:
            if "G28" in gcode:
                self.goHome()

            if "G92" in gcode:
                self.getAxisPos()

            if gcode == "M114":
                self.getAxisPos()

            if gcode == "M20":
                self.listSDCard(response_list)

            if "M23" in gcode:
                self.initSDPrint(response_list)

            if "M28" in gcode:
                self.sd_write_flag = True

            if gcode == "M29": 
                self.sd_write_flag = False

            if "M524" in gcode:
                self.sd_abort_flag = True

        except Exception as e:
            print(f"exception : {e}")

        else:
            code = gcode.split(" ")[0]
            print(f"code = {code}")
            self.fireCallback(code)

    def checksum(self, gcode):
        cs = ord(gcode[0])
        for ch in gcode[1:]:
            cs = cs ^ ord(ch)

        return cs
    
    def goHome(self):
        self.home_flag = True
        self.getAxisPos()

    def decodeAxisPos(self, cmd):
        part = cmd.split('Count')[0]
        self.pos_list = [pos for pos in part.split() if ':' in pos]
        print(f"position : {self.pos_list}")
        
    def getAxisPos(self):
        return self.pos_list

    def listSDCard(self, cmd_list):
        self.sd_card_files_list = [data.split(" ")[0] for data in cmd_list if data.split(" ")[0].lower().endswith(self.gcode_ext_tuple)]
        print(f"SD card : {self.sd_card_files_list}")

    def initSDPrint(self, response_list):
        if "File opened" in response_list[1]:
            self.sd_file_open_flag = True
        
        elif "open failed" in response_list[1]:
            self.sd_file_open_flag = False

    def decodeTemp(self, response):
        matches = re.findall(r'(?:^|\s)(T\d*|B)\s*:\s*(-?\d+(?:\.\d+)?)(?:\s*/\s*(-?\d+(?:\.\d+)?))?', response)
        if matches:
            self.append_response_flag = False
            self.temp_report_flag = True
            temps = {}
            for key, cur_str, target_str in matches:
                try:
                    cur_val = float(cur_str)
                    target_val = float(target_str) if target_str else 0.0
                    temps[key] = (cur_val, target_val)
                except ValueError:
                    continue
            if "T0" in temps and "T" not in temps:
                temps["T"] = temps["T0"]
            if temps:
                self.temp_dict = temps
                self.fireCallback("FullTempUpdate", temps=temps)
                return True
        return False

    def getTemp(self):
        return self.temp_dict
