import csv
import os
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Grid
from textual.widgets import Button, Input, Label
from textual.widgets import Header, Footer

try:
    from .gui import TrappyApp
except:
    from gui import TrappyApp

class FormApp(TrappyApp):
    

    #def __init__(self, fields):
    fields = {}
    inputs = {}

    def compose(self) -> ComposeResult:
        container = Container()
        
        for field in self.fields:
            label = Label(f"{field}:")
            input_field = Input(id=field.lower())
            self.inputs[field] = input_field
            yield Horizontal(label, input_field)
        
        yield Header()
        yield Horizontal(Button("Submit", id="submit"), Button("Quit", id="quit"))
        yield Footer()


    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            row = []
            for field in self.fields:
                input_value = self.inputs[field].value
                row.append(input_value)

            # Clear the inputs
            for input_field in self.inputs.values():
                input_field.value = ""

        elif event.button.id == "quit":
            self.exit(self.inputs)


async def create(fields={}):
    f = FormApp().run()
    #f.fields = fields
    #ret = f.run()
    return ret

if __name__ == "__main__":

    f = FormApp()
    f.fields = {"name":str, "age":int}
    x = f.run(inline=True)
    print(x)
