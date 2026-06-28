from qtpy.QtGui import QTextDocument
doc = QTextDocument()
doc.setHtml('C<sub><span style="font-size: 14pt;">458</span></sub>')
print(doc.toHtml())