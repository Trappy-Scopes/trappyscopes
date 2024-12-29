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





