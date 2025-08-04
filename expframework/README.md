# Experiment Framework (`expframework`)

This submodule describes an `Experiment` object with the following functionalities:

1. Data management
2. Recording proper metadata and preserving experimental conditions over different sessions
3. Creating and managing independently timed measurement streams.
4. Implement an Event Model to keep track of all digital and user steps.

Some additional features that are implemented for convinience:

1. Automatic pdf report generation: `ExpReport`
2. File synching with a file-server: `ExpSync`
3. Integrated protocol recording system and ScriptEngine
4. Integrated plotting system

## The `Experiment` system

### What is an Experiment?

An experiment is a series of operations done by a human or manchine to investigate a scientific question. To answer a scientific question, the `User` typically describes an experimental system, and gathers multiple streams of measurements (a timelapse of microscopy images), a timeseries of temperature. This data is further analysed to make scientific deductions or to test a hypothesis. The Trappy-Scopes `expframework`submodule formalizes this very general procedure in the following way:

We imagine the following: A scientist in the lab creates the observable (and interesting!) phenomena in a tiny box and observes it. This observation leads to scientific discovery. To make this happen, we need a box (or a system) where this phenomena happens and the means to manipulate the state of this box. Further, we need eyes to observe the phenomena and a systematic way of detailing it. The box can be approximated by a set of scientific instruments:

1. Actuators: insturments that can change the state of a system
2. Detectors: instruments that can read information (detect phenomena)
3. Processors: instruments that control the above two and records information

A `ScopeAssembly` describes one or many scientific instruments. The devices within these assembly are used to create and change the environment of the experimental system. A simple example is below:

We have a microscope with a red light source and we need to record an image of the sample.

```python
scope ## < Scope Assembly :: 6 devices :: microscope>
scope.red.setVs(2) ## Set red channel to 2V (actuator)
scope.cam.read("img", "red_image_png") ## Record an image on the camera (detector)
```

An `Experiment` is an additional construct around the code used to control the instument. To emit anykind of datafile from the `ScopeAssembly` construct, an experiment has to be created. 

An `Experiment` is typically composed of multiple `Sessions`. Everytime, an experiment is open or closed, or a user logoffs and a new one logs in, the session is changed. A `User` is the person/machine that is operating the experiment or the scope. It´s only usage is to determine ownership of the data and to furnish user information metadata.

An `Experiment` at its core is a seperate directory for storing datafiles. Additionally, it is composed of multiple streams of measurements and clocks to time different events. Further, it records a list of events in cronological order. Many generic events that may be needed to program an experiment (like delays, prompts, recurring tasks) are available within the framework and are programmed to automatically log themselves.



## Componets at a glance

The following graph represents an `Experiemnt` context. The framework can be understood completely by understanding these different components.

```
Experiment {name, unique eid}
*- root directory: (datafile1, datafile2, ... datafileN)
|- payload (postprocess, analysis, converted)
|- scripts (directory of all executed scripts)
:-<user and session>---------------------------------------------------------------
|- User                                                              :: User.name() 
|- Session1, Session2, Session3, ..., SessionN                       :: exp.sessions
::-<parameters and measurements>----------------------------------------------------
|- attributes (parameters for the experiment)                        :: exp.attribs
|- MeasurementStream1, MeasurementStream2,...MeasurementStreamN      :: exp.mstreams
::-<time and events>----------------------------------------------------------------
|- expclock, {<additional clocks>}                                   :: exp.clocks
|- scheduler (for scheduling/timing operations, `ExpSchedule`)       :: exp.schedule
|- ExpEvent1, ExpEvent2, ExpEvent3, ... ExpEventN (`[ExpEvent, ]`)   :: exp.events
::-<metadata and description>--------------------------------------------------------
|- notebook (a series of timed notes by the user)                    :: exp.notebook
|- report (a pdf report w measurements and all events)               :: exp.report                              
|- logs  (everything described above and more metadata)              :: exp.logs
::-<utilities>-----------------------------------------------------------------------
|- additional services (ExpSync, ExpGit)  
*
```

### Create an experiemt

An `Experiment` is  with `exp = Experiment("experiment_name")`. A new session is created automatically, everytime the user restarts the trappy-scopes application, or when a new experiment is created. By creating an experiemt, you automatically  change the working directory to the one created by the experiment. Within the experiment directories, files can be created as such.

You can also construct an experiment using a few fields:

```python
exp = Experiment.Construct(["longterm", "temp", "curve"], scopeid=True, \
                           username=True, date=True, time=True, eid=True)
## creates: MDev__YB__2025_03_09__0hh_16mm__longterm_temp_curve__3f58ee69ec
```

### Data storage  and corresponding utilities(`ExpSync`and `ExpGit`)

With the creation of an experiment, the directory of the REPL changes to the `exp.exp_dir`.  All files created from the python REPL or from a script would emit files in this folder. To mark the creation of a file using and `ExpEvent`, the method `exp.newfile` method. 

The `ExpSync` extension provides an interface to synchronise files using [`rsync`])(https://rsync.samba.org/). Rightnow the utility only supporst samba shares on linux and mac os. A `file_server` configuration block can be added to enable it:

```yaml
file_server:
    active: true					 ### option switcg
    destination: "{date}"  ### destination folder from the root of the share [effify]
    server: 172.22.63.19   ### ip address of the server 
    share: share_folder    ### share folder (there are multiple shres on the same ip)
    username: admin       ### username for authentification.
    password: pass   			### password for authentification.
 ## [effify]: supports fields: date, time, user, scopeid
```

#todo The `ExpGit` utility can be additionally enabled to track the changes in the experiment. The utility can be setup to exclude large data files (which it does by default). This could be used as an extra protection against poor event modelling.


### Measurement Streams

#### Scheduler (`ExpScheduler`) #todo

`ExpScheduler` uses the [schedule](https://schedule.readthedocs.io/en/stable/) API to manage and schedule tasks at a cetrain recurring frequency or at a given time. The module can be used in the following way:

```python
exp.schedule.every(10).minutes.do(record_temp)
```

 It is instructive to read this paragraph on the pecularities of event scheduling: [here](https://schedule.readthedocs.io/en/stable/#when-not-to-use-schedule). The `ExpSchedule` module automatically starts a thread to execute the remaining jobs, hence, `schedule.run_pending()` should **not** be called explicitly.

#### Experiment notes

Notes can be logged in the dataset as special `ExpEvent`: `user_note`. The functions `exp.note`, `exp.write` can be used to log specific notes.

The `exp.notebook` property (implemented in the `ExpNotebook` class can be used to access the whole notebook at once.


## ScriptEngine

`ScriptEngine` is used to run a prefedined procedure in an `Experiment`. It can be used to create experiments, run code, and define special python fucntions. Currently,  it is necessary to pass `globals()` as the first parameter:

```python
ScriptEngine.run(globals(), scripts=["path/to/script1.py", "path/to/script2.py"])
```

General/recommended templates for writing scripts can be found in the `scripts\toyexps` folder. A `__description__` methods should ideally be defined. This text field is logged in the experiment events list to provide a meaningfull context for the script. Scripts are automatically copied in the experiments folder.



### Other Tools:

1. `exp.delay`: a better replacement to `time.sleep`.
2. `exp.track`: time and log execution of a function.
3. `exp.user_prompt`: accept input (prompt) from the user.
4. `exp.multiprompt`: accept multiple prompts from the user.
5. `exp.interrupt`: mark an interruption in the experiment sequence.



