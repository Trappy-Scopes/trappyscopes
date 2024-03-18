import sys
from prompt_toolkit import prompt
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style
from pygments.lexers import PythonLexer
from pygments.token import Token

class CustomCompleter(Completer):
    def get_completions(self, document, complete_event):
        try:
            import readline
        except ImportError:
            return

        line = document.current_line.lstrip()
        begidx, endidx = readline.get_begidx(), readline.get_endidx()

        before_cursor = line[:endidx]
        word_before_cursor = before_cursor.split()[-1]

        completions = []
        for obj in dir(__main__):
            if obj.startswith(word_before_cursor):
                completions.append(obj)

        for completion in completions:
            yield Completion(completion, start_position=-len(word_before_cursor))

def get_prompt_tokens(cli):
    return [
        (Token.Prompt, '>>> ' if cli.in_main_input else '... '),
    ]


while True:
    try:
        user_input = prompt(
            lexer=PygmentsLexer(PythonLexer),
            style={Token.Prompt: '#ansiblue'},
            auto_suggest=get_prompt_tokens,
            completer=CustomCompleter(),
        )
        exec(user_input)
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(e)
