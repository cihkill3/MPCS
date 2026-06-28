from qtpy.QtWidgets import QApplication, QCheckBox
import sys
app = QApplication(sys.argv)
cb = QCheckBox('C<sub><font size="+1">458</font></sub>')
cb.show()
print(cb.text())
