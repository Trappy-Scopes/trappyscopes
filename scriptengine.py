from colorama import Fore, Style

def LoadScript(scriptfile):
		print(f"{Fore.YELLOW}{'='*10} Executing: {Fore.WHITE}{scriptfile} {Fore.YELLOW} {'='*10}{Style.RESET_ALL}")
		with open(scriptfile) as f:
			exec(f.read(), globals())