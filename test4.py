import sys
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)
import pyqtgraph as pg


class InputForm(QWidget):
    def __init__(self):
        super().__init__()

        # Set up the layout
        self.setWindowTitle("Input Form with PyQtGraph")
        layout = QVBoxLayout()

        # Create input fields
        self.name_label = QLabel("Name:")
        self.name_input = QLineEdit()
        self.age_label = QLabel("Age:")
        self.age_input = QLineEdit()

        # Add a PyQtGraph widget
        self.graph_label = QLabel("PyQtGraph Example:")
        self.graph_widget = pg.PlotWidget()
        self.graph_widget.plot([1, 2, 3, 4], [10, 20, 10, 30])

        # Submit button
        self.submit_button = QPushButton("Submit")
        self.submit_button.clicked.connect(self.on_submit)

        # Add widgets to layout
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.age_label)
        layout.addWidget(self.age_input)
        layout.addWidget(self.graph_label)
        layout.addWidget(self.graph_widget)
        layout.addWidget(self.submit_button)

        self.setLayout(layout)

    def on_submit(self):
        # Handle form submission
        name = self.name_input.text()
        age = self.age_input.text()

        try:
            age = int(age)
            QMessageBox.information(
                self, "Form Submitted", f"Name: {name}\nAge: {age}"
            )
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Age must be a number!")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    form = InputForm()
    form.show()

    sys.exit(app.exec_())
