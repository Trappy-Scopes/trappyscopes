## With the help of deepseek

import os
import shutil
from pathlib import Path
import mkdocs_gen_files

ROOT = Path(__file__).parent
print(ROOT)
PKG_DIR = ROOT / "scope-cli"

def copy_readmes():
    """Copy module READMEs to documentation structure"""
    for module_dir in PKG_DIR.iterdir():
        if module_dir.is_dir() and (module_dir / "README.md").exists():
            # Create module docs directory
            doc_dir = f"docs/{module_dir.name}"
            os.makedirs(ROOT / doc_dir, exist_ok=True)
            
            # Copy README as index.md
            shutil.copy(
                module_dir / "README.md",
                ROOT / doc_dir / "index.md"
            )
            
            # Create API reference stub
            with mkdocs_gen_files.open(f"{module_dir.name}/api.md", "w") as f:
                f.write(f"# {module_dir.name.capitalize()} API Reference\n\n")
                f.write(f"::: my_package.{module_dir.name}\n")
                f.write("    options:\n")
                f.write("      show_root_heading: true\n")
                f.write("      show_source: true\n")

def create_main_index():
    """Generate main index from root README"""
    with open(ROOT / "README.md", "r") as src:
        with mkdocs_gen_files.open("index.md", "w") as dest:
            dest.write(src.read())

if __name__ == "__main__":
    copy_readmes()
    create_main_index()