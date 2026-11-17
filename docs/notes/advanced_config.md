# Advances Configuration

A complete configuration guide to the TrappyVerse.


A machine is imagined.
```yaml
# ~/trappyverse/trappyconfig.yaml
name: coin_toss_machine
description: Machine that tosses coins and records the outcome.
```


Now, let's setup a python environment for it:


```yaml
config:
  venv:
      active: true
      name: casino  # The code runs on the "casino" virtual environemnt
  branch: main      # The "main" branch of trappyscopes is used.
  startup_recipie: freestyle # Interactive mode that sets-up the environment for user engagement.
  # Load the cointoss experiment script by dafault.
  startup_scripts: ["/scripts/toyexps/cointoss/cointoss.py"]
```


If you maintain your own fork of `trappyscopes`, then you can setup automatic sync operations. You can also use this feature to automatically sync other required repositories:

```yaml
config:
 git_sync:                  
     active: true                # Config block is active. The function is turned on.
     command: git pull           # Exact command to use for git syncronisation
     repos:
     	- https://github.com/<YOURLAB>/trappyscopes.git  # Your fork
     	- https://github.com/<YOURLAB>/protocols.git     # Your protocols repo
     	- https://github.com/<YOURLAB>/lab_scripts.git   # Your lab scripts repo
```


Our machine will record coin-tossing. The machine will consist of one devie -- "coin":
```yaml
ScopeAssembly:
  coin:
    description: "5 cents Euro coin"
    kind: hive.physical.PhysicalObject
    args: ["coin"]
    kwargs:
      persistent: False
```

We will first test the machine by simulating cointosses. The script contains a `toss()` method. Let's bind it to keyboard shortcuts to make it easier to call:

```yaml
config:
	keyboard_shortcuts:
    active: true                 # Config block is active. The function is turned on.
    scope_assembly: true         # Esc+S+C gives the coin object.
    experiment: false
    bindings:
     - keys: "esc t"             # Esc+t tosses the coin.
       code: "toss()"
       submit: true
       description: Toss a coin.
```
