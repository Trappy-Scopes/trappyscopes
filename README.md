# trappyscopes-cli 

## (Trappy-Scopes command line interface)

trappyscopes is a python framework for building and controlling laboratory instruments. It facillitates the creation of highly heterogenous instrument assemblies by integration any existing python package. The aim of  `trappyscopes` is to enable fast deployment of paralel measurement systems that are software defined.

The base model of this library imagines instruments as an arbitrary tree of python enabled computers and "pythonic" microcontrollers (micropython or circuitpython). With this base model, the control layer enables plug and play interfacing with minimal configuration. The key idea is to have the following workflow while building instruments.

1. Connect all components with their respective interfaces (serial, ethernet, over wifi etc)
2. Install this library and all required 3rd party packages for the components.
3. Define the structure of the instrument in a configuraion file.
4. You are done! Launch the cli to acquire data.



### Some other salient features of the framework

1. Pythonic interfacing
2. Software defined infrastructure is at the core of lab management.
3. Made to support parallelization and open-source instrumentation.
4. Seemlessly interfaces with any existing python pacakge.



### A quick example

Given the following configuration of instruments, where M1 and M2 are separate machines connected by a network:

```mermaid
graph LR
  subgraph M1
    M1_("Machine 1 (M1)")
    M1_ -.- S("Sensor (MS1)")
  end
  
  subgraph M2
    M2_("Machine 2 (M2)")
    M2_ -.- S_("Sensor (MS2)")
  end
  
  M1 --mounts--> M2
```


```python
# These commands work on M1
scope.MS1.read()
scope.M2.MS2.read()
```

Given the configuration:

```yaml
ScopeAssembly:
  ...
  MS1:
    description: Sensor on Machine 1.
    kind: sensor1.library.Sensor1Constructor
    args: []
    kwargs: {}
  M2:
    description: Machine 2 over netwwork.
    kind: hive.processorgroups.remote.RemoteGroup
    args: []
    kwargs:
      - automount: True
```



## Installation

1. Install through `pip`

  ```bash
  pip install trappyscopes
  ```

2. You can install directly from the source and install the environment using the inbuilt command to build the environment.

  ```bash
  git clone -r <repo_link>
  cd <trappyscopes>
  python main.py --install
  ```

3. Basic information about application startup
  ```bash
  python main.py -h
  ```

4. `python main.py` can be replaced by `./ts`, which is a bash script that does the same (plus some extra things). You might have to run `chmod +x ts` or `sudo +x ts` to provide executable priviledges to the script.


## Configuring a scope

1. `trappyscopes` cli is configured through a `YAML` configuration file. Let´s start by generating a configurartion file.

  ```bash
  python main.py --new_config
  ```

  This generate the following files in the home directory:
  ```
   (~)
    |-trappyverse
    . |- trappyconfig.yaml
      .
  ```
2. `trappyverse/trappyconfig.yaml` is the default configuration file name and should be unchanged. We can have more than one configuration file on a system. To start the software with a custom configuration file:

  ```bash
  python main.py --config ~/parallelverse/customconfig.yaml
  ```
3. Now let's look at the configuration file!
  1. The first two lines are these:

  ```yaml
    name: <hostname>          # Name of the scope, which defaults to hostname. The is defined as the global variable `scopeid` with the defaul startup recipie. 
    kind: mystery-device      # A signle word descriptor for the device.
    description: The functionally has not been described yet # A short description of the functionality of the device.
  ```

  These fields can be edited as such and are of little consequence in terms of programming. The `name` must be chosen with care, and it's recommened that it is also the hostname of the machine. This makes remote access easy and preventss conflicts. 

  `name: MDev` is a special name, which defines any device as a "Development Scope" and has some special priveledges. For more information, check the [`MDev`](notes/mdev.md) entry in the notes.

  2. Now let's set check some configuration options and learn what they do:

  ```yaml
  config:
    trappydir: ~/trappyverse   # Directory where the configuration of the scope is stored.
    ui_mode: interactive       # User interaction mode
    venv:                      # Whether to use a virtual environment for 
        active: true                # Config block is active. The function is turned on.
        command: source ~/opt/miniconda3/bin/activate 
        name: trappy                # Name of the virtual environment that will be called after the command
      git_sync:                  # Automatically git-sync certain repositories
        active: true                # Config block is active. The function is turned on.
        command: git pull           # Exact command to use for git syncronisation
        repos:                      # List of local repositories, where the command will be called
          - ~/lab_protocols/
          - ~/lab_scripts/                     
      set_wallpaper: false       # This option will set a "information" panel as the wallpaper. This helps to id the device, incase of multiplexing.
      log_level: 20              # Log level of the root logger. Use 10 for debug. 20 is info and higher.
      config_server:             # Configuration files are synchronised with this server, when changed.         
        active: true
        server: <ip>/<address>
        share: <name-of-server-share>
        destination: "{date}"   # Sub folder inside the share. This will create a folder with the "current date" opon operation.
        username: <username>
        password: <password>
      config_redact_fields:     # Fields that will be redacted, if the config file is copied
        - username
        - password
      startup_recipie: core.startup  # Startup procedure that defines how the CLI environment is created. `core.startup.__init__.py` defines the default one.
      startup_scripts:          # Scripts to run by default when the CLI is started.   
      - ./scripts/script1.py
      - ./scripts/script2.py
    
  ```

  Note some key features here: 
    1. Any mapping can be turned off by defining a field `active: false` inside it. If this argument is skipped, then it's assumed to be `true`.
    2. Custom addresses (like the `destination` in `config_server`) can be defined with an "effifible" string (inspired by the f-strings in python):
    
~~~yaml
```
  config_server:
  destination: "{date}_{scopeid}_{user}" # -> 2025_05_01_microscope1_User1
```
~~~


  The following terms can be used: `scopeid`, `user`, `date`, and `time`.

    3. Now let's look at the default `ScopeAssembly` block below:

  ```yaml
    ScopeAssembly:
      <hostname>: 
        description: "Host processorgroup."
        kind: hive.processorgroups.linux.LinuxMachine
        args: []
        kwargs: {}
  ```

  The device that we see here is the host computing machine that is detected and mounted. It is one of the devices under the `ScopeAssembly`, which is identified as the global variable `scope`. Within the scope assembly, we can define an arbitrary number of devices with the follwing schema:

  ```yaml
    ScopeAssembly:
      device_name:
        active: true
        description: Provide a meaningful description of the device.
        kind: <path.to.object.Constructor>
        args: []   # Arguments that are passed to the object constructor.
        kwargs: {} # Keyword arguments passed to the object constructor.
        # Optional configuration
        metaclass: hive.detector.Detector  # Define the object as a detector and extend its functionality
        read_method: capture  # Method of the origianl object that is interpreted as the "read" method.
          args: []            # These will be wrapped in a `functools.partial` instance.
          kwargs: {}          # These will also be wrapped in a `functools.partial` instance.
        write_method: set # Similar to the "read_method" option.
          args: []            # These will be wrapped in a `functools.partial` instance.
          kwargs: {}          # These will also be wrapped in a `functools.partial` instance.
  ```

  For more information regarding the optional configuration options, refer to: [notes/devices.md](notes/devices.md).

  4. For now, we can leave the previous block as it was and quickly gloss over the `Experiment` configuration block:

  TODO: Git auth for protocols.
    
  ```yaml
    Experiment:
      exp_dir: ~/experiments              # Default directory where experiments are stored
      protocols_dir: ~/lab_protocols      # Directory where protocols are stored, This can also be a git-address.
      calibration_dir: ~/calibration_dir  # Directory where calibrations are stored.
      exp_dir_structure:                  # This is the directory structure, that will be created within every experiment.
        - scripts
        - postprocess
        - converted
        - analysis
      exp_report: false                   # Whether the pdf report functionality is turned on or not.
      eid_generator: core.uid.uid         # This is the funtion that will be called to generate experiment IDs. By default is calls `nanoid.generate('1234567890abcdef', 10)`
      file_server:                        # File server for synchronisation of experiments
        active: true
        server: <ip>/<address>
        share: <name-of-server-share>
        destination: "{date}"
        username: <username>
        password: <password>
  ```

  5. The configuration is defined in `core.permaconfig.config.py` as `TrappyConfig`. It uses the [Confuse](https://confuse.readthedocs.io/en/latest/usage.html#confuse-painless-configuration) library as a base.

 


---
 # Depreciated



2. A little introduction can be summoned by calling `intro()`.

## Start-up and usage

+ Use `./trappyscope`, a typical startup would look like:
  ```bash
  ./trappyscope -su UserName experiment_script.py
  ```

+ Start control layer utility with `python -i main.py` in the interactive mode. 

+ Scripts are an important part of running experimental procedures:
  ```bash
  python main.py <script1> <script2> <script3>
  trappyscope <script1> <script2> <script3>
  python main.py --iterate 3 <script1> ## Run Script1 three times
  ```

+ The scripts are executed in sequence and can be used to load pre-defined experimental protocols.

+ Alternatively, to load a script/execute a script from the interactive session:
  ```bash
  ScriptEngine.now(globals(), "scriptfile.py")
  ```



## Start an experiment

+ All data-collection should be done within the context of an `Experiment`:

  ```python
  exp = Experiment("test")
  ```

  You should get the following output:

  ```bash
  ────────────────────────────── Experiment open ─────────────────────────────────────────
  [17:21:08] INFO     Loading Experiment: test                                                                                                experiment.py:267
  Working directory changed to: /Users/byatharth/experiments/test
  .
  ├── .experiment
  ├── analysis
  ├── converted
  ├── experiment.yaml
  ├── postprocess
  └── sessions.yaml
  
  3 directories, 3 files
  
  user:ghost || ‹‹M1›› Experiment: test 
  >>>
  ```

The experiment features are described in the [expframework](expframework/README.md) submodule.

## Describing one scope

A `scope` is described as a tree of devices. It is a combination of Processors (`ProcessorGroup`), `Sensors` , and `Actuators`. A scope configuration is defined in the `deviceid.yaml` configuration file. An example is given below:

```yaml
name: MDev
uuid: null
type: microscope
frame:
- pico
- topplate
- lit
- diffuser
- lenses.asphere
- sample
- samplestage
- midplate
- zoomlens
- zoomlensholdplate
- camera
- baseplate
optics:
  lenses:
  - 120deg plastic asphere
  - ACL2520U
  - zoomlens
hardware:
  pico:
  - nullpico
  - pico1
  - nullpico
  camera: nullcamera
  illumination: CA_PWM_RGB_LED_5mm
git_sync: false
write_server: ssd1
file_server: smb://files1.igc.gulbenkian.pt/igc/folders/LP/yatharth
auto_fsync: false
auto_pico_fsync: true
```

## Describing N-scopes

Multiple scopes are defined by defining each of the configuration files on each of the scopes. After this is done, the network layer allows the scopes to be connected to the laboratory hive, where all scopes can be accessed on the fly.







## How to do Science on the scopes?

## An `Experiment`

The data and metadata collection for any experiment is handled through the `Experiment` class. It's primary role is to manage storage for every different experiments. Creation of the class, immediately changes the working directory to the experiment one. 

### Unique ID

Each experiment is also assigned a 10-digit hex unique id. Example: `e8423b83d2`. 

### File Structure

Each experiment has the following directory structure:

```
Experiment_name
    |- .experiment              (identifier)
    |- experiment.yaml          (event logs)
    |- data1, data2, data3, ... (data - in the repository)
    |- postprocess              (postprocessed data)
    |- converted                (online conversion - eg. between video formats)
    |- analysis                 (analysis results)
```

### Flow of Control - TODO check with the current version

```mermaid
flowchart
  
  subgraph Setup
    Create-ID-files --> Create-folders --> Copy-Payload
  end
  
  subgraph Loading
    load(load events) --> CWD(Change working directory)
  end
  
  subgraph Deletion
    del -.calls.- close("exp.close()") --> Logs(Write event logs to yaml) --> CWDB(Change working <br>dir to original)
  end
  
  Setup --> Loading --> Deletion
```

### LoadScript utility TODO



### Configuration Files

1. `camconfig.yaml` : Contains the camera configuration file for the default mode.
2. `deviceid.yaml` : Contains the  unique identity constants for the device.
3. `common.py`  : Contains common constants for all devices.



###  TODO: Obsolete Current Sequence


```mermaid
flowchart LR
  print-flugg.header --> load-device_id --> complete-all-imports --> connect-pico --> Free-REPL
```



### Hardware

The hardware is modelled as a device-tree or a hierarchical collection of devices. All nodes that are not end-nodes are turing complete computational devices.

```python
assembly: 
 | rpi: null
 | cam: camera
 | pico: 
 | | lit: light
 | | beacon: beacon
 | | tandh: t&h sensor
 | 
 *
```

## Hardware firmware

The hardware firmware is synched to the pico device in parts. 

**Pico Connection and FS Sync:**

```mermaid
graph TD
  pico(Pico)
  
  open --mode--> pico
  sync --mode--> pico
  
```

```mermaid
---
title: "Pico Open Protocol"
---
graph TD
  Open-Pico --> connect-to-board -.-> Sync
  Sync --up--> pico_firmware[[pico_firmware]]
  Sync --up--> lights[[lights]]
  logs[[logs]] --down--> Sync
  
```




### Device ID

Examplar Device ID file:

```yaml

```



The default mode for parsing a device ID structure is to first cast each field to a container/collection type and enforce the first value as the unique name and the 2nd value, if present, as a **Universal** unique identifier.





### Experiments

1. The `Experiment` class manages the saving of data in  specific folders and logs experiement events.
2. A folder qualifies as an Experiemnt if it contains the `.experiment` file with the UUID of the experiment.
3. The file `<Experiment_name>.yaml` contains the event logs of the experiments.





