from qtpy.QtGui import QTextDocument
doc = QTextDocument()
doc.setHtml('C<sub><font size="+1">458</font></sub>')
print(doc.toHtml())