# Experiment Framework

This module provides an `Experiment` object that virtually represents an actual experiment. The main functionalities that this object provides are:

1. Directory and file management
2. Recording proper metadata and preserving experimental conditions over differnt sessions
3. Creating and managing measurement streams (contain indipendent stream of measurements).
4. Implement an Event Model to keep track of all the steps and changes.

Some additional features that are implemented for convinience:

1. Automatic pdf report generation: `ExpReport`
2. File synching with a file-server: `ExpRsync`
3. Integrated protocol recording system
4. Integrated plotting system


## The `Experiment` system

An `Experiment` is created by a `User` (`User.login("you")`) with `exp = Experiment("experiment_name")`. It is composed of multiple `Sessions`. A new session is created automatically, everytime the user restarts the trappy-scopes application, or when a new experiment is created. By creating an experiemt, you automatically  change the working directory to the one created by the experiment. Within the experiment directories, files can be created as such.


### Main tools:


#### Scheduler (`ExpScheduler`)

`ExpScheduler` uses the [schedule](https://schedule.readthedocs.io/en/stable/) API to manage and schedule tasks at a cetrain recurring frequency or at a given time. The module can be used in the following way:

```python
exp.schedule.every(10).minutes.do(record_temp)
```

 It is instructive to read this paragraph on the pecularities of event scheduling: [here](https://schedule.readthedocs.io/en/stable/#when-not-to-use-schedule). The `ExpSchedule` module automatically starts a thread to execute the remaining jobs, hence, `schedule.run_pending()` should **not** be called explicitly.

#### Measurement Streams 

#### Experiment notes

Notes can be logged in the dataset as special `ExpEvent`: `user_note`. The functions `exp.note`, `exp.write` can be used to log specific notes.

The `exp.notebook` property (implemented in the `ExpNotebook` class can be used to access the whole notebook at once.




### Other Tools:

1. `exp.delay`: a better replacement to `time.sleep`.
2. `exp.track`: time and log execution of a function.
3. `exp.user_prompt`: accept input from the user.
4. `exp.multiprompt`: accept multiple prompts from the user.
5. `exp.interrupted`: mark an interruption in the experiment sequence.



