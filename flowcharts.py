from diagrams.programming.flowchart import Action
from diagrams import Diagram


def generate_seq(flow, name="Control flow"):
    with Diagram(name, show=False):
        #flow = [Action(event) for event in flow]
        flow = [f"Action('{event}')" for event in flow]
        exec(" >> ".join(flow))