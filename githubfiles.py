import requests
from rich import print
from rich.markdown import Markdown

def get_file(repo, path, branch='main'):
    url = f"https://raw.githubusercontent.com/Trappy-Scopes/{repo}/{branch}/{path}"
    print(url)
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        print(f"Failed to retrieve file: {response.status_code}")
        return None

def get_md(repo, path, branch='main'):
	return Markdown(get_file(repo, path, branch=branch), inline_code_theme='monokai')