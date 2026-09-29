# فحص البيئة: يطبع إصدارات Python وPySide6 وQt وNumPy ورقم بناء Windows.
import sys, platform
import numpy
import PySide6
from PySide6 import QtCore
print("Python  :", sys.version.split()[0], f"({platform.architecture()[0]})")
print("PySide6 :", PySide6.__version__)
print("Qt      :", QtCore.qVersion())
print("NumPy   :", numpy.__version__)
print("Windows : build", sys.getwindowsversion().build)