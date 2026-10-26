from dataclasses import dataclass


class DictAsClass():
    def __init__(self, dictionary):
        self._data = dictionary
    
    def __getattr__(self, key):
        if key in self._data:
            return self._data[key]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}'")
    
    def get(self, key, default=None):
        return self._data.get(key, default)


@dataclass
class Axis:
    name: str
    pos: float
    min: float
    max: float
    feed: float
    stepsmm: float
    
    
class AxisHandler():
    def __init__(self):
        self.axis_dict = {}
        
    def addAxis(self, name, pos=None, min=None, max=None, feed=None, stepsmm=None):
        axis = Axis(name, pos, min, max, feed, stepsmm)
        self.axis_dict[name] = axis
        
    def getAxis(self, name):
        if name in self.axis_dict:
            return self.axis_dict[name]
        
    def setValue(self, name, key, value):
        axis = self.getAxis(name)
        
        if axis is not None and key is not None and value is not None:
            setattr(axis, key, value)

    def pos(self, name, pos):
        self.setValue(name, "pos", pos)
                    
    def min(self, name, min):
        self.setValue(name, "min", min)
        
    def max(self, name, max):
        self.setValue(name, "max", max)
        
    def feed(self, name, feed):
        self.setValue(name, "feed", feed)
        
    def stepsmm(self, name, stepsmm):
        self.setValue(name, "stepsmm", stepsmm)


@dataclass
class Laser:
    name: str
    focus: float
    xpos: float
    ypos: float
    cmd: dict


class LaserHandler():
    def __init__(self):
        self.laser_dict = {}

    def getHandlerData(self):
        return self.laser_dict
        
    def addLaser(self, name, focus, xpos, ypos, cmd):
        laser = Laser(name, focus, xpos, ypos, cmd)
        self.laser_dict[name] = laser

    def getKeys(self):
        return self.laser_dict.keys()
        
    def getLaser(self, name):
        if name in self.laser_dict:
            return self.laser_dict[name]
        
    def setValue(self, name, key, value):
        laser = self.getLaser(name)
        
        if laser and key and value:
            setattr(laser, key, value)
        
    def focus(self, name, focus):
        self.setValue(name, "focus", focus)
            
    def xpos(self, name, xpos):
        self.setValue(name, "xpos", xpos)
    
    def ypos(self, name, ypos):
        self.setValue(name, "ypos", ypos)
    
    def cmd(self, name, cmd):
        self.setValue(name, "cmd", cmd)
        
                   
class WidgetHandler():
    def __init__(self, **kwargs):
        super().__init__()
        
        self._widget = kwargs.get("widget")
        self.method_get = kwargs.get("get")
        self.method_set = kwargs.get("set")
        self.method_add = kwargs.get("add")
        self.method_clear = kwargs.get("clear")
        self.method_enable = kwargs.get("enable")
        
    def callMethod(self, call, widget, method_name, value=None):
        method = getattr(widget, method_name)
        
        if call == "get":
            return method()
        
        if call == "set":
            if value is not None:
                method(value)
                
            else:
                method()
        
    def get(self):
        if self._widget and self.method_get:
            return self.callMethod("get", self._widget, self.method_get)
        
    def set(self, arg):
        if self._widget and self.method_set:
            self.callMethod("set", self._widget, self.method_set, value=arg)
            
    def add(self, arg):
        if self._widget and self.method_add:
            self.callMethod("set", self._widget, self.method_add, value=arg)
            
    def clear(self):
        if self._widget and self.method_clear:
            self.callMethod("set", self._widget, self.method_clear)
            
    def enable(self, arg):
        if self._widget and self.method_enable:
            self.callMethod("set", self._widget, self.method_enable, value=arg)
            
            
class WidgetManger():
    def __init__(self):
        self.widget_methods = {"QLineEdit" : {"get" : lambda w : w.text(),
                                              "set" : lambda w, arg : w.setText(arg),
                                              "enable" : lambda w, arg : w.setEnabled(arg),
                                              "clear" : lambda w : w.clear(),
                                              "show" : lambda w : w.setVisible(True),
                                              "hide" : lambda w : w.setVisible(False)
                                              },
                               
                               "QTextEdit" : {"get" : lambda w : w.text(),
                                              "set" : lambda w, arg : w.setText(arg),
                                              "enable" : lambda w, arg : w.setEnabled(arg),
                                              "clear" : lambda w : w.clear(),
                                              "add" : lambda w, arg : w.append(str(arg)),
                                              "show" : lambda w : w.setVisible(True),
                                              "hide" : lambda w : w.setVisible(False)
                                              },
                               
                               "QLabel" : {"get" : lambda w : w.text(),
                                           "set" : lambda w, arg : w.setText(arg),
                                           "enable" : lambda w, arg : w.setEnabled(arg),
                                           "clear" : lambda w : w.clear(),
                                           "show" : lambda w : w.setVisible(True),
                                           "hide" : lambda w : w.setVisible(False)
                                           },
                               
                               "QComboBox" : {"get" : lambda w : w.currentText(),
                                              "set" : lambda w, arg : w.setCurrentText(arg),
                                              "enable" : lambda w, arg : w.setEnabled(arg),
                                              "clear" : lambda w : w.clear(),
                                              "add" : lambda w, args : w.addItems(args),
                                              "show" : lambda w : w.setVisible(True),
                                              "hide" : lambda w : w.setVisible(False)
                                              },
                               
                               "QPushButton" : {"get" : lambda w : w.text(),
                                                "set" : lambda w, arg : w.setText(arg),
                                                "enable" : lambda w, arg : w.setEnabled(arg),
                                                "clear" : lambda w : w.setText(""),
                                                "show" : lambda w : w.setVisible(True),
                                                "hide" : lambda w : w.setVisible(False)
                                                },
                               
                               "QLCDNumber" : {"set" : lambda w, arg: w.display(arg),
                                               "get" : lambda w: w.value(),
                                               "show" : lambda w : w.setVisible(True),
                                               "hide" : lambda w : w.setVisible(False)
                                               },
                               
                               "QProgressBar" : {"get" : lambda w : w.value(),
                                                 "set" : lambda w, arg : w.setValue(arg),
                                                 "enable" : lambda w, arg : w.setEnabled(arg),
                                                 "clear" : lambda w : w.setValue(0),
                                                 "min" : lambda w, min : w.setMinimum(min),
                                                 "max" : lambda w, max : w.setMaximum(max),
                                                 "show" : lambda w : w.setVisible(True),
                                                 "hide" : lambda w : w.setVisible(False)
                                                 }
                               }
        
    def operate(self, widget, operation, value=None):
        widget_type = type(widget).__name__
        
        if widget_type not in self.widget_methods:
            return False
        
        method_dict = self.widget_methods[widget_type]
        
        if operation not in method_dict:
            return False
        
        method = method_dict[operation]
        
        if method is None:
            return False
        
        if operation == "get":
            return method(widget)
        
        if operation in ["set", "enable", "add", "min", "max", "clear", "show", "hide"]:
            if value is not None:
                method(widget, value)
            
            else:
                method(widget)